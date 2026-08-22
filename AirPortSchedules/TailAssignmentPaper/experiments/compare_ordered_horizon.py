"""Compare legacy, ordered no-w, and standalone event ABCD formulations vs horizon."""

from __future__ import annotations

import argparse
import contextlib
import csv
import glob
import inspect
import io
import re
import sys
import time
from pathlib import Path

from pyomo.common.errors import ApplicationError

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


def parse_horizon_days(path: str) -> int:
    """Extract planning horizon h from canonical instance filenames."""
    match = re.search(r"_h=(\d+)_", Path(path).name)
    if not match:
        raise ValueError(f"Could not parse horizon from filename: {path}")
    return int(match.group(1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--instances",
        nargs="+",
        default=None,
        help="Explicit instance paths; overrides --input glob.",
    )
    parser.add_argument(
        "--input",
        default="data/feasible_instances/horizon_scaling/DataCplex_density=0.5_p=10_h=*_test_0.json",
    )
    parser.add_argument("--solver", default="cplexamp")
    parser.add_argument("--executable", default=None)
    parser.add_argument(
        "--formulations",
        nargs="+",
        choices=["legacy", "ordered_abcd", "event_exact"],
        default=["legacy", "ordered_abcd", "event_exact"],
    )
    parser.add_argument("--time-limit", type=int, default=120)
    parser.add_argument(
        "--ordered-overlap-mode",
        choices=["clique", "pairwise"],
        default="clique",
        help="Overlap constraint mode for ordered_abcd formulation.",
    )
    parser.add_argument(
        "--ordered-tight-state-big-m",
        action="store_true",
        help="Use tightened state big-M rows in ordered_abcd formulation.",
    )
    parser.add_argument(
        "--ordered-coarse-state-big-m",
        action="store_true",
        help="Force coarse state big-M rows in ordered_abcd formulation.",
    )
    parser.add_argument(
        "--output",
        default="results/tables/formulation_abcd_horizon_scaling_latest.csv",
    )
    args = parser.parse_args()

    if args.ordered_tight_state_big_m and args.ordered_coarse_state_big_m:
        parser.error("Choose at most one of --ordered-tight-state-big-m or --ordered-coarse-state-big-m")
    if args.ordered_coarse_state_big_m:
        ordered_tight_state_big_m = False
    elif args.ordered_tight_state_big_m:
        ordered_tight_state_big_m = True
    else:
        ordered_tight_state_big_m = True

    if args.instances:
        paths = [str(ROOT / Path(path)) for path in args.instances]
    else:
        paths = sorted(glob.glob(str(ROOT / args.input)))
    if not paths:
        parser.error(f"No instances matched {args.input}")

    selected = [entry for entry in FORMULATIONS if entry[0] in args.formulations]
    rows = []
    for path in paths:
        horizon_days = parse_horizon_days(path)
        for label, formulation in selected:
            row = {
                "instance": str(Path(path).relative_to(ROOT)),
                "H": horizon_days,
                "P": "",
                "F": "",
                "formulation": label,
                "status": "ERROR",
                "objective": "",
                "vars": "",
                "constraints": "",
                "cpu_s": "",
                "build_s": "",
                "wall_s": "",
                "peak_rss_mb": "",
                "error": "",
            }
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    build_started = time.perf_counter()
                    scheduler = formulation(path)
                    build_kwargs = {}
                    if label == "ordered_abcd":
                        signature = inspect.signature(scheduler.build_model)
                        if "overlap_mode" in signature.parameters:
                            build_kwargs["overlap_mode"] = args.ordered_overlap_mode
                        if "tight_state_big_m" in signature.parameters:
                            build_kwargs["tight_state_big_m"] = ordered_tight_state_big_m
                    scheduler.build_model(**build_kwargs)
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

                row.update(
                    {
                        "P": len(scheduler.aircraft_ids),
                        "F": len(scheduler.flight_ids),
                        "status": summary.get("status", "unknown"),
                        "objective": summary.get("obj", ""),
                        "vars": summary.get("n_vars", ""),
                        "constraints": summary.get("n_cons", ""),
                        "cpu_s": summary.get("cpu", ""),
                        "build_s": round(build_s, 6),
                        "wall_s": round(wall_s, 6),
                        "peak_rss_mb": peak_rss_mb,
                        "overlap_mode": (args.ordered_overlap_mode if label == "ordered_abcd" else "default"),
                        "tight_state_big_m": (ordered_tight_state_big_m if label == "ordered_abcd" else "default"),
                    }
                )
            except (ApplicationError, RuntimeError, ValueError, OSError, TypeError) as error:
                row["error"] = f"{type(error).__name__}: {error}"
            rows.append(row)

    rows.sort(key=lambda row: (int(row["H"]), row["formulation"]))

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {output}")


if __name__ == "__main__":
    main()
