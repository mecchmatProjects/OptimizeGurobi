"""Upper- and lower-bound study for the strengthened maintenance MILP.

For every instance and formulation variant this records the three bound
sources that bracket the optimum of the minimisation model:

  * the LP relaxation value, a valid lower bound;
  * a timeline-feasible heuristic schedule cost, a valid upper bound only when
    every flight is covered;
  * the MILP incumbent (primal bound) and dual bound, with the resulting gap.

Only raw per-run rows are written; aggregation belongs to the analysis step.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import logging
from pathlib import Path

from pyomo.environ import (Constraint, NonNegativeReals, SolverFactory, Var,
                           value)  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from model import MILP_Sheduler, Scheduler  # noqa: E402
from solver_utils import (apply_time_limit, extract_bounds, termination_of,
                          relax_integrality, parse_deferral_days, solve_and_load)
from experiment_utils import ExperimentCSV, experiment_metadata, instance_paths
from benchmark_validation import verify_milp_certificate
from tqdm import tqdm

VARIANTS = {
    "baseline": {},
    "combined": {
        "use_strong_maint_link": True,
        "use_sparse_maint_aircraft_domain": True,
        "use_tight_c13_m": True,
        "use_maint_reachability": False,
        "use_strong_maint_conflicts": True,
    },
}

FIELDS = [
    "instance", "variant", "mode", "flights", "aircraft", "days",
    "variables", "constraints", "z_variables", "build_s", "solver",
    "time_limit_s", "status", "objective", "dual_bound", "primal_bound",
    "mip_gap", "nodes", "runtime_s", "coverage", "error",
    "max_deferral_days", "restrictive_deferral", "wall_s", "bound_validated",
]


def model_size(model):
    variables = sum(1 for _ in model.component_data_objects(Var, active=True))
    constraints = sum(1 for _ in model.component_data_objects(Constraint, active=True))
    return variables, constraints


def blank_row(path, variant, mode):
    row = {field: None for field in FIELDS}
    row.update(instance=path.stem, variant=variant, mode=mode, error="")
    return row


def run_heuristic(path, heuristic, max_deferral_days=3, enabled_checks=None):
    started = time.perf_counter()
    row = blank_row(path, f"heuristic:{heuristic}", "heuristic")
    row["solver"] = "none"
    row.update(max_deferral_days=max_deferral_days,
               restrictive_deferral=max_deferral_days is not None, bound_validated=False)
    try:
        scheduler = Scheduler(str(path), allow_ferry=False, heuristic=heuristic)
        routes, unassigned = scheduler.optimize()
        total = 0.0
        certificate = {'assignment': {}, 'maintenance_events': []}
        for aircraft in scheduler.aircrafts:
            timeline = scheduler.get_timeline(aircraft, routes[aircraft])
            if timeline is None:
                raise RuntimeError(f"infeasible replay for aircraft {aircraft}")
            total += timeline["cost"]
            certificate['assignment'].update({str(fid): aircraft for fid in routes[aircraft]})
            certificate['maintenance_events'].extend(
                {'tail': aircraft, 'check': event['check'], 'station': event['orig'],
                 'start': event['start'], 'end': event['end']}
                for event in timeline['events'] if event['kind'] == 'MAINT')
        assigned = len(scheduler.flights) - len(unassigned)
        row.update(
            flights=len(scheduler.flights),
            aircraft=len(scheduler.aircrafts),
            status="complete" if not unassigned else "partial",
            objective=total,
            coverage=assigned / len(scheduler.flights) if scheduler.flights else None,
        )
        # A partial schedule leaves flights uncovered, so its cost is not a bound.
        if not unassigned:
            target = MILP_Sheduler(str(path), enabled_checks=enabled_checks,
                                   max_hour_check_deferral_days=max_deferral_days)
            validation = verify_milp_certificate(target, certificate)
            row['bound_validated'] = validation['status'] == 'PASS'
            if row['bound_validated']:
                row["primal_bound"] = total
            else:
                row['error'] = 'cost only; model certificate failed: ' + '; '.join(validation['errors'][:3])
        else:
            row["error"] = f"{len(unassigned)} unassigned"
    except Exception as exc:  # noqa: BLE001 - recorded, never silently dropped
        row["status"] = "error"
        row["error"] = f"{type(exc).__name__}: {exc}"
    row["runtime_s"] = round(time.perf_counter() - started, 6)
    return row


def run_solve(path, variant, mode, solver_name, executable, time_limit,
              enabled_checks, max_deferral_days=3, tee=False):
    row = blank_row(path, variant, mode)
    row.update(solver=solver_name, time_limit_s=time_limit)
    row.update(max_deferral_days=max_deferral_days,
               restrictive_deferral=max_deferral_days is not None)
    build_started = time.perf_counter()
    try:
        scheduler = MILP_Sheduler(str(path), enabled_checks=enabled_checks,
                     max_hour_check_deferral_days=max_deferral_days)
        model = scheduler.build_model(**VARIANTS[variant])
    except Exception as exc:  # noqa: BLE001
        row["status"] = "build-error"
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["build_s"] = round(time.perf_counter() - build_started, 6)
        return row

    row["build_s"] = round(time.perf_counter() - build_started, 6)
    variables, constraints = model_size(model)
    row.update(
        flights=len(scheduler.flight_ids),
        aircraft=len(scheduler.aircraft_ids),
        days=len(scheduler.days),
        variables=variables,
        constraints=constraints,
        z_variables=len(list(model.Z)),
    )

    if mode == "lp":
        relax_integrality(model)

    if mode == "build":
        row["status"] = "built"
        row["solver"] = "none"
        row["time_limit_s"] = None
        return row

    solver_kwargs = {"executable": str(executable)} if executable else {}
    solver = SolverFactory(solver_name, **solver_kwargs)
    if not apply_time_limit(solver, solver_name, time_limit):
        row["time_limit_s"] = None

    solve_started = time.perf_counter()
    try:
        result, loaded, loaded_objective = solve_and_load(solver, model, tee=tee)
        row["runtime_s"] = round(time.perf_counter() - solve_started, 6)
        row["status"] = termination_of(result)
        dual_bound, primal_bound, gap, nodes = extract_bounds(result)
        row.update(dual_bound=dual_bound, primal_bound=primal_bound,
                   mip_gap=gap, nodes=nodes)
        row["objective"] = (dual_bound if row['status'].lower() == 'optimal' else None) if mode == 'lp' else loaded_objective
        row['bound_validated'] = loaded
        if primal_bound is None:
            row["error"] = "no incumbent within budget"
    except Exception as exc:  # noqa: BLE001
        row["runtime_s"] = round(time.perf_counter() - solve_started, 6)
        row["status"] = "error"
        row["error"] = f"{type(exc).__name__}: {exc}"
    row['wall_s'] = time.perf_counter() - build_started
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solver", default="cplex")
    parser.add_argument("--executable", type=Path, default=None)
    parser.add_argument("--time-limit", type=int, default=300)
    parser.add_argument("--heuristic", default="greedy+insertion")
    parser.add_argument("--only-checks", default="")
    parser.add_argument("--skip-heuristic", action="store_true")
    parser.add_argument("--skip-lp", action="store_true")
    parser.add_argument("--build-only", action="store_true",
                        help="Record model size and build time without solving.")
    parser.add_argument('--pattern', default='*.json')
    parser.add_argument('--max-hour-check-deferral-days', type=parse_deferral_days, default=3)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('--tee', action='store_true')
    args = parser.parse_args(argv)

    enabled_checks = [item.strip().upper()
                      for item in args.only_checks.split(",")
                      if item.strip()] or None

    paths = instance_paths(args.input_dir, args.pattern)
    if not paths:
        raise SystemExit(f"No JSON instances found in {args.input_dir}")

    logging.basicConfig(level=logging.INFO)
    metadata = experiment_metadata(ROOT, paths, {**vars(args), 'variants': VARIANTS})
    with ExperimentCSV(args.output, FIELDS, metadata, args.resume, args.overwrite) as output:
        completed = {(row['instance'], row['variant'], row['mode']) for row in output.previous
                     if row['status'] not in ('error', 'build-error')}
        for path in tqdm(paths, desc='Bound instances'):
            if not args.skip_heuristic and not args.build_only:
                key = (path.stem, f'heuristic:{args.heuristic}', 'heuristic')
                if key not in completed:
                    output.write(run_heuristic(path, args.heuristic,
                                              args.max_hour_check_deferral_days, enabled_checks))
            for variant in VARIANTS:
                modes = ['build'] if args.build_only else (['milp'] if args.skip_lp else ['lp', 'milp'])
                for mode in modes:
                    if (path.stem, variant, mode) not in completed:
                        row = run_solve(path, variant, mode, args.solver, args.executable,
                                        args.time_limit, enabled_checks,
                                        args.max_hour_check_deferral_days, args.tee)
                        output.write(row)
                        logging.info('%s %s %s: %s', path.stem, variant, mode, row['status'])
    print(f'Wrote {args.output}')


if __name__ == "__main__":
    main()
