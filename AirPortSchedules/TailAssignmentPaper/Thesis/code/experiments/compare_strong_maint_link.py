"""Compare baseline and strengthened maintenance-trigger linking."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

from pyomo.environ import Constraint, NonNegativeReals, SolverFactory, Var, value

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from model import MILP_Sheduler  # noqa: E402


def apply_duration_override(scheduler, duration_days):
    """Rebuild only the sparse trigger-day index for controlled experiments."""
    for check, days in duration_days.items():
        if check in scheduler.CHECK_LIST:
            scheduler.check_dur_days[check] = days
            scheduler.check_dur[check] = days * scheduler.DAY_SHIFT

    scheduler.z_days_by_flight_check = {}
    scheduler.z_flights_by_day_check = {
        (day, check): []
        for day in scheduler.days
        for check in scheduler.CHECK_LIST
    }
    scheduler.z_var_count = 0
    last_day = scheduler.days[-1]
    for flight in scheduler.maint_flight_ids:
        arrival_day = scheduler.flight_data[flight]["day_arrival"]
        for check in scheduler.CHECK_LIST:
            if scheduler.check_days[check] is None:
                end_day = last_day
            else:
                span_days = max(1, scheduler.check_dur_days[check])
                end_day = min(arrival_day + span_days - 1, last_day)
            days = tuple(range(arrival_day, end_day + 1))
            scheduler.z_days_by_flight_check[(flight, check)] = days
            scheduler.z_var_count += len(days) * len(scheduler.aircraft_ids)
            for day in days:
                scheduler.z_flights_by_day_check[(day, check)].append(flight)


def model_size(model):
    variables = sum(1 for _ in model.component_data_objects(Var, active=True))
    constraints = sum(1 for _ in model.component_data_objects(Constraint, active=True))
    return variables, constraints


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

    This is a minimisation model, so the dual bound is a valid lower bound and
    the primal bound is the incumbent, i.e. a valid upper bound on the optimum.
    """
    problem = result.problem
    dual_bound = _finite(getattr(problem, "lower_bound", None))
    primal_bound = _finite(getattr(problem, "upper_bound", None))
    gap = None
    if dual_bound is not None and primal_bound is not None:
        denominator = abs(primal_bound)
        if denominator > 1e-12:
            gap = abs(primal_bound - dual_bound) / denominator
    nodes = None
    for attribute in ("nodes_explored", "number_of_nodes", "node_count"):
        candidate = _finite(getattr(result.solver, attribute, None))
        if candidate is not None:
            nodes = int(candidate)
            break
    return dual_bound, primal_bound, gap, nodes


