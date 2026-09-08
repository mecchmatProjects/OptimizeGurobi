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
from pathlib import Path

from pyomo.environ import (Constraint, NonNegativeReals, SolverFactory, Var,
                           value)  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from model import MILP_Sheduler, Scheduler  # noqa: E402

VARIANTS = {
    "baseline": {},
    "combined": {
        "use_strong_maint_link": True,
        "use_sparse_maint_aircraft_domain": True,
        "use_tight_c13_m": True,
        "use_maint_reachability": True,
        "use_strong_maint_conflicts": True,
    },
}

FIELDS = [
    "instance", "variant", "mode", "flights", "aircraft", "days",
    "variables", "constraints", "z_variables", "build_s", "solver",
    "time_limit_s", "status", "objective", "dual_bound", "primal_bound",
    "mip_gap", "nodes", "runtime_s", "coverage", "error",
]


def _finite(raw):
    if raw is None:
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    return number if float("-inf") < number < float("inf") else None


def extract_bounds(result):
    """Return (dual bound, primal bound, relative gap, nodes).

    Handles both the legacy Pyomo results object and the APPSI interface, which
    reports the incumbent and bound directly rather than under ``problem``.
    """
    dual_bound = _finite(getattr(result, "objective_bound", None))
    primal_bound = _finite(getattr(result, "incumbent_objective", None))
    if dual_bound is None and primal_bound is None:
        problem = getattr(result, "problem", None)
        if problem is not None:
            dual_bound = _finite(getattr(problem, "lower_bound", None))
            primal_bound = _finite(getattr(problem, "upper_bound", None))
    gap = None
    if dual_bound is not None and primal_bound is not None:
        denominator = abs(primal_bound)
        if denominator > 1e-12:
            gap = abs(primal_bound - dual_bound) / denominator
    nodes = None
    solver_info = getattr(result, "solver", None)
    for holder in (result, solver_info):
        if holder is None:
            continue
        for attribute in ("nodes_explored", "number_of_nodes", "node_count"):
            candidate = _finite(getattr(holder, attribute, None))
            if candidate is not None:
                return dual_bound, primal_bound, gap, int(candidate)
    return dual_bound, primal_bound, gap, nodes


def termination_of(result):
    condition = getattr(result, "termination_condition", None)
    if condition is None:
        solver_info = getattr(result, "solver", None)
        condition = getattr(solver_info, "termination_condition", None)
    return str(condition) if condition is not None else "unknown"


def model_size(model):
    variables = sum(1 for _ in model.component_data_objects(Var, active=True))
    constraints = sum(1 for _ in model.component_data_objects(Constraint, active=True))
    return variables, constraints


def apply_time_limit(solver, solver_name, time_limit):
    """Set the wall-clock limit using the option name each backend recognises.

    Returns False when no limit could be attached, so the caller can record that
    the run was effectively unlimited instead of reporting a bogus budget.
    """
    if time_limit is None:
        return False
    name = solver_name.lower()
    # APPSI-style interfaces carry the limit on a typed config object.
    config = getattr(solver, "config", None)
    if config is not None and hasattr(config, "time_limit"):
        config.time_limit = float(time_limit)
        return True
    options = getattr(solver, "options", None)
    if options is None:
        return False
    if "gurobi" in name:
        options["TimeLimit"] = int(time_limit)
    elif "cplex" in name:
        options["timelimit"] = int(time_limit)
    elif "glpk" in name:
        options["tmlim"] = int(time_limit)
    elif "highs" in name:
        options["time_limit"] = float(time_limit)
    else:
        options["TimeLimit"] = int(time_limit)
    return True


def blank_row(path, variant, mode):
    row = {field: None for field in FIELDS}
    row.update(instance=path.stem, variant=variant, mode=mode, error="")
    return row


def run_heuristic(path, heuristic):
    started = time.perf_counter()
    row = blank_row(path, f"heuristic:{heuristic}", "heuristic")
    row["solver"] = "none"
    try:
        scheduler = Scheduler(str(path), allow_ferry=False, heuristic=heuristic)
        routes, unassigned = scheduler.optimize()
        total = 0.0
        for aircraft in scheduler.aircrafts:
            timeline = scheduler.get_timeline(aircraft, routes[aircraft])
            if timeline is None:
                raise RuntimeError(f"infeasible replay for aircraft {aircraft}")
            total += timeline["cost"]
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
            row["primal_bound"] = total
        else:
            row["error"] = f"{len(unassigned)} unassigned"
    except Exception as exc:  # noqa: BLE001 - recorded, never silently dropped
        row["status"] = "error"
        row["error"] = f"{type(exc).__name__}: {exc}"
    row["runtime_s"] = round(time.perf_counter() - started, 6)
    return row


def run_solve(path, variant, mode, solver_name, executable, time_limit,
              enabled_checks):
    row = blank_row(path, variant, mode)
    row.update(solver=solver_name, time_limit_s=time_limit)
    build_started = time.perf_counter()
    try:
        scheduler = MILP_Sheduler(str(path), enabled_checks=enabled_checks)
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
        for variable in model.component_data_objects(Var, active=True):
            variable.domain = NonNegativeReals
            variable.setub(1.0)

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
        # Never auto-load: a time-limited run may end with no incumbent at all,
        # which the APPSI interface reports by raising on solution load.
        try:
            result = solver.solve(model, load_solutions=False)
        except TypeError:
            result = solver.solve(model)
        row["runtime_s"] = round(time.perf_counter() - solve_started, 6)
        row["status"] = termination_of(result)
        dual_bound, primal_bound, gap, nodes = extract_bounds(result)
        row.update(dual_bound=dual_bound, primal_bound=primal_bound,
                   mip_gap=gap, nodes=nodes)
        row["objective"] = primal_bound
        if primal_bound is None:
            row["error"] = "no incumbent within budget"
    except Exception as exc:  # noqa: BLE001
        row["runtime_s"] = round(time.perf_counter() - solve_started, 6)
        row["status"] = "error"
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solver", default="highs")
    parser.add_argument("--executable", type=Path, default=None)
    parser.add_argument("--time-limit", type=int, default=300)
    parser.add_argument("--heuristic", default="greedy+insertion")
    parser.add_argument("--only-checks", default="")
    parser.add_argument("--skip-heuristic", action="store_true")
    parser.add_argument("--skip-lp", action="store_true")
    parser.add_argument("--build-only", action="store_true",
                        help="Record model size and build time without solving.")
    args = parser.parse_args()

    enabled_checks = [item.strip().upper()
                      for item in args.only_checks.split(",")
                      if item.strip()] or None

    paths = sorted(
        path for path in args.input_dir.glob("*.json")
        if path.name != "manifest.json"
        and not path.name.endswith((".solution.json", ".validation.json",
                                    ".metrics.json", ".manifest.json"))
    )
    if not paths:
        raise SystemExit(f"No JSON instances found in {args.input_dir}")

    rows = []
    for index, path in enumerate(paths, start=1):
        print(f"[{index}/{len(paths)}] {path.stem}", flush=True)
        if not args.skip_heuristic:
            rows.append(run_heuristic(path, args.heuristic))
        for variant in VARIANTS:
            if args.build_only:
                rows.append(run_solve(path, variant, "build", args.solver,
                                      args.executable, args.time_limit,
                                      enabled_checks))
                continue
            if not args.skip_lp:
                rows.append(run_solve(path, variant, "lp", args.solver,
                                      args.executable, args.time_limit,
                                      enabled_checks))
            rows.append(run_solve(path, variant, "milp", args.solver,
                                  args.executable, args.time_limit,
                                  enabled_checks))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
