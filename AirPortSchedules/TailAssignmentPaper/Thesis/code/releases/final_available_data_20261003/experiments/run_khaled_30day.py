#!/usr/bin/env python3
"""Bounded paper-style classical MILP runs on the 30-day M/L/X instances.

The instances use zero-based flight IDs. The model now maps those IDs to their
actual cost-matrix row. A polynomial bipartite path-cover construction creates
and validates a complete no-ferry routing start before Gurobi is called. This
is only an incumbent generator; Gurobi still optimizes and proves (or fails to
prove) optimality under the requested time limit.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
import logging
from pathlib import Path

from pyomo.environ import Constraint, SolverFactory, Var, value
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_bipartite_matching

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from model import MILP_Sheduler  # noqa: E402  # type: ignore[reportMissingImports]
from solver_utils import (apply_time_limit, extract_bounds, termination_of, solve_and_load,
                          apply_threads, completed_status, solver_details)
from experiment_utils import ExperimentCSV, experiment_metadata, instance_paths
from tqdm import tqdm

DEFAULT_INSTANCES = [
    "md30_p20_h30_r1.json",
    "ld30_p30_h30_r1.json",
    "xd30_p40_h30_r1.json",
]


def build_routing_start(scheduler, model):
    """Construct a complete aircraft path cover and validate active model rows."""
    flights = scheduler.flight_ids
    n_flights = len(flights)
    n_aircraft = len(scheduler.aircraft_ids)

    arrivals_by_airport = {airport: [] for airport in scheduler.airports}
    for row, fid in enumerate(flights):
        flight = scheduler.flight_data[fid]
        arrivals_by_airport[flight["destination"]].append(
            (flight["arrivalTime"], row, fid)
        )

    edge_rows = []
    edge_columns = []
    for column, fid in enumerate(flights):
        flight = scheduler.flight_data[fid]
        feasible_aircraft = set(scheduler._x_aircrafts_for_flight(fid))

        for arrival, predecessor_row, predecessor in arrivals_by_airport[flight["origin"]]:
            if arrival + scheduler.min_turn > flight["departureTime"]:
                continue
            if not feasible_aircraft.intersection(
                scheduler._x_aircrafts_for_flight(predecessor)
            ):
                continue
            edge_rows.append(predecessor_row)
            edge_columns.append(column)

        for slot, aircraft in enumerate(scheduler.aircraft_ids):
            if (scheduler.aircraft_init[aircraft] == flight["origin"]
                    and scheduler._x_has_arc(fid, aircraft)):
                edge_rows.append(n_flights + slot)
                edge_columns.append(column)

    graph = csr_matrix(
        ([True] * len(edge_rows), (edge_rows, edge_columns)),
        shape=(n_flights + n_aircraft, n_flights),
        dtype=bool,
    )
    matched_predecessor = maximum_bipartite_matching(graph, perm_type="row")
    if len(matched_predecessor) != n_flights or any(
        int(row) < 0 for row in matched_predecessor
    ):
        raise RuntimeError(
            f"No complete aircraft path cover: matched "
            f"{sum(int(row) >= 0 for row in matched_predecessor)}/{n_flights} flights"
        )

    successor = {
        int(predecessor_row): flights[column]
        for column, predecessor_row in enumerate(matched_predecessor)
    }
    root_aircraft = {
        n_flights + slot: aircraft
        for slot, aircraft in enumerate(scheduler.aircraft_ids)
    }
    flight_row = {fid: row for row, fid in enumerate(flights)}
    assignment = {}

    for root, aircraft in root_aircraft.items():
        node = root
        while node in successor:
            fid = successor[node]
            if fid in assignment:
                raise RuntimeError(f"Path cover assigned flight {fid} more than once")
            if not scheduler._x_has_arc(fid, aircraft):
                raise RuntimeError(
                    f"Path uses forbidden assignment arc ({fid}, {aircraft})"
                )
            assignment[fid] = aircraft
            node = flight_row[fid]

    if len(assignment) != n_flights:
        raise RuntimeError(
            f"Path cover has {len(assignment)}/{n_flights} flights reachable "
            "from initial aircraft positions"
        )

    for fid, aircraft in assignment.items():
        for candidate in scheduler._x_aircrafts_for_flight(fid):
            model.x[fid, candidate].set_value(int(candidate == aircraft))

    violations = []
    tolerance = 1e-6
    for component in model.component_objects(ctype=Constraint, active=True):
        for row in component.values():
            body = value(row.body)
            if row.lower is not None and body < value(row.lower) - tolerance:
                violations.append(row.name)
            if row.upper is not None and body > value(row.upper) + tolerance:
                violations.append(row.name)
    if violations:
        raise RuntimeError(
            f"Routing start violates {len(violations)} model rows; "
            f"examples: {violations[:5]}"
        )

    return assignment


def _finite(value_):
    if value_ is None:
        return None
    try:
        parsed = float(value_)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def assignment_cost_lower_bound(instance_path):
    """Valid objective floor from exact flight coverage and nonnegative costs."""
    import json

    data = json.loads(Path(instance_path).read_text(encoding="utf-8"))
    return sum(min(float(cost) for cost in row) for row in data["Cost_Matrix"])


def validated_bounds(raw_dual, primal, assignment_floor):
    """Return a conservative lower bound and whether the solver bound is sane."""
    consistent = (
        raw_dual is not None
        and raw_dual >= assignment_floor - 1e-6
        and (primal is None or raw_dual <= primal + 1e-6)
    )
    lower = max(assignment_floor, raw_dual) if consistent else assignment_floor
    gap = (
        max(0.0, (primal - lower) / abs(primal))
        if primal is not None and abs(primal) > 1e-12
        else None
    )
    return lower, consistent, gap


def run_instance(path, solver_name, executable, time_limit, overlap="none", threads=None):
    started = time.perf_counter()
    scheduler = MILP_Sheduler(path, prepare_maintenance=False)
    model = scheduler.build_model(
        use_maintenance=False,
        allow_ferry=True,
        use_overlap=(overlap != "none"),
        use_clique_overlap=(overlap == "clique"),
    )
    build_s = time.perf_counter() - started
    variable_count = sum(
        1 for _ in model.component_data_objects(ctype=Var, active=True)
    )
    constraint_count = sum(
        1 for _ in model.component_data_objects(ctype=Constraint, active=True)
    )
    assignment = {}
    start_objective = None
    start_error = ''
    try:
        assignment = build_routing_start(scheduler, model)
        start_objective = value(model.obj)
    except RuntimeError as exc:
        start_error = str(exc)
        for variable in model.component_data_objects(Var):
            variable.set_value(None)
    trivial_bound = assignment_cost_lower_bound(path)

    solver_kwargs = {"executable": str(executable)} if executable else {}
    solver = SolverFactory(solver_name, **solver_kwargs)
    apply_time_limit(solver, solver_name, time_limit)
    apply_threads(solver, solver_name, threads)
    if "gurobi" in solver_name.lower():
        solver.options["TimeLimit"] = int(time_limit)
        solver.options["MIPFocus"] = 1
        solver.options["Heuristics"] = 0.25
        solver.options["Presolve"] = 2

    solve_started = time.perf_counter()
    solve_kwargs = {'tee': False}
    warmstart = bool(assignment) and solver.warm_start_capable()
    if warmstart:
        solve_kwargs['warmstart'] = True
    result, _loaded, _objective = solve_and_load(solver, model, **solve_kwargs)
    solve_s = time.perf_counter() - solve_started
    status = termination_of(result)
    details = solver_details(result, solver)
    raw_dual, solver_primal, _gap, nodes = extract_bounds(result)
    candidates = [bound for bound in (solver_primal, start_objective) if bound is not None]
    primal = min(candidates) if candidates else None
    if not completed_status(status):
        raw_dual = None
        primal = start_objective
    proven_lower, consistent_raw_dual, gap = validated_bounds(
        raw_dual, primal, trivial_bound
    )

    return {
        **details,
        'error': '' if completed_status(status) else f"Solver failure: {status}; {details['solver_message']}",
        "instance": Path(path).stem,
        "aircraft": len(scheduler.aircraft_ids),
        "flights": len(scheduler.flight_ids),
        "horizon_days": len(scheduler.days),
        "formulation": f"classical_{overlap}_overlap",
        "solver": solver_name,
        "time_limit_s": time_limit,
        "build_s": round(build_s, 3),
        "solve_s": round(solve_s, 3),
        "variables": variable_count,
        "constraints": constraint_count,
        "z_variables": scheduler.z_var_count,
        "start_incumbent": start_objective,
        "status": status,
        "assignment_cost_lower_bound": trivial_bound,
        "raw_solver_dual_bound": raw_dual,
        "dual_bound_consistent": consistent_raw_dual,
        "dual_bound": proven_lower,
        "primal_bound": primal,
        "relative_gap_pct": 100.0 * gap if gap is not None else None,
        "assignment_coverage": len(assignment) / len(scheduler.flight_ids),
        'warmstart_submitted': warmstart, 'start_error': start_error,
        'nodes': nodes, 'wall_s': time.perf_counter() - started,
        'stem': Path(path).stem, 'P': len(scheduler.aircraft_ids),
        'H': len(scheduler.days), 'F': len(scheduler.flight_ids),
        'vars': variable_count, 'cpu_s': solve_s, 'objective': primal,
        'gap_pct': 100 * gap if gap is not None else None,
    }


def write_latex_table(source, destination):
    with Path(source).open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    if not rows or any(row.get('status') in ('error', 'missing') for row in rows):
        raise ValueError('Table requires non-error run rows; incomplete outcomes must be reviewed separately.')
    if any(row.get('formulation') != 'classical_none_overlap' for row in rows):
        raise ValueError('This table is for the paper-style classical model without overlap rows.')
    def number(raw, decimals=0):
        parsed = _finite(raw)
        return '--' if parsed is None else f'{parsed:,.{decimals}f}'
    lines = [r'\begin{table}[htbp]', r'\centering\small',
             r'\caption{Classical routing results regenerated from the declared raw CSV. '
             r'Finite upper bounds come from solver incumbents or validated complete routing starts; '
             r'solve status and budget remain recorded in the source CSV.}',
             r'\label{tab:khaled_30day_classical}', r'\begin{tabular}{lrrrrrrrr}',
             r'\toprule', r'Instance & $P$ & $F$ & Variables & Constraints & Build (s) & '
             r'Upper bound & Lower bound & Gap (\%) \\', r'\midrule']
    for row in rows:
        label = row['instance'].split('_')[0].replace('_', r'\_')
        values = [label, number(row['aircraft']), number(row['flights']),
                  number(row['variables']), number(row['constraints']), number(row['build_s'], 1),
                  number(row['primal_bound'], 1), number(row['dual_bound'], 1),
                  number(row['relative_gap_pct'], 2)]
        lines.append(' & '.join(values) + r' \\')
    lines.extend([r'\bottomrule', r'\end{tabular}', r'\end{table}'])
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "data" / "Long_family")
    parser.add_argument("--pattern", default=None)
    parser.add_argument("--instances", nargs="*", default=None)
    parser.add_argument("--solver", default="cplex")
    parser.add_argument("--executable", type=Path,
                        default=None)
    parser.add_argument("--time-limit", type=int, default=60)
    parser.add_argument("--overlap", choices=("none", "pairwise", "clique"),
                        default="none",
                        help="Supplemental conflict formulation; none matches the paper's compact routing core.")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "results" / "tables" / "khaled_30day_classical.csv")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--quick', action='store_true', help='First selected instance only.')
    selection.add_argument('--full', action='store_true', help='All selected instances.')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('--threads', type=int, default=None)
    parser.add_argument('--continue-on-solver-error', action='store_true')
    parser.add_argument('--table-csv', type=Path, help='Generate LaTeX only; do not run a solver.')
    parser.add_argument('--latex-output', type=Path)
    args = parser.parse_args(argv)
    if args.table_csv:
        if not args.latex_output:
            parser.error('--table-csv requires --latex-output.')
        write_latex_table(args.table_csv, args.latex_output)
        return
    if args.instances is not None and args.pattern is not None:
        parser.error('Choose --instances or --pattern, not both.')
    paths = (instance_paths(args.input_dir, args.pattern) if args.pattern else
             [args.input_dir / name for name in (args.instances or DEFAULT_INSTANCES)])
    if args.quick:
        paths = paths[:1]

    fields = [
        "instance", "aircraft", "flights", "horizon_days", "formulation",
        "solver", "time_limit_s", "build_s", "solve_s", "variables",
        "constraints", "z_variables", "start_incumbent", "status",
        "assignment_cost_lower_bound", "raw_solver_dual_bound",
        "dual_bound_consistent", "dual_bound", "primal_bound",
        "relative_gap_pct", "assignment_coverage", "error",
        'warmstart_submitted', 'start_error', 'wall_s', 'nodes',
        'solver_message', 'solver_return_code',
    ]
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    metadata = experiment_metadata(ROOT, paths, vars(args))
    with ExperimentCSV(args.output, fields, metadata, args.resume, args.overwrite) as output:
        completed = {row['instance'] for row in output.previous
                     if completed_status(row['status'])}
        for path in tqdm(paths, desc='Classical instances', file=sys.stdout):
            if path.stem in completed:
                continue
            if not path.exists():
                row = {'instance': path.stem, 'status': 'missing'}
            else:
                try:
                    row = run_instance(path, args.solver, args.executable,
                                       args.time_limit, overlap=args.overlap, threads=args.threads)
                except Exception as exc:
                    row = {'instance': path.stem, 'status': 'error',
                           'error': f'{type(exc).__name__}: {exc}'}
            output.write(row)
            logging.info('%s: %s', path.stem, row['status'])
            if not completed_status(row['status']) and not args.continue_on_solver_error:
                logging.error('%s', row.get('error', 'missing input'))
                return 1
    print(f"WROTE {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
