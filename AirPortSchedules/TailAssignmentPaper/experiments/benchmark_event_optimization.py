"""Benchmark baseline/optimized Event-based models against strengthened legacy."""

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
    OptimizedPaperEventBasedMILPScheduler,
    PaperEventBasedMILPScheduler,
)
from src.model import LegacyCorrectedStrengthenedMILPScheduler  # noqa: E402

FORMULATIONS = {
    "legacy_corrected_strengthened": LegacyCorrectedStrengthenedMILPScheduler,
    "event_based": PaperEventBasedMILPScheduler,
    "event_based_optimized": OptimizedPaperEventBasedMILPScheduler,
}


def run_case(path: Path, formulation: str, executable: str, limit: int, repeat: int) -> dict[str, object]:
    scheduler_type = FORMULATIONS[formulation]
    scheduler = (
        scheduler_type(str(path), enabled_checks=["A"])
        if formulation.startswith("legacy_")
        else scheduler_type(str(path))
    )
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
    parser.add_argument("--time-limit", type=int, default=60)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--output",
        default="results/tables/event_optimization_benchmark.csv",
    )
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

    failures = []
    for repeat in range(1, args.repeats + 1):
        for path in paths:
            group = [row for row in rows if row["repeat"] == repeat and row["case"] == path.stem]
            by_formulation = {row["formulation"]: row for row in group}
            event_rows = [
                by_formulation["event_based"],
                by_formulation["event_based_optimized"],
            ]
            event_statuses = {row["status"] for row in event_rows}
            event_objectives = {row["objective"] for row in event_rows}
            event_matches = len(event_statuses) == 1 and (
                event_statuses != {"optimal"} or len(event_objectives) == 1
            )
            all_rows_must_match = path.stem != "c13_loophole_test"
            all_statuses = {row["status"] for row in group}
            all_objectives = {row["objective"] for row in group}
            all_match = len(all_statuses) == 1 and (
                all_statuses != {"optimal"} or len(all_objectives) == 1
            )
            if not event_matches or (all_rows_must_match and not all_match):
                failures.append(
                    (repeat, path.stem, all_statuses, all_objectives)
                )
    if failures:
        raise SystemExit(f"Parity failures: {failures}")
    print(f"Wrote {len(rows)} parity-matched rows to {output}")


if __name__ == "__main__":
    main()
