"""Compare A-only models with and without the safe optional-check reduction."""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pyomo
from pyomo.environ import Constraint, Var

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model import LegacyCorrectedStrengthenedMILPScheduler
from src.validate_maintenance import validate_solved_model


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _revision() -> str | None:
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


def _solve_variant(
    data_path: Path,
    prune: bool,
    solver: str,
    executable: str | None,
    time_limit: int,
    threads: int,
    legacy_deferral_days: int,
) -> dict[str, object]:
    scheduler = LegacyCorrectedStrengthenedMILPScheduler(
        str(data_path),
        enabled_checks=["A"],
        max_hour_check_deferral_days=legacy_deferral_days,
    )
    started = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        model = scheduler.build_model(prune_unneeded_hour_checks=prune)
    build_s = time.perf_counter() - started
    variable_count = len(list(model.component_data_objects(Var, active=True)))
    constraint_count = len(list(model.component_data_objects(Constraint, active=True)))
    trigger_count = len(model.Z)
    pruned_tails = sorted(scheduler.unneeded_hour_checks_by_aircraft) if prune else []

    solve_started = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        summary = scheduler.solve(
            solver_name=solver,
            executable=executable,
            time_limit=time_limit,
            warm_start=False,
            solver_options={"threads": threads},
        )
    row: dict[str, object] = {
        "variant": "pruned" if prune else "baseline",
        "status": summary.get("status", ""),
        "objective": summary.get("obj", ""),
        "gap": summary.get("gap", ""),
        "vars": variable_count,
        "constraints": constraint_count,
        "z_vars": trigger_count,
        "pruned_tails": json.dumps(pruned_tails),
        "build_s": round(build_s, 6),
        "cpu_s": summary.get("cpu", ""),
        "wall_s": round(time.perf_counter() - solve_started, 6),
        "replay_status": "not_run",
        "replay_violations": "",
    }
    if summary.get("status") == "optimal":
        violations = validate_solved_model(scheduler)
        row["replay_status"] = "pass" if not violations else "fail"
        row["replay_violations"] = len(violations)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        default=ROOT / "data" / "instances" / "event_vs_legacy_clean_test.json",
    )
    parser.add_argument("--a-threshold", type=float, default=100000.0)
    parser.add_argument("--solver", default="cplexamp")
    parser.add_argument("--executable", default=None)
    parser.add_argument("--solver-version", default="not-specified")
    parser.add_argument("--time-limit", type=int, default=60)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--legacy-deferral-days", type=int, default=0)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "tables" / "a_check_pruning_smoke.csv",
    )
    args = parser.parse_args()
    if not args.data.is_file():
        parser.error(f"input instance does not exist: {args.data}")
    if args.a_threshold <= 0 or args.time_limit <= 0 or args.threads <= 0:
        parser.error("threshold, time limit, and thread count must be positive")
    if args.legacy_deferral_days < 0:
        parser.error("legacy deferral days must be nonnegative")

    data = json.loads(args.data.read_text(encoding="utf-8"))
    data["Maintenance_Thresholds"]["A"] = args.a_threshold
    data["Maintenance_Families"] = ["A"]
    initial = data.setdefault("Initial_Checks", {})
    initial["A"] = {
        str(aircraft): float(initial.get("A", {}).get(str(aircraft), 0.0))
        for aircraft in data["Aircrafts"]
    }

    with tempfile.TemporaryDirectory(prefix="tap-a-check-pruning-") as temp_dir:
        transformed_input = Path(temp_dir) / args.data.name
        transformed_input.write_text(json.dumps(data, indent=2), encoding="utf-8")
        bound_scheduler = LegacyCorrectedStrengthenedMILPScheduler(
            str(transformed_input),
            enabled_checks=["A"],
            max_hour_check_deferral_days=args.legacy_deferral_days,
        )
        tail_bounds = {}
        for aircraft in bound_scheduler.aircraft_ids:
            initial_hours = bound_scheduler.init_check_hrs["A"].get(aircraft, 0.0)
            max_assignable_hours = sum(
                bound_scheduler.flight_data[flight]["duration"]
                for flight in bound_scheduler._x_flights_for_aircraft(aircraft)
            ) / 60.0
            tail_bounds[str(aircraft)] = {
                "initial_a_hours": initial_hours,
                "max_assignable_flight_hours": max_assignable_hours,
                "sum_hours": initial_hours + max_assignable_hours,
                "threshold_hours": args.a_threshold / 60.0,
                "precondition_holds": (
                    initial_hours + max_assignable_hours
                    <= args.a_threshold / 60.0 + 1e-9
                ),
            }
        baseline = _solve_variant(
            transformed_input,
            False,
            args.solver,
            args.executable,
            args.time_limit,
            args.threads,
            args.legacy_deferral_days,
        )
        pruned = _solve_variant(
            transformed_input,
            True,
            args.solver,
            args.executable,
            args.time_limit,
            args.threads,
            args.legacy_deferral_days,
        )
        transformed_hash = _sha256(transformed_input)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = [baseline, pruned]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    metadata = {
        "git_revision": _revision(),
        "python": platform.python_version(),
        "pyomo": pyomo.version.version,
        "source_sha256": _sha256(ROOT / "src" / "model.py"),
        "original_input": str(args.data.resolve()),
        "original_input_sha256": _sha256(args.data),
        "transformed_input_sha256": transformed_hash,
        "profile": {
            "maintenance_families": ["A"],
            "initial_a_hours": initial["A"],
            "a_threshold_minutes": args.a_threshold,
            "legacy_deferral_days": args.legacy_deferral_days,
            "pruning_precondition": "initial A hours plus total assignable A-only flight hours <= threshold",
            "tail_bounds": tail_bounds,
        },
        "solver": {
            "name": args.solver,
            "version": args.solver_version,
            "executable": args.executable,
            "time_limit_s": args.time_limit,
            "threads": args.threads,
        },
        "results_csv_sha256": _sha256(args.output),
    }
    metadata_path = args.output.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {len(rows)} variants to {args.output}")
    print(f"Wrote provenance metadata to {metadata_path}")
    if all(row["status"] == "optimal" for row in rows):
        if abs(float(baseline["objective"]) - float(pruned["objective"])) > 1e-6:
            raise SystemExit("Safe-pruning objective mismatch")
        if pruned["z_vars"] >= baseline["z_vars"]:
            raise SystemExit("Pruning removed no maintenance-trigger variables")
        if pruned["replay_status"] != "pass":
            raise SystemExit("Pruned schedule did not pass independent replay")
        print("Safe-pruning objective and independent replay checks passed.")


if __name__ == "__main__":
    main()