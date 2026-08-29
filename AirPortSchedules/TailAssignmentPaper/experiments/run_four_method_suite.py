"""Generate and run a correctness/performance suite for all four A-only methods.

The suite is deliberately separate from canonical data/instances. It creates
small regression cases plus a scalable feasible family, then evaluates the same
JSON case with:

    legacy_paper_c13, legacy_endpoint_split, legacy_corrected, event_based

Examples:
    python experiments/run_four_method_suite.py --generate
    python experiments/run_four_method_suite.py --run --executable F:/.../CPLEXamp.exe
    python experiments/run_four_method_suite.py --generate --run --executable F:/.../CPLEXamp.exe
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import shutil
import sys
import time
from pathlib import Path

from pyomo.environ import Constraint, Var, value

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.compact_a_event_model import PaperEventBasedMILPScheduler
from src.generate_feasible_instances import build_feasible_instance
from src.model import (
    LegacyCorrectedMILPScheduler,
    LegacyEndpointSplitMILPScheduler,
    LegacyPaperC13MILPScheduler,
)

SUITE_DIR = ROOT / "data" / "four_method_suite"
RESULTS_PATH = ROOT / "results" / "tables" / "four_method_suite.csv"
SUMMARY_PATH = ROOT / "results" / "tables" / "four_method_suite_summary.csv"
FORMULATIONS = {
    "legacy_paper_c13": LegacyPaperC13MILPScheduler,
    "legacy_endpoint_split": LegacyEndpointSplitMILPScheduler,
    "legacy_corrected": LegacyCorrectedMILPScheduler,
    "event_based": PaperEventBasedMILPScheduler,
}
DEFAULT_PERFORMANCE_GRID = [(p, h) for p in (5, 10, 20, 40) for h in (7, 15, 30)]
EXTENDED_PERFORMANCE_GRID = [
    (p, h)
    for p in (10, 20, 30, 40, 50)
    for h in (7, 15, 30, 40, 50)
]


def generate_suite(performance_grid) -> None:
    SUITE_DIR.mkdir(parents=True, exist_ok=True)
    for path in SUITE_DIR.glob("*.json"):
        path.unlink()

    special_cases = {
        "c13_loophole_test.json": ROOT / "data" / "instances" / "c13_loophole_test.json",
        "event_vs_legacy_clean_test.json": ROOT / "data" / "instances" / "event_vs_legacy_clean_test.json",
    }
    for name, source in special_cases.items():
        shutil.copyfile(source, SUITE_DIR / name)

    for p, h in performance_grid:
        data = build_feasible_instance(
            density=1.0,
            p=p,
            h=h,
            index=0,
            maintenance_families="A",
        )
        path = SUITE_DIR / f"perf_p={p}_h={h}.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    manifest = {
        "description": "A-only four-method correctness and performance suite",
        "methods": list(FORMULATIONS),
        "regression_cases": list(special_cases),
        "performance_grid": [
            {"P": p, "H": h, "file": f"perf_p={p}_h={h}.json"}
            for p, h in performance_grid
        ],
        "notes": [
            "Regression cases preserve the canonical inputs by copying them.",
            "Performance cases are generated with overnight A maintenance and a common JSON input per cell.",
            "Objective parity is checked only between optimal runs on the same case.",
        ],
    }
    (SUITE_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Generated {len(list(SUITE_DIR.glob('*.json')))} JSON cases in {SUITE_DIR}")


def model_size(model) -> tuple[int, int]:
    return (
        len(list(model.component_data_objects(Var, active=True))),
        len(list(model.component_data_objects(Constraint, active=True))),
    )


def run_case(path: Path, formulation: str, solver: str, executable: str | None, limit: int,
             configuration: str, warm_start: bool) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    row: dict[str, object] = {
        "case": path.stem,
        "file": path.name,
        "P": len(data["Aircrafts"]),
        "H": max(int(float(flight[4]) // 1440) + 1 for flight in data["Flights"]),
        "F": len(data["Flights"]),
        "formulation": formulation,
        "solver_configuration": configuration,
        "warm_start": warm_start,
        "status": "",
        "objective": "",
        "vars": "",
        "constraints": "",
        "cpu_s": "",
        "wall_s": "",
        "build_s": "",
        "error": "",
    }
    started = time.perf_counter()
    try:
        scheduler_type = FORMULATIONS[formulation]
        if formulation.startswith("legacy_"):
            scheduler = scheduler_type(str(path), enabled_checks=["A"])
        else:
            scheduler = scheduler_type(str(path))
        with contextlib.redirect_stdout(io.StringIO()):
            scheduler.build_model()
        row["build_s"] = round(time.perf_counter() - started, 6)
        row["vars"], row["constraints"] = model_size(scheduler.model)
        solve_started = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            summary = scheduler.solve(
                solver_name=solver,
                executable=executable,
                time_limit=limit,
                warm_start=warm_start,
                solver_options=(
                    {"preprocessing presolve": 0}
                    if configuration == "presolve_off" and solver.lower() == "cplexamp"
                    else {}
                ),
            )
        row.update(
            status=summary.get("status", ""),
            objective=summary.get("obj", ""),
            cpu_s=summary.get("cpu", ""),
            wall_s=round(time.perf_counter() - solve_started, 6),
        )
    except Exception as error:  # preserve one failure row per method/case
        row["status"] = "ERROR"
        row["error"] = f"{type(error).__name__}: {error}"
    return row


def run_suite(solver: str, executable: str | None, limit: int,
              configuration: str, warm_start: bool, pattern: str) -> None:
    paths = sorted(
        path for path in SUITE_DIR.glob(pattern) if path.name != "manifest.json"
    )
    if not paths:
        raise SystemExit("Suite is empty; run with --generate first.")
    rows = [
        run_case(path, formulation, solver, executable, limit, configuration, warm_start)
        for path in paths
        for formulation in FORMULATIONS
    ]
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary_rows = []
    for formulation in FORMULATIONS:
        method_rows = [row for row in rows if row["formulation"] == formulation]
        performance_rows = [
            row for row in method_rows if str(row["case"]).startswith("perf_")
        ]
        optimal_rows = [row for row in performance_rows if row["status"] == "optimal"]
        summary_rows.append({
            "formulation": formulation,
            "cases": len(method_rows),
            "performance_cases": len(performance_rows),
            "performance_optimal": len(optimal_rows),
            "performance_infeasible": sum(
                row["status"] == "infeasible" for row in performance_rows
            ),
            "mean_vars": round(sum(int(row["vars"]) for row in performance_rows) / len(performance_rows), 3),
            "mean_constraints": round(sum(int(row["constraints"]) for row in performance_rows) / len(performance_rows), 3),
            "mean_cpu_s": round(sum(float(row["cpu_s"]) for row in optimal_rows) / len(optimal_rows), 6) if optimal_rows else "",
            "mean_wall_s": round(sum(float(row["wall_s"]) for row in optimal_rows) / len(optimal_rows), 6) if optimal_rows else "",
        })
    with SUMMARY_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)

    parity_failures = []
    for case in sorted({row["case"] for row in rows}):
        case_rows = [row for row in rows if row["case"] == case]
        optimal = [row for row in case_rows if row["status"] == "optimal"]
        objectives = {round(float(row["objective"]), 6) for row in optimal}
        if len(optimal) == 4 and len(objectives) != 1:
            parity_failures.append((case, sorted(objectives)))
    print(f"Wrote {len(rows)} rows to {RESULTS_PATH}")
    print(f"Wrote formulation summary to {SUMMARY_PATH}")
    if parity_failures:
        print(f"Objective parity failures: {parity_failures}")
    else:
        print("Objective parity passed for every case where all four methods were optimal.")
    loophole = [row for row in rows if row["case"] == "c13_loophole_test"]
    if loophole:
        status_by_method = {
            row["formulation"]: row["status"] for row in loophole
        }
        expected = {
            "legacy_paper_c13": "optimal",
            "legacy_endpoint_split": "optimal",
            "legacy_corrected": "infeasible",
            "event_based": "optimal",
        }
        if status_by_method == expected:
            print("C13 loophole regression passed: corrected model rejects the fixed violation.")
        else:
            print(f"C13 loophole regression mismatch: {status_by_method}")


def main() -> None:
    global SUITE_DIR, RESULTS_PATH, SUMMARY_PATH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--solver", default="cplexamp")
    parser.add_argument("--executable", default=None)
    parser.add_argument("--time-limit", type=int, default=60)
    parser.add_argument("--configuration", choices=["presolve_on", "presolve_off"], default="presolve_on")
    parser.add_argument("--warm-start", action="store_true")
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Use P=10,20,30,40,50 and H=7,15,30,40,50.",
    )
    parser.add_argument("--suite-dir", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--pattern",
        default="*.json",
        help="Case filename glob used during --run; manifest.json is always excluded.",
    )
    args = parser.parse_args()
    if not args.generate and not args.run:
        parser.error("choose --generate, --run, or both")
    performance_grid = EXTENDED_PERFORMANCE_GRID if args.extended else DEFAULT_PERFORMANCE_GRID
    if args.suite_dir:
        SUITE_DIR = ROOT / args.suite_dir
    if args.output:
        RESULTS_PATH = ROOT / args.output
        SUMMARY_PATH = RESULTS_PATH.with_name(
            f"{RESULTS_PATH.stem}_summary{RESULTS_PATH.suffix}"
        )
    if args.generate:
        generate_suite(performance_grid)
    if args.run:
        run_suite(
            args.solver,
            args.executable,
            args.time_limit,
            args.configuration,
            args.warm_start,
            args.pattern,
        )


if __name__ == "__main__":
    main()
