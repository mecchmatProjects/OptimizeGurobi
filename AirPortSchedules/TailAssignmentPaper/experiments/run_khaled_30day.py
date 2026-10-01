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
from pathlib import Path

from pyomo.environ import Constraint, SolverFactory, Var, value
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_bipartite_matching

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from model import MILP_Sheduler  # noqa: E402  # type: ignore[reportMissingImports]

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


def run_instance(path, solver_name, executable, time_limit, overlap="none"):
    started = time.perf_counter()
    scheduler = MILP_Sheduler(path)
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
    assignment = build_routing_start(scheduler, model)
    start_objective = value(model.obj)
    trivial_bound = assignment_cost_lower_bound(path)

    solver_kwargs = {"executable": str(executable)} if executable else {}
    solver = SolverFactory(solver_name, **solver_kwargs)
    if "gurobi" in solver_name.lower():
        solver.options["TimeLimit"] = int(time_limit)
        solver.options["MIPFocus"] = 1
        solver.options["Heuristics"] = 0.25
        solver.options["Presolve"] = 2
    elif "cplex" in solver_name.lower():
        solver.options["timelimit"] = int(time_limit)

    solve_started = time.perf_counter()
    result = solver.solve(model, tee=False, warmstart=True, load_solutions=False)
    solve_s = time.perf_counter() - solve_started
    status = str(result.solver.termination_condition)
    raw_dual = _finite(getattr(result.problem, "lower_bound", None))
    primal = _finite(getattr(result.problem, "upper_bound", None))
    proven_lower, consistent_raw_dual, gap = validated_bounds(
        raw_dual, primal, trivial_bound
    )

    return {
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
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "data" / "Long_family")
    parser.add_argument("--pattern", default="*.json")
    parser.add_argument("--instances", nargs="*", default=DEFAULT_INSTANCES)
    parser.add_argument("--solver", default="gurobi")
    parser.add_argument("--executable", type=Path,
                        default=Path(r"C:\gurobi1103\win64\bin\gurobi.bat"))
    parser.add_argument("--time-limit", type=int, default=60)
    parser.add_argument("--overlap", choices=("none", "pairwise", "clique"),
                        default="none",
                        help="Supplemental conflict formulation; none matches the paper's compact routing core.")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "results" / "tables" / "khaled_30day_classical.csv")
    args = parser.parse_args(argv)

    paths = [args.input_dir / name for name in args.instances]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in paths:
        if not path.exists():
            print(f"MISSING {path}", flush=True)
            rows.append({"instance": path.stem, "status": "missing"})
            continue
        print(f"RUN {path.name}", flush=True)
        try:
            row = run_instance(
                path, args.solver, args.executable, args.time_limit,
                overlap=args.overlap,
            )
        except Exception as exc:
            row = {"instance": path.stem, "status": "error",
                   "error": f"{type(exc).__name__}: {exc}"}
        rows.append(row)
        print(row, flush=True)

    fields = [
        "instance", "aircraft", "flights", "horizon_days", "formulation",
        "solver", "time_limit_s", "build_s", "solve_s", "variables",
        "constraints", "z_variables", "start_incumbent", "status",
        "assignment_cost_lower_bound", "raw_solver_dual_bound",
        "dual_bound_consistent", "dual_bound", "primal_bound",
        "relative_gap_pct", "assignment_coverage", "error",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"WROTE {args.output}")


if __name__ == "__main__":
    main()
