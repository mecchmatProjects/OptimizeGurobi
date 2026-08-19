"""Compare baseline and strengthened maintenance-trigger linking.

The baseline remains the default formulation. The strengthened variant is
selected only through ``use_strong_maint_link=True`` and writes to a separate
Step 7 result file.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

from pyomo.environ import NonNegativeReals, SolverFactory, Var, value

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from model import MILP_Sheduler  # noqa: E402


def model_size(model):
    variables = sum(1 for _ in model.component_data_objects(Var, active=True))
    constraints = sum(
        1 for _ in model.component_data_objects(ctype=None, active=True)
        if _.ctype.__name__ == "Constraint"
    )
    return variables, constraints


def run_variant(path, strong_link, solver_name, time_limit, solve_lp):
    started = time.perf_counter()
    scheduler = MILP_Sheduler(str(path))
    model = scheduler.build_model(
        use_strong_maint_link=strong_link,
    )
    build_seconds = time.perf_counter() - started
    variables, constraints = model_size(model)

    row = {
        "instance": path.stem,
        "variant": "strong" if strong_link else "baseline",
        "variables": variables,
        "constraints": constraints,
        "c9_rows": len(list(model.c9)),
        "z_variables": len(list(model.Z)),
        "build_s": round(build_seconds, 6),
        "solver": solver_name if solve_lp else "none",
        "status": "built",
        "objective": None,
        "runtime_s": None,
    }

    if not solve_lp:
        return row

    for variable in model.component_data_objects(Var, active=True):
        variable.domain = NonNegativeReals
        variable.setub(1.0)

    solver = SolverFactory(solver_name)
    if time_limit is not None:
        solver.options["timelimit"] = time_limit
    solve_started = time.perf_counter()
    result = solver.solve(model, tee=False)
    row["runtime_s"] = round(time.perf_counter() - solve_started, 6)
    row["status"] = str(result.solver.termination_condition)
    try:
        row["objective"] = float(value(model.obj))
    except (TypeError, ValueError):
        row["objective"] = None
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solver", default="cplex")
    parser.add_argument("--time-limit", type=int, default=300)
    parser.add_argument("--solve-lp", action="store_true")
    args = parser.parse_args()

    paths = sorted(args.input_dir.glob("*.json"))
    if not paths:
        raise SystemExit(f"No JSON instances found in {args.input_dir}")

    rows = []
    for path in paths:
        for strong_link in (False, True):
            rows.append(run_variant(
                path,
                strong_link,
                args.solver,
                args.time_limit,
                args.solve_lp,
            ))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
