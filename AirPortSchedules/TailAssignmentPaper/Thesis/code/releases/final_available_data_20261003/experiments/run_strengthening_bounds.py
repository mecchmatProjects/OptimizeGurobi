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
import gc
import logging
import sys
import time
from pathlib import Path
from typing import Any

from pyomo.environ import Constraint, SolverFactory, Var
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.benchmark_validation import verify_milp_certificate
from src.experiment_utils import ExperimentCSV, experiment_metadata, instance_paths
from src.model import MILP_Sheduler, Scheduler
from src.solver_utils import (
    apply_threads,
    apply_time_limit,
    completed_status,
    extract_bounds,
    finite,
    parse_deferral_days,
    relax_integrality,
    solve_and_load,
    solver_details,
    termination_of,
)

log = logging.getLogger(__name__)

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
    "solver_message", "solver_return_code", "solver_artifacts",
    "solver_reported_s",
]


def model_size(model):
    variables = sum(1 for _ in model.component_data_objects(Var, active=True))
    constraints = sum(1 for _ in model.component_data_objects(Constraint, active=True))
    return variables, constraints


def blank_row(path, variant, mode):
    row: dict[str, Any] = {field: None for field in FIELDS}
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
              enabled_checks, max_deferral_days=3, tee=False, artifact_dir=None,
              threads=None):
    row = blank_row(path, variant, mode)
    row.update(solver=solver_name, time_limit_s=time_limit)
    row.update(max_deferral_days=max_deferral_days,
               restrictive_deferral=max_deferral_days is not None)
    build_started = time.perf_counter()
    log.info('%s %s %s: building model', path.stem, variant, mode)
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
        z_variables=scheduler.z_var_count,
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
    apply_threads(solver, solver_name, threads)
    if not apply_time_limit(solver, solver_name, time_limit):
        row["time_limit_s"] = None

    solve_started = time.perf_counter()
    log.info('%s %s %s: transferring %s variables, %s constraints to %s',
                 path.stem, variant, mode, variables, constraints, solver_name)
    try:
        solve_kwargs: dict[str, Any] = {'tee': tee}
        if artifact_dir is not None:
            from pyomo.common.tempfiles import TempfileManager
            temp_manager: Any = TempfileManager
            directory = Path(artifact_dir) / f'{path.stem}_{variant}_{mode}'
            directory.mkdir(parents=True, exist_ok=True)
            previous_tempdir = temp_manager.tempdir
            temp_manager.tempdir = str(directory.resolve())
            row['solver_artifacts'] = str(directory.resolve())
            solve_kwargs.update(keepfiles=True, logfile=str(directory.resolve() / 'solver.log'))
        try:
            result, loaded, loaded_objective = solve_and_load(
                solver, model, load_solution=mode != 'lp', **solve_kwargs)
        finally:
            if artifact_dir is not None:
                temp_manager.tempdir = previous_tempdir
        row["runtime_s"] = round(time.perf_counter() - solve_started, 6)
        row["status"] = termination_of(result)
        row['solver_reported_s'] = finite(getattr(getattr(result, 'solver', None), 'time', None))
        row.update(solver_details(result, solver))
        dual_bound, primal_bound, gap, nodes = extract_bounds(result)
        row.update(dual_bound=dual_bound, primal_bound=primal_bound,
                   mip_gap=gap, nodes=nodes)
        row["objective"] = (dual_bound if row['status'].lower() == 'optimal' else None) if mode == 'lp' else loaded_objective
        row['bound_validated'] = (row['status'].lower() == 'optimal' and dual_bound is not None) if mode == 'lp' else loaded
        if not completed_status(row['status']):
            row.update(objective=None, dual_bound=None, primal_bound=None,
                       mip_gap=None, bound_validated=False)
            row['error'] = (f"Solver failure: {row['status']}; "
                            f"return_code={row['solver_return_code']}; {row['solver_message']}")
        elif primal_bound is None and row['status'].lower() == 'maxtimelimit':
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
    parser.add_argument('--mode', choices=('all', 'lp', 'milp'), default='all')
    parser.add_argument('--variant', choices=('both', 'baseline', 'combined'), default='both')
    parser.add_argument('--keepfiles', action='store_true', help='Retain solver log, NL and solution files.')
    parser.add_argument('--continue-on-solver-error', action='store_true',
                        help='Record failures and continue; default stops at first solver failure.')
    parser.add_argument('--threads', type=int, default=None,
                        help='Explicit thread limit; CPLEX accepts 0 for automatic, 1 limits parallel memory use.')
    args = parser.parse_args(argv)
    if args.threads is not None and (args.threads < 0 or (args.threads == 0 and 'cplex' not in args.solver.lower())):
        parser.error('--threads must be positive; CPLEX also supports 0 for automatic.')
    if args.keepfiles and not any(name in args.solver.lower() for name in ('cplex', 'gurobi', 'glpk', 'cbc', 'scip')):
        parser.error('--keepfiles requires a file-based solver interface.')

    enabled_checks = [item.strip().upper()
                      for item in args.only_checks.split(",")
                      if item.strip()] or None

    paths = instance_paths(args.input_dir, args.pattern)
    if not paths:
        raise SystemExit(f"No JSON instances found in {args.input_dir}")

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    metadata = experiment_metadata(ROOT, paths, {**vars(args), 'variants': VARIANTS})
    with ExperimentCSV(args.output, FIELDS, metadata, args.resume, args.overwrite) as output:
        completed = {(row['instance'], row['variant'], row['mode']) for row in output.previous
                     if completed_status(row['status'])}
        for path in tqdm(paths, desc='Bound instances', file=sys.stdout):
            if not args.skip_heuristic and not args.build_only:
                key = (path.stem, f'heuristic:{args.heuristic}', 'heuristic')
                if key not in completed:
                    output.write(run_heuristic(path, args.heuristic,
                                              args.max_hour_check_deferral_days, enabled_checks))
            variants = VARIANTS if args.variant == 'both' else [args.variant]
            for variant in variants:
                modes = ['build'] if args.build_only else (['lp', 'milp'] if args.mode == 'all' else [args.mode])
                if args.skip_lp and 'lp' in modes:
                    modes.remove('lp')
                for mode in modes:
                    if (path.stem, variant, mode) not in completed:
                        gc.collect()
                        row = run_solve(path, variant, mode, args.solver, args.executable,
                                        args.time_limit, enabled_checks,
                                        args.max_hour_check_deferral_days, args.tee,
                                        args.output.with_suffix('.solver') if args.keepfiles else None,
                                        args.threads)
                        output.write(row)
                        gc.collect()
                        log.info('%s %s %s: %s', path.stem, variant, mode, row['status'])
                        if not completed_status(row['status']) and not args.continue_on_solver_error:
                            log.error('%s; inspect %s', row['error'], row.get('solver_artifacts', 'solver log'))
                            return 1
    print(f'Wrote {args.output}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