def run_variant(path, strong_link, solver_name, time_limit, solve_mode,
                duration_days, enabled_checks, use_day_spacing,
                use_capacity, executable, sparse_domain, tight_c13_m,
                reachability, strong_conflicts):
    started = time.perf_counter()
    scheduler = MILP_Sheduler(str(path), enabled_checks=enabled_checks)
    if duration_days:
        apply_duration_override(scheduler, duration_days)
    model = scheduler.build_model(
        use_strong_maint_link=strong_link,
        use_sparse_maint_aircraft_domain=sparse_domain,
        use_tight_c13_m=tight_c13_m,
        use_maint_reachability=reachability,
        use_strong_maint_conflicts=strong_conflicts,
        use_day_spacing=use_day_spacing,
        use_capacity=use_capacity,
    )
    build_seconds = time.perf_counter() - started
    variables, constraints = model_size(model)
    row = {
        "instance": path.stem,
        "variant": "+".join(
            name for enabled, name in (
                (strong_link, "strong_link"),
                (sparse_domain, "sparse_z"),
                (tight_c13_m, "tight_c13_m"),
                (reachability, "reachability"),
                (strong_conflicts, "strong_conflicts"),
            ) if enabled
        ) or "baseline",
        "variables": variables,
        "constraints": constraints,
        "c9_rows": len(list(model.c9)),
        "z_variables": len(list(model.Z)),
        "build_s": round(build_seconds, 6),
        "solver": solver_name if solve_mode else "none",
        "status": "built",
        "objective": None,
        "runtime_s": None,
        "dual_bound": None,
        "primal_bound": None,
        "mip_gap": None,
        "nodes": None,
        "error": "",
    }
    if not solve_mode:
        return row
    if solve_mode == "lp":
        for variable in model.component_data_objects(Var, active=True):
            variable.domain = NonNegativeReals
            variable.setub(1.0)
    solver_kwargs = {"executable": str(executable)} if executable else {}
    solver = SolverFactory(solver_name, **solver_kwargs)
    if time_limit is not None:
        solver.options["timelimit"] = time_limit
    solve_started = time.perf_counter()
    try:
        result = solver.solve(model, tee=False)
        row["runtime_s"] = round(time.perf_counter() - solve_started, 6)
        row["status"] = str(result.solver.termination_condition)
        dual_bound, primal_bound, gap, nodes = extract_bounds(result)
        row["dual_bound"] = dual_bound
        row["primal_bound"] = primal_bound
        row["mip_gap"] = gap
        row["nodes"] = nodes
        if row["status"] not in {"optimal", "feasible"}:
            row["error"] = "non-success termination"
            return row
        row["objective"] = float(value(model.obj))
    except Exception as exc:
        row["runtime_s"] = round(time.perf_counter() - solve_started, 6)
        row["status"] = "error"
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solver", default="cplex")
    parser.add_argument("--executable", type=Path, default=None,
                        help="Optional solver executable path.")
    parser.add_argument("--time-limit", type=int, default=300)
    parser.add_argument("--solve-lp", action="store_true")
    parser.add_argument("--solve-milp", action="store_true")
    parser.add_argument("--multi-day-checks", default="C=2,D=3",
                        help="Optional duration override, e.g. C=2,D=3; "
                             "use an empty string to keep source durations.")
    parser.add_argument("--only-checks", default="",
                        help="Comma-separated active checks, e.g. C or C,D.")
    parser.add_argument("--no-day-spacing", action="store_true",
                        help="Disable calendar spacing constraints for isolation.")
    parser.add_argument("--no-capacity", action="store_true",
                        help="Disable station capacity constraints for isolation.")
    parser.add_argument("--sparse-z", action="store_true",
                        help="Use aircraft-compatible sparse maintenance z domain.")
    parser.add_argument("--tight-c13-m", action="store_true",
                        help="Use interval-specific C13 big-M bounds.")
    parser.add_argument("--reachability", action="store_true",
                        help="Filter deferred maintenance trigger days by station reachability.")
    parser.add_argument("--strong-conflicts", action="store_true",
                        help="Use pairwise maintenance-window conflict rows.")
    args = parser.parse_args()
    paths = sorted(
        path for path in args.input_dir.glob("*.json")
        if path.name != "manifest.json"
    )
    if not paths:
        raise SystemExit(f"No JSON instances found in {args.input_dir}")
    rows = []
    duration_days = {}
    if args.multi_day_checks and args.multi_day_checks.lower() != "none":
        for item in args.multi_day_checks.split(","):
            check, days = item.split("=", 1)
            duration_days[check.strip().upper()] = int(days)
    enabled_checks = [item.strip().upper() for item in args.only_checks.split(",")
                      if item.strip()] or None
    if args.solve_lp and args.solve_milp:
        parser.error("choose at most one of --solve-lp and --solve-milp")
    solve_mode = "lp" if args.solve_lp else "milp" if args.solve_milp else None
    for path in paths:
        for strong_link in (False, True):
            rows.append(run_variant(path, strong_link, args.solver,
                                    args.time_limit, solve_mode,
                                    duration_days, enabled_checks,
                                    not args.no_day_spacing,
                                    not args.no_capacity,
                                    args.executable,
                                    args.sparse_z,
                                    args.tight_c13_m,
                                    args.reachability,
                                    args.strong_conflicts))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
