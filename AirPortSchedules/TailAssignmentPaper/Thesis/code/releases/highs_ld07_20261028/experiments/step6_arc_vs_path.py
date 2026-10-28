#!/usr/bin/env python3
"""
Step 6: Arc-based vs Path-based MILP comparison.

Compares the existing arc-based classical MILP (C1-C4 core, no maintenance)
against a path-based set-partitioning MILP on the same instances.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import math
import sys
import time
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

import pyomo.environ as pyo
from pyomo.environ import Binary, Constraint, ConstraintList, Objective, Set, Var, minimize
from pyomo.opt import SolverFactory, TerminationCondition

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from model import MILP_Sheduler


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)


@dataclass
class CompareRow:
    instance: str
    repeat: int
    flights: int
    aircraft: int
    arc_status: str
    arc_obj: float | None
    arc_build_s: float
    arc_solve_s: float
    arc_total_s: float
    arc_vars: int
    arc_declared_vars: int
    arc_cons: int
    path_status: str
    path_obj: float | None
    path_enumeration_s: float
    path_build_s: float
    path_solve_s: float
    path_total_s: float
    path_vars: int
    path_cons: int
    path_count_total: int
    path_coverage_valid: bool
    objective_match: bool
    speedup_path_vs_arc: float | None


def load_instance(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def build_flight_maps(raw: dict) -> tuple[list[int], dict[int, dict]]:
    flights = []
    data = {}
    for row in raw["Flights"]:
        fid, orig, dest = int(row[0]), row[1], row[2]
        dep, arr = float(row[3]), float(row[4])
        flights.append(fid)
        data[fid] = {
            "origin": orig,
            "destination": dest,
            "dep": dep,
            "arr": arr,
        }
    flights.sort(key=lambda f: data[f]["dep"])
    return flights, data


def build_cost_lookup(raw: dict) -> tuple[list[int], dict[int, dict[int, float]]]:
    aircraft = [int(a) for a in raw["Aircrafts"]]
    aid_to_idx = {aid: idx for idx, aid in enumerate(aircraft)}

    costs = {}
    for i, row in enumerate(raw["Flights"]):
        fid = int(row[0])
        costs[fid] = {}
        for aid in aircraft:
            costs[fid][aid] = float(raw["Cost_Matrix"][i][aid_to_idx[aid]])
    return aircraft, costs


def generate_aircraft_paths(
    flights: list[int],
    fd: dict[int, dict],
    init_airport: str,
    min_turn: float,
) -> list[tuple[int, ...]]:
    """Enumerate feasible flight sequences for one aircraft.

    Includes empty path and all feasible prefixes.
    """

    by_origin = {}
    for f in flights:
        by_origin.setdefault(fd[f]["origin"], []).append(f)

    for origin in by_origin:
        by_origin[origin].sort(key=lambda x: fd[x]["dep"])

    paths: set[tuple[int, ...]] = {()}  # allow aircraft to stay idle

    def dfs(curr_airport: str, curr_time: float, curr_path: tuple[int, ...]) -> None:
        cand = by_origin.get(curr_airport, [])
        for nxt in cand:
            dep = fd[nxt]["dep"]
            arr = fd[nxt]["arr"]
            if dep < curr_time + min_turn:
                continue
            if curr_path and nxt <= curr_path[-1] and dep <= fd[curr_path[-1]]["dep"]:
                continue
            if nxt in curr_path:
                continue
            new_path = curr_path + (nxt,)
            if new_path in paths:
                continue
            paths.add(new_path)
            dfs(fd[nxt]["destination"], arr, new_path)

    dfs(init_airport, -math.inf, ())
    return sorted(paths, key=lambda p: (len(p), p))


def solve_path_based(
    instance_path: Path,
    solver_name: str = "highs",
    time_limit: int = 120,
) -> tuple[str, float | None, float, float, float, int, int, int, bool]:
    raw = load_instance(instance_path)
    flights, fd = build_flight_maps(raw)
    aircraft, costs = build_cost_lookup(raw)
    init_pos = {int(k): v for k, v in raw["AIRCRAFT_INIT_POS"].items()}

    min_turn = 60.0

    enumeration_start = time.perf_counter()
    paths_by_aircraft: dict[int, list[tuple[int, ...]]] = {}
    route_cost: dict[tuple[int, int], float] = {}
    route_covers: dict[tuple[int, int], set[int]] = {}

    total_paths = 0
    for aid in aircraft:
        paths = generate_aircraft_paths(flights, fd, init_pos[aid], min_turn)
        paths_by_aircraft[aid] = paths
        total_paths += len(paths)
        for ridx, route in enumerate(paths):
            route_cost[(aid, ridx)] = sum(costs[f][aid] for f in route)
            route_covers[(aid, ridx)] = set(route)
            enumeration_s = time.perf_counter() - enumeration_start

            build_start = time.perf_counter()
    m = pyo.ConcreteModel(name="PathBasedTAP")
    m.A = Set(initialize=aircraft)
    m.F = Set(initialize=flights)
    m.R = Set(m.A, initialize={a: list(range(len(paths_by_aircraft[a]))) for a in aircraft})
    ar_index = [(a, r) for a in aircraft for r in range(len(paths_by_aircraft[a]))]
    m.AR = Set(dimen=2, initialize=ar_index)
    m.y = Var(m.AR, domain=Binary)

    # Each aircraft chooses at most one route (including empty route).
    m.one_route = ConstraintList()
    for a in aircraft:
        m.one_route.add(sum(m.y[a, r] for r in m.R[a]) <= 1)

    # Every flight covered exactly once.
    m.cover = ConstraintList()
    for f in flights:
        m.cover.add(
            sum(
                m.y[a, r]
                for a in aircraft
                for r in m.R[a]
                if f in route_covers[(a, r)]
            ) == 1
        )

    m.obj = Objective(
        expr=sum(route_cost[(a, r)] * m.y[a, r] for a in aircraft for r in m.R[a]),
        sense=minimize,
    )
    build_s = time.perf_counter() - build_start

    solver = SolverFactory(solver_name)
    if time_limit is not None:
        solver.options["TimeLimit"] = int(time_limit)

    t0 = time.perf_counter()
    res = solver.solve(m)
    solve_s = time.perf_counter() - t0

    tc = res.solver.termination_condition
    status = str(tc)
    if tc == TerminationCondition.optimal:
        obj = float(pyo.value(m.obj))
    else:
        obj = None

    selected_routes = [
        (a, r)
        for a, r in ar_index
        if pyo.value(m.y[a, r], exception=False) is not None
        and pyo.value(m.y[a, r]) > 0.5
    ]
    coverage_valid = (
        tc == TerminationCondition.optimal
        and all(
            sum(f in route_covers[(a, r)] for a, r in selected_routes) == 1
            for f in flights
        )
        and all(sum(a == selected_a for a, _ in selected_routes) <= 1 for selected_a in aircraft)
    )

    n_var = len(list(m.component_data_objects(ctype=Var)))
    n_con = len(list(m.component_data_objects(ctype=pyo.Constraint)))

    return status, obj, enumeration_s, build_s, solve_s, n_var, n_con, total_paths, coverage_valid


def solve_arc_based(
    instance_path: Path,
    solver_name: str = "highs",
    time_limit: int = 120,
) -> tuple[str, float | None, float, float, int, int, int]:
    build_start = time.perf_counter()
    sched = MILP_Sheduler(instance_path)
    with redirect_stdout(io.StringIO()):
        sched.build_model(use_maintenance=False, allow_ferry=True, use_overlap=True)
    build_s = time.perf_counter() - build_start

    n_var = len(sched.model.x)
    n_declared_var = len(list(sched.model.component_data_objects(ctype=Var)))
    n_con = len(list(sched.model.component_data_objects(ctype=Constraint)))

    t0 = time.perf_counter()
    with redirect_stdout(io.StringIO()):
        summary = sched.solve(solver_name=solver_name, time_limit=time_limit)
    solve_s = time.perf_counter() - t0

    status = str(summary.get("status", "unknown"))
    obj = summary.get("obj")
    return status, obj, build_s, solve_s, n_var, n_declared_var, n_con


def run_comparison(
    instances: list[Path],
    repeats: int = 10,
    solver_name: str = "highs",
    time_limit: int = 120,
) -> list[CompareRow]:
    rows: list[CompareRow] = []

    for inst in instances:
        raw = load_instance(inst)
        flights = len(raw["Flights"])
        aircraft = len(raw["Aircrafts"])

        log.info("=" * 80)
        log.info("Instance: %s", inst.stem)

        for repeat in range(1, repeats + 1):
            arc_status, arc_obj, arc_build, arc_solve, arc_vars, arc_declared_vars, arc_cons = (
                solve_arc_based(inst, solver_name=solver_name, time_limit=time_limit)
            )
            path_result = solve_path_based(inst, solver_name=solver_name, time_limit=time_limit)
            (
                path_status, path_obj, path_enumeration, path_build, path_solve,
                path_vars, path_cons, path_count, path_coverage_valid,
            ) = path_result

            arc_total = arc_build + arc_solve
            path_total = path_enumeration + path_build + path_solve
            obj_match = bool(
                arc_obj is not None
                and path_obj is not None
                and abs(float(arc_obj) - float(path_obj)) <= 1e-6
                and path_coverage_valid
            )
            speedup = (arc_total / path_total) if path_total > 0 else None

            log.info(
                "Repeat %d/%d: arc=%.4fs path=%.4fs paths=%d parity=%s",
                repeat, repeats, arc_total, path_total, path_count, obj_match,
            )
            rows.append(
                CompareRow(
                    instance=inst.stem,
                    repeat=repeat,
                    flights=flights,
                    aircraft=aircraft,
                    arc_status=arc_status,
                    arc_obj=float(arc_obj) if arc_obj is not None else None,
                    arc_build_s=arc_build,
                    arc_solve_s=arc_solve,
                    arc_total_s=arc_total,
                    arc_vars=arc_vars,
                    arc_declared_vars=arc_declared_vars,
                    arc_cons=arc_cons,
                    path_status=path_status,
                    path_obj=float(path_obj) if path_obj is not None else None,
                    path_enumeration_s=path_enumeration,
                    path_build_s=path_build,
                    path_solve_s=path_solve,
                    path_total_s=path_total,
                    path_vars=path_vars,
                    path_cons=path_cons,
                    path_count_total=path_count,
                    path_coverage_valid=path_coverage_valid,
                    objective_match=obj_match,
                    speedup_path_vs_arc=speedup,
                )
            )

    return rows


def write_results(rows: list[CompareRow], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "instance", "repeat", "flights", "aircraft",
            "arc_status", "arc_obj", "arc_build_s", "arc_solve_s", "arc_total_s",
            "arc_vars", "arc_declared_vars", "arc_cons",
            "path_status", "path_obj", "path_enumeration_s", "path_build_s", "path_solve_s",
            "path_total_s", "path_vars", "path_cons", "path_count_total", "path_coverage_valid",
            "objective_match", "speedup_path_vs_arc",
        ])
        for r in rows:
            w.writerow([
                r.instance, r.repeat, r.flights, r.aircraft,
                r.arc_status, r.arc_obj, f"{r.arc_build_s:.6f}", f"{r.arc_solve_s:.6f}",
                f"{r.arc_total_s:.6f}", r.arc_vars, r.arc_declared_vars, r.arc_cons,
                r.path_status, r.path_obj, f"{r.path_enumeration_s:.6f}", f"{r.path_build_s:.6f}",
                f"{r.path_solve_s:.6f}", f"{r.path_total_s:.6f}", r.path_vars, r.path_cons,
                r.path_count_total, r.path_coverage_valid, r.objective_match,
                f"{r.speedup_path_vs_arc:.4f}" if r.speedup_path_vs_arc is not None else "N/A",
            ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--solver", default="highs")
    parser.add_argument("--time-limit", type=int, default=120)
    parser.add_argument("--output", type=Path, default=Path("results/tables/step6_arc_vs_path.csv"))
    args = parser.parse_args()

    instances = [
        Path("data/instances/ABCD_all_checks_test.json"),
        Path("data/instances/ABCD_multi_check_test.json"),
        Path("data/instances/ABCD_no_maint_test.json"),
        Path("data/instances/ABCD_near_threshold_test.json"),
        Path("data/instances/ABCD_capacity_bottleneck_test.json"),
        Path("data/instances/ABCD_check_hierarchy_test.json"),
        Path("data/instances/ABCD_two_b_one_c_test.json"),
    ]

    missing = [str(p) for p in instances if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing instances: {missing}")

    rows = run_comparison(
        instances,
        repeats=args.repeats,
        solver_name=args.solver,
        time_limit=args.time_limit,
    )
    write_results(rows, args.output)

    log.info("=" * 80)
    log.info("Wrote %d rows to %s", len(rows), args.output)


if __name__ == "__main__":
    main()
