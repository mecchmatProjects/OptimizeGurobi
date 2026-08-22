"""Compare legacy, ordered no-w, and standalone event ABCD formulations."""

from __future__ import annotations

import argparse
import contextlib
import csv
import glob
import io
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.compact_a_event_model import OrderedABCDEventMILPScheduler
from src.event_model import EventMILPScheduler
from src.model import LegacyEndpointSplitMILPScheduler

FORMULATIONS = (
    ("legacy", LegacyEndpointSplitMILPScheduler),
    ("ordered_abcd", OrderedABCDEventMILPScheduler),
    ("event_exact", EventMILPScheduler),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/feasible_instances/abcd_fleet_scaling/p=*/*.json")
    parser.add_argument("--solver", default="cplexamp")
    parser.add_argument("--executable", required=True)
    parser.add_argument("--time-limit", type=int, default=60)
    parser.add_argument("--output", default="results/tables/formulation_abcd_fleet_scaling.csv")
    args = parser.parse_args()

    paths = sorted(glob.glob(str(ROOT / args.input)))
    if not paths:
        parser.error(f"No instances matched {args.input}")

    rows = []
    for path in paths:
        for label, formulation in FORMULATIONS:
            with contextlib.redirect_stdout(io.StringIO()):
                build_started = time.perf_counter()
                scheduler = formulation(path)
                scheduler.build_model()
                build_s = time.perf_counter() - build_started
                solve_started = time.perf_counter()
                summary = scheduler.solve(
                    solver_name=args.solver,
                    executable=args.executable,
                    time_limit=args.time_limit,
                    warm_start=False,
                )
                wall_s = time.perf_counter() - solve_started
            try:
                import importlib
                psutil = importlib.import_module("psutil")
                peak_rss_mb = round(
                    psutil.Process().memory_info().rss / (1024 * 1024), 3
                )
            except ImportError:
                peak_rss_mb = "unavailable"
            rows.append({
                "instance": str(Path(path).relative_to(ROOT)),
                "P": len(scheduler.aircraft_ids),
                "F": len(scheduler.flight_ids),
                "formulation": label,
                "status": summary["status"],
                "objective": summary.get("obj"),
                "vars": summary["n_vars"],
                "constraints": summary["n_cons"],
                "cpu_s": summary.get("cpu"),
                "build_s": round(build_s, 6),
                "wall_s": round(wall_s, 6),
                "peak_rss_mb": peak_rss_mb,
            })

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {output}")


if __name__ == "__main__":
    main()
