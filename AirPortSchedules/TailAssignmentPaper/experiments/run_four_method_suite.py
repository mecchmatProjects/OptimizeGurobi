"""Generate and run a correctness/performance suite for the A-only methods.

The suite is deliberately separate from canonical data/instances. It creates
small regression cases plus a scalable feasible family, then evaluates the same
JSON case with:

    legacy_paper_c13, legacy_endpoint_split,
    legacy_corrected_strengthened, event_based_optimized, event_based_flex

Examples:
    python experiments/run_four_method_suite.py --generate
    python experiments/run_four_method_suite.py --run --executable F:/.../CPLEXamp.exe
    python experiments/run_four_method_suite.py --generate --run --executable F:/.../CPLEXamp.exe
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pyomo
from pyomo.environ import Constraint, TransformationFactory, Var, value

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.compact_a_event_model import (
    FlexiblePaperEventBasedMILPScheduler,
    OptimizedPaperEventBasedMILPScheduler,
    UniformFlexibleDayMILPScheduler,
    UniformFlexibleEventMILPScheduler,
    UniformNightDayMILPScheduler,
    UniformNightEventMILPScheduler,
)
from src.generate_feasible_instances import build_feasible_instance
from src.model import (
    LegacyCorrectedStrengthenedMILPScheduler,
    LegacyEndpointSplitMILPScheduler,
    LegacyHourPrefixMILPScheduler,
    LegacyPaperC13MILPScheduler,
    LegacyStrictIntervalMILPScheduler,
)
from src.validate_maintenance import validate_solved_model

SUITE_DIR = ROOT / "data" / "four_method_suite"
RESULTS_PATH = ROOT / "results" / "tables" / "four_method_suite.csv"
SUMMARY_PATH = ROOT / "results" / "tables" / "four_method_suite_summary.csv"
FORMULATIONS = {
    "legacy_paper_c13": LegacyPaperC13MILPScheduler,
    "legacy_endpoint_split": LegacyEndpointSplitMILPScheduler,
    "legacy_corrected_strengthened": LegacyCorrectedStrengthenedMILPScheduler,
    "event_based_optimized": OptimizedPaperEventBasedMILPScheduler,
    "event_based_flex": FlexiblePaperEventBasedMILPScheduler,
    "legacy_strict_interval": LegacyStrictIntervalMILPScheduler,
    "legacy_hour_prefix": LegacyHourPrefixMILPScheduler,
    "uniform_flexible_day": UniformFlexibleDayMILPScheduler,
    "uniform_flexible_event": UniformFlexibleEventMILPScheduler,
    "uniform_night_day": UniformNightDayMILPScheduler,
    "uniform_night_event": UniformNightEventMILPScheduler,
}
DEFAULT_FORMULATIONS = (
    "legacy_paper_c13",
    "legacy_endpoint_split",
    "legacy_corrected_strengthened",
    "event_based_optimized",
    "event_based_flex",
)
PROVENANCE_SOURCES = (
    ROOT / "experiments" / "run_four_method_suite.py",
    ROOT / "src" / "model.py",
    ROOT / "src" / "compact_a_event_model.py",
    ROOT / "src" / "generate_feasible_instances.py",
    ROOT / "src" / "generate_instances.py",
    ROOT / "src" / "validate_maintenance.py",
)
DEFAULT_PERFORMANCE_GRID = [(p, h) for p in (5, 10, 20, 40) for h in (7, 15, 30)]
EXTENDED_PERFORMANCE_GRID = [
    (p, h)
    for p in (10, 20, 30, 40, 50)
    for h in (7, 15, 30, 40, 50)
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _instance_profile(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "P": len(data["Aircrafts"]),
        "observed_H": max(
            int(float(flight[4]) // 1440) + 1 for flight in data["Flights"]
        ),
        "F": len(data["Flights"]),
        "declared_maintenance_families": data.get("Maintenance_Families"),
        "effective_enabled_checks": ["A"],
    }


def write_run_metadata(
    output: Path,
    input_paths: list[Path],
    solver: str,
    executable: str | None,
    solver_version: str | None,
    threads: int,
    time_limit: int,
    configuration: str,
    warm_start: bool,
    legacy_deferral_days: int | None,
    lp_relaxation: bool,
    formulations: list[str],
    append: bool,
) -> Path:
    metadata_path = output.with_suffix(".metadata.json")
    snapshot = output.with_suffix(".sources.zip")
    with zipfile.ZipFile(snapshot, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in PROVENANCE_SOURCES:
            archive.write(source, source.relative_to(ROOT).as_posix())
    if append and metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        metadata = {"schema_version": 1, "runs": []}

    metadata["runs"].append({
        "git_revision": _git_revision(),
        "python": platform.python_version(),
        "pyomo": pyomo.version.version,
        "sources": {
            str(path.relative_to(ROOT)): sha256_file(path)
            for path in PROVENANCE_SOURCES
        },
        "inputs": {
            str(path.relative_to(ROOT)): {
                "sha256": sha256_file(path),
                **_instance_profile(path),
            }
            for path in input_paths
        },
        "configuration": {
            "methods": formulations,
            "effective_enabled_checks": ["A"],
            "solver": solver,
            "solver_version": solver_version or "not-specified",
            "executable": executable,
            "time_limit_s": time_limit,
            "threads": threads,
            "presolve_configuration": configuration,
            "warm_start": warm_start,
            "legacy_max_hour_check_deferral_days": legacy_deferral_days,
            "lp_relaxation": lp_relaxation,
            "event_based_optimized_policy": "immediate-after-trigger-flight",
            "event_based_flex_max_deferral_minutes": (
                FlexiblePaperEventBasedMILPScheduler.MAX_MAINT_DEFER
            ),
            "policies": {
                name: {
                    "policy_id": FORMULATIONS[name].POLICY_ID,
                    "day_indexed_z": FORMULATIONS[name].DAY_INDEXED_Z,
                    "maximum_start_deferral_minutes": FORMULATIONS[name].MAX_MAINT_DEFER,
                    "time_grid_minutes": FORMULATIONS[name].MAINTENANCE_TIME_GRID,
                    "one_check_per": "aircraft_actual_start_calendar_day",
                    "capacity": "simultaneous_half_open_bay_occupancy",
                    "calendar_spacing_requirement": None,
                    "night_start_minute": (
                        FORMULATIONS[name].NIGHT_START_MINUTE
                        if FORMULATIONS[name].FIXED_NIGHT_START else None
                    ),
                }
                for name in formulations if name.startswith("uniform_")
            },
        },
        "result_csv_sha256": sha256_file(output),
        "source_snapshot": snapshot.name,
        "source_snapshot_sha256": sha256_file(snapshot),
        "schedule_sha256": (
            sha256_file(output.with_suffix(".schedules.json"))
            if output.with_suffix(".schedules.json").is_file() else None
        ),
    })
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata_path


def generate_suite(
    performance_grid,
    flights_per_aircraft: int | None = None,
    spread_rotations: bool = False,
    replicate_indices: list[int] | None = None,
) -> None:
    replicate_indices = replicate_indices or [0]
    if any(index < 0 for index in replicate_indices):
        raise ValueError("replicate indices must be nonnegative")
    if len(set(replicate_indices)) != len(replicate_indices):
        raise ValueError("replicate indices must be unique")
    SUITE_DIR.mkdir(parents=True, exist_ok=True)
    for path in SUITE_DIR.glob("*.json"):
        path.unlink()

    special_cases = {
        "c13_loophole_test.json": ROOT / "data" / "instances" / "c13_loophole_test.json",
        "event_vs_legacy_clean_test.json": ROOT / "data" / "instances" / "event_vs_legacy_clean_test.json",
    }
    for name, source in special_cases.items():
        shutil.copyfile(source, SUITE_DIR / name)

    performance_cases = []
    for p, h in performance_grid:
        for index in replicate_indices:
            data = build_feasible_instance(
                density=1.0,
                p=p,
                h=h,
                index=index,
                flights_per_aircraft=flights_per_aircraft,
                maintenance_families="A",
                spread_rotations=spread_rotations,
            )
            suffix = f"_r={index}" if len(replicate_indices) > 1 else ""
            filename = f"perf_p={p}_h={h}{suffix}.json"
            path = SUITE_DIR / filename
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            performance_cases.append({
                "P": p,
                "H": h,
                "replicate_index": index,
                "file": filename,
            })

    manifest = {
        "description": "A-only five-method correctness and performance suite",
        "methods": list(DEFAULT_FORMULATIONS),
        "flights_per_aircraft": flights_per_aircraft,
        "spread_rotations": spread_rotations,
        "replicate_indices": replicate_indices,
        "regression_cases": list(special_cases),
        "performance_grid": performance_cases,
        "notes": [
            "Regression cases preserve the canonical inputs by copying them.",
            "Performance cases are generated with overnight A maintenance and a common JSON input per cell.",
            "Fixed-model objective parity is checked on optimal runs for each case.",
            "The flexible-model objective is checked against the immediate-start relaxation bound.",
            "Replicate indices are passed directly to build_feasible_instance without changing stable_seed.",
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
             configuration: str, warm_start: bool, threads: int,
             legacy_deferral_days: int | None,
             lp_relaxation: bool) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    row: dict[str, object] = {
        "case": path.stem,
        "stem": path.stem,
        "file": path.name,
        "P": len(data["Aircrafts"]),
        "H": max(int(float(flight[4]) // 1440) + 1 for flight in data["Flights"]),
        "F": len(data["Flights"]),
        "formulation": formulation,
        "solver_configuration": configuration,
        "warm_start": warm_start,
        "legacy_max_hour_check_deferral_days": (
            legacy_deferral_days if formulation.startswith("legacy_") else "not-applicable"
        ),
        "lp_relaxation": lp_relaxation,
        "status": "",
        "objective": "",
        "vars": "",
        "constraints": "",
        "cpu_s": "",
        "wall_s": "",
        "build_s": "",
        "replay_status": "not_run",
        "replay_violation_count": "",
        "replay_violation_types": "",
        "replay_error": "",
        "error": "",
        "has_solution": False,
        "lower_bound": "",
        "upper_bound": "",
        "gap_pct": "",
        "nodes_max": "",
    }
    started = time.perf_counter()
    try:
        scheduler_type = FORMULATIONS[formulation]
        if formulation.startswith("legacy_"):
            scheduler = scheduler_type(
                str(path),
                enabled_checks=["A"],
                max_hour_check_deferral_days=legacy_deferral_days,
            )
        else:
            scheduler = scheduler_type(str(path))
        with contextlib.redirect_stdout(io.StringIO()):
            scheduler.build_model()
        if lp_relaxation:
            TransformationFactory("core.relax_integer_vars").apply_to(scheduler.model)
        row["build_s"] = round(time.perf_counter() - started, 6)
        row["vars"], row["constraints"] = model_size(scheduler.model)
        solve_started = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            summary = scheduler.solve(
                solver_name=solver,
                executable=executable,
                time_limit=limit,
                warm_start=warm_start,
                solver_options={
                    "threads": threads,
                    **(
                        {"preprocessing presolve": 0}
                        if configuration == "presolve_off" and solver.lower() == "cplexamp"
                        else {}
                    ),
                },
            )
        row.update(
            status=summary.get("status", ""),
            objective=summary.get("obj", ""),
            cpu_s=summary.get("cpu", ""),
            wall_s=round(time.perf_counter() - solve_started, 6),
            has_solution=summary.get("has_solution", False),
            lower_bound=summary.get("lower_bound", ""),
            upper_bound=summary.get("upper_bound", ""),
            gap_pct=100 * summary["gap"] if summary.get("gap") is not None else "",
        )
        if row["has_solution"] and not lp_relaxation:
            try:
                violations = validate_solved_model(scheduler)
                row["replay_status"] = "pass" if not violations else "fail"
                row["replay_violation_count"] = len(violations)
                row["replay_violation_types"] = ";".join(
                    sorted({violation.get("type", "flight_hours") for violation in violations})
                )
                model = scheduler.model
                schedule = {
                    "case": path.stem, "formulation": formulation,
                    "status": row["status"], "violations": violations,
                    "assignments": [
                        list(index) for index in model.X if value(model.x[index]) > 0.5
                    ],
                    "events": [],
                }
                if hasattr(model, "event_z"):
                    for key in model.Z:
                        if value(model.event_z[key]) <= 0.5:
                            continue
                        flight, aircraft, check = key
                        arrival = scheduler.flight_data[flight]["arrivalTime"]
                        completion = arrival + (
                            value(model.s[key]) if hasattr(model, "s")
                            else scheduler.check_dur[check]
                        )
                        schedule["events"].append({
                            "flight": flight, "aircraft": aircraft, "check": check,
                            "start": completion - scheduler.check_dur[check],
                            "completion": completion,
                        })
                else:
                    schedule["events"] = [
                        {"legacy_index": list(index)} for index in model.Z
                        if value(model.z[index]) > 0.5
                    ]
                row["_schedule"] = schedule
            except (AttributeError, KeyError, TypeError, ValueError) as error:
                row["replay_status"] = "error"
                row["replay_error"] = f"{type(error).__name__}: {error}"
    except Exception as error:  # preserve one failure row per method/case
        row["status"] = "ERROR"
        row["error"] = f"{type(error).__name__}: {error}"
    return row


def run_suite(solver: str, executable: str | None, limit: int, threads: int,
              solver_version: str | None, configuration: str, warm_start: bool, pattern: str,
              legacy_deferral_days: int | None, lp_relaxation: bool,
              formulations: list[str] | None = None, append: bool = False) -> None:
    active = formulations or list(DEFAULT_FORMULATIONS)
    paths = sorted(
        path for path in SUITE_DIR.glob(pattern) if path.name != "manifest.json"
    )
    if not paths:
        raise SystemExit("Suite is empty; run with --generate first.")
    rows = [
        run_case(
            path, formulation, solver, executable, limit, configuration,
            warm_start, threads, legacy_deferral_days, lp_relaxation,
        )
        for path in paths
        for formulation in active
    ]
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    schedules_path = RESULTS_PATH.with_suffix(".schedules.json")
    schedules = [row.pop("_schedule") for row in rows if "_schedule" in row]
    if append and schedules_path.is_file():
        schedules = [
            item for item in json.loads(schedules_path.read_text(encoding="utf-8"))
            if item["formulation"] not in set(active)
        ] + schedules
    schedules_path.write_text(json.dumps(schedules, indent=2) + "\n", encoding="utf-8")
    fieldnames = list(rows[0])
    if append and RESULTS_PATH.exists():
        with RESULTS_PATH.open(newline="", encoding="utf-8") as handle:
            existing = [
                row for row in csv.DictReader(handle)
                if row["formulation"] not in set(active)
            ]
        for name in (existing[0] if existing else {}):
            if name not in fieldnames:
                fieldnames.append(name)
        rows = [
            {name: row.get(name, "") for name in fieldnames}
            for row in existing + rows
        ]
    with RESULTS_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    metadata_path = write_run_metadata(
        RESULTS_PATH,
        paths,
        solver,
        executable,
        solver_version,
        threads,
        limit,
        configuration,
        warm_start,
        legacy_deferral_days,
        lp_relaxation,
        active,
        append,
    )

    present = [name for name in FORMULATIONS if any(row["formulation"] == name for row in rows)]
    summary_rows = []
    for formulation in present:
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
            "mean_vars": round(
                sum(int(row["vars"]) for row in performance_rows) / len(performance_rows),
                3,
            ) if performance_rows else "",
            "mean_constraints": round(
                sum(int(row["constraints"]) for row in performance_rows)
                / len(performance_rows),
                3,
            ) if performance_rows else "",
            "mean_cpu_s": round(sum(float(row["cpu_s"]) for row in optimal_rows) / len(optimal_rows), 6) if optimal_rows else "",
            "mean_wall_s": round(sum(float(row["wall_s"]) for row in optimal_rows) / len(optimal_rows), 6) if optimal_rows else "",
        })
    with SUMMARY_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)

    parity_failures = []
    relaxation_unresolved = []
    prefix_methods = {"legacy_strict_interval", "legacy_hour_prefix"}
    if prefix_methods.issubset(present):
        parity_formulations = set(prefix_methods)
        if not lp_relaxation and "legacy_corrected_strengthened" in present:
            parity_formulations.add("legacy_corrected_strengthened")
    elif any(name.startswith("uniform_") for name in present):
        parity_formulations = {"uniform_flexible_day", "uniform_flexible_event"}
    else:
        parity_formulations = {
            "legacy_corrected_strengthened",
            "event_based_optimized",
        }
    parity_formulations.intersection_update(present)
    for case in sorted({row["case"] for row in rows}):
        case_rows = [row for row in rows if row["case"] == case]
        by_formulation = {row["formulation"]: row for row in case_rows}
        for policy in ("flexible", "night"):
            pair = [by_formulation.get(f"uniform_{policy}_{encoding}") for encoding in ("day", "event")]
            if all(item is not None and item["status"] == "optimal" for item in pair):
                if abs(float(pair[0]["objective"]) - float(pair[1]["objective"])) > 1e-6:
                    parity_failures.append((case, f"{policy} encoding objective mismatch"))
        for encoding in ("day", "event"):
            flexible = by_formulation.get(f"uniform_flexible_{encoding}")
            night = by_formulation.get(f"uniform_night_{encoding}")
            if flexible and night and flexible["status"] == night["status"] == "optimal":
                if float(flexible["objective"]) > float(night["objective"]) + 1e-6:
                    parity_failures.append((case, "flexible optimum exceeds nightly restriction"))
        for row in case_rows:
            if str(row["formulation"]).startswith("uniform_") and row["has_solution"]:
                if row["replay_status"] != "pass":
                    parity_failures.append((case, row["formulation"], "incumbent replay failed"))
        fixed_rows = [by_formulation[name] for name in parity_formulations]
        if fixed_rows and all(row["status"] == "optimal" for row in fixed_rows):
            fixed_objectives = {
                round(float(row["objective"]), 6) for row in fixed_rows
            }
            if len(fixed_objectives) != 1:
                parity_failures.append((case, "fixed-objective mismatch", sorted(fixed_objectives)))
        if not lp_relaxation and "event_based_flex" in by_formulation and "event_based_optimized" in by_formulation:
            flexible = by_formulation["event_based_flex"]
            immediate = by_formulation["event_based_optimized"]
            if immediate["status"] == "optimal" and flexible["status"] in {"infeasible", "ERROR"}:
                parity_failures.append(
                    (case, "flex lost an immediate-start feasible case", flexible["status"])
                )
            elif immediate["status"] == "optimal" and flexible["status"] != "optimal":
                relaxation_unresolved.append((case, flexible["status"]))
            elif (
                flexible["status"] == "optimal"
                and immediate["status"] == "optimal"
                and float(flexible["objective"]) > float(immediate["objective"]) + 1e-6
            ):
                parity_failures.append(
                    (case, "flex objective exceeds immediate-start", flexible["objective"], immediate["objective"])
                )
    print(f"Wrote {len(rows)} rows to {RESULTS_PATH}")
    print(f"Wrote formulation summary to {SUMMARY_PATH}")
    print(f"Wrote provenance metadata to {metadata_path}")
    if parity_failures:
        print(f"Objective comparison failures: {parity_failures}")
        raise SystemExit(1)
    else:
        print("Fixed-formulation parity and flexible relaxation bound passed.")
    if relaxation_unresolved:
        print(f"Flexible relaxation bound unresolved for non-optimal runs: {relaxation_unresolved}")
    loophole = [row for row in rows if row["case"] == "c13_loophole_test"]
    if loophole:
        status_by_method = {
            row["formulation"]: row["status"] for row in loophole
        }
        expected = {
            name: ("infeasible" if name == "legacy_corrected_strengthened" else "optimal")
            for name in present
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
    parser.add_argument(
        "--solver-version",
        default=None,
        help="Solver version string recorded in the provenance sidecar.",
    )
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument(
        "--legacy-deferral-days",
        type=int,
        default=None,
        help="Maximum trigger-to-check day difference for legacy methods; omit for the historical unbounded setting.",
    )
    parser.add_argument(
        "--lp-relaxation",
        action="store_true",
        help="Relax integrality with Pyomo's bound-preserving transformation.",
    )
    parser.add_argument("--time-limit", type=int, default=60)
    parser.add_argument("--configuration", choices=["presolve_on", "presolve_off"], default="presolve_on")
    parser.add_argument("--warm-start", action="store_true")
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Use P=10,20,30,40,50 and H=7,15,30,40,50.",
    )
    parser.add_argument("--fleet-sizes", nargs="+", type=int, default=None)
    parser.add_argument("--horizons", nargs="+", type=int, default=None)
    parser.add_argument("--flights-per-aircraft", type=int, default=None)
    parser.add_argument("--spread-rotations", action="store_true")
    parser.add_argument("--replicates", type=int, default=1)
    parser.add_argument("--suite-dir", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--pattern",
        default="*.json",
        help="Case filename glob used during --run; manifest.json is always excluded.",
    )
    parser.add_argument(
        "--formulations",
        nargs="+",
        choices=sorted(FORMULATIONS),
        default=None,
        help="Restrict the run to a subset of methods.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Merge the run into an existing --output file, replacing only the methods run.",
    )
    args = parser.parse_args()
    if not args.generate and not args.run:
        parser.error("choose --generate, --run, or both")
    if args.threads < 1:
        parser.error("--threads must be a positive integer")
    if args.replicates < 1:
        parser.error("--replicates must be a positive integer")
    if args.legacy_deferral_days is not None and args.legacy_deferral_days < 0:
        parser.error("--legacy-deferral-days must be nonnegative")
    performance_grid = EXTENDED_PERFORMANCE_GRID if args.extended else DEFAULT_PERFORMANCE_GRID
    if args.fleet_sizes is not None or args.horizons is not None:
        default_p = sorted({p for p, _ in performance_grid})
        default_h = sorted({h for _, h in performance_grid})
        fleet_sizes = args.fleet_sizes or default_p
        horizons = args.horizons or default_h
        performance_grid = [
            (p, h) for p in fleet_sizes for h in horizons
        ]
    if args.suite_dir:
        SUITE_DIR = ROOT / args.suite_dir
    if args.output:
        RESULTS_PATH = ROOT / args.output
        SUMMARY_PATH = RESULTS_PATH.with_name(
            f"{RESULTS_PATH.stem}_summary{RESULTS_PATH.suffix}"
        )
    if args.generate:
        generate_suite(
            performance_grid,
            flights_per_aircraft=args.flights_per_aircraft,
            spread_rotations=args.spread_rotations,
            replicate_indices=list(range(args.replicates)),
        )
    if args.run:
        run_suite(
            args.solver,
            args.executable,
            args.time_limit,
            args.threads,
            args.solver_version,
            args.configuration,
            args.warm_start,
            args.pattern,
            args.legacy_deferral_days,
            args.lp_relaxation,
            args.formulations,
            args.append,
        )


if __name__ == "__main__":
    main()
