"""Compare the legacy and compact event formulations for A checks only."""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import sys
import time
from pathlib import Path

from pyomo.common.errors import ApplicationError
from pyomo.environ import Constraint, Var

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.compact_a_event_model import (
    CompactAEventMILPScheduler,
    OrderedAEventMILPScheduler,
)
from src.model import LegacyEndpointSplitMILPScheduler

FORMULATIONS = {
    "legacy_a": LegacyEndpointSplitMILPScheduler,
    "compact_a_event": CompactAEventMILPScheduler,
    "ordered_a_event": OrderedAEventMILPScheduler,
}


def metadata(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "instance": path.name,
        "P": len(data["Aircrafts"]),
        "F": len(data["Flights"]),
    }


def run_one(path: Path, formulation: str, solver: str, executable: str, limit: int):
    row = metadata(path)
    row["formulation"] = formulation
    started = time.perf_counter()
    try:
        if formulation == "legacy_a":
            scheduler = LegacyEndpointSplitMILPScheduler(
                str(path), enabled_checks=["A"]
            )
            scheduler.build_model()
        elif formulation == "compact_a_event":
            scheduler = CompactAEventMILPScheduler(str(path))
            scheduler.build_model()
        else:
            scheduler = OrderedAEventMILPScheduler(str(path))
            scheduler.build_model()
        build_s = time.perf_counter() - started
        model = scheduler.model
        if model is None:
            raise RuntimeError("Model was not built")
        variables = len(list(model.component_data_objects(Var, active=True)))
        constraints = len(
            list(model.component_data_objects(Constraint, active=True))
        )
        solve_started = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            summary = scheduler.solve(
                solver_name=solver,
                executable=executable,
                time_limit=limit,
                warm_start=False,
            )
        row.update(
            {
                "status": summary.get("status"),
                "objective": summary.get("obj"),
                "vars": variables,
                "constraints": constraints,
                "build_s": round(build_s, 6),
                "wall_s": round(time.perf_counter() - solve_started, 6),
                "error": "",
            }
        )
    except (ApplicationError, OSError, RuntimeError, TypeError, ValueError) as error:
        row.update(
            {
                "status": "ERROR",
                "objective": "",
                "vars": "",
                "constraints": "",
                "build_s": round(time.perf_counter() - started, 6),
                "wall_s": "",
                "error": f"{type(error).__name__}: {error}",
            }
        )
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default="data/feasible_instances")
    parser.add_argument("--pattern", default="DataCplex_density=1_p=10_h=*_test_0.json")
    parser.add_argument("--solver", default="cplexamp")
    parser.add_argument("--executable", required=True)
    parser.add_argument("--time-limit", type=int, default=60)
    parser.add_argument("--output", default="results/tables/formulation_a_comparison.csv")
    args = parser.parse_args()

    paths = sorted(Path(args.input_dir).glob(args.pattern))
    rows = [
        run_one(path, formulation, args.solver, args.executable, args.time_limit)
        for path in paths
        for formulation in FORMULATIONS
    ]
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "instance", "P", "F", "formulation", "status", "objective", "vars",
        "constraints", "build_s", "wall_s", "error",
    ]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {output}")


if __name__ == "__main__":
    main()
