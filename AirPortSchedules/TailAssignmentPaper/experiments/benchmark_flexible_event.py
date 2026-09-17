"""Benchmark the flexible-start Event-based model against the immediate-start one."""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import sys
import time
from pathlib import Path

from pyomo.environ import Constraint, Var

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.compact_a_event_model import (  # noqa: E402
    FlexiblePaperEventBasedMILPScheduler,
    OptimizedPaperEventBasedMILPScheduler,
)

FORMULATIONS = {
    "event_based_optimized": OptimizedPaperEventBasedMILPScheduler,
    "event_based_flex": FlexiblePaperEventBasedMILPScheduler,
}
METRICS = ("vars", "constraints", "cpu_s", "wall_s")


def run_case(path: Path, formulation: str, executable: str, limit: int, repeat: int) -> dict[str, object]:
    scheduler = FORMULATIONS[formulation](str(path))
    started = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        model = scheduler.build_model()
    build_s = time.perf_counter() - started
    variables = len(list(model.component_data_objects(Var, active=True)))
    constraints = len(list(model.component_data_objects(Constraint, active=True)))
    solve_started = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        summary = scheduler.solve(
            solver_name="cplexamp",
            executable=executable,
            time_limit=limit,
            warm_start=False,
        )
    return {
        "case": path.stem,
        "formulation": formulation,
        "repeat": repeat,
        "status": summary.get("status", ""),
        "objective": summary.get("obj", ""),
        "vars": variables,
        "constraints": constraints,
        "build_s": round(build_s, 6),
        "cpu_s": summary.get("cpu", ""),
        "wall_s": round(time.perf_counter() - solve_started, 6),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default="data/four_method_suite")
    parser.add_argument("--pattern", default="perf_*.json")
    parser.add_argument("--executable", required=True)
    parser.add_argument("--time-limit", type=int, default=120)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", default="results/tables/flexible_event_benchmark.csv")
    args = parser.parse_args()

    paths = sorted(
        path
        for path in (ROOT / args.input_dir).glob(args.pattern)
        if path.name != "manifest.json"
    )
    rows = [
        run_case(path, formulation, args.executable, args.time_limit, repeat)
        for repeat in range(1, args.repeats + 1)
        for path in paths
        for formulation in FORMULATIONS
    ]
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    # The flexible model is a relaxation of the immediate-start model, so its
    # objective may only improve; anything strictly worse is a modelling error.
    violations = []
    for repeat in range(1, args.repeats + 1):
        for path in paths:
            by_formulation = {
                row["formulation"]: row
                for row in rows
                if row["repeat"] == repeat and row["case"] == path.stem
            }
            fixed = by_formulation["event_based_optimized"]
            flexible = by_formulation["event_based_flex"]
            if fixed["status"] != flexible["status"]:
                if not (fixed["status"] == "infeasible" and flexible["status"] == "optimal"):
                    violations.append((repeat, path.stem, "status", fixed["status"], flexible["status"]))
                continue
            if fixed["status"] == "optimal" and float(flexible["objective"]) > float(fixed["objective"]) + 1e-6:
                violations.append(
                    (repeat, path.stem, "objective", fixed["objective"], flexible["objective"])
                )
    if violations:
        raise SystemExit(f"Relaxation violations: {violations}")

    print(f"Wrote {len(rows)} rows to {output}")
    for metric in METRICS:
        fixed_total = sum(
            float(row[metric]) for row in rows if row["formulation"] == "event_based_optimized"
        )
        flex_total = sum(
            float(row[metric]) for row in rows if row["formulation"] == "event_based_flex"
        )
        delta = (flex_total - fixed_total) / fixed_total * 100.0
        print(f"  {metric:12s} flexible vs immediate: {delta:+.2f}%")


if __name__ == "__main__":
    main()
