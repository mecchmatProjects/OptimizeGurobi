"""Run named A-only profiles with independent replay and provenance."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from pyomo.environ import Constraint, Var

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.benchmark_validation import extract_milp_certificate, validate_benchmark_certificate
from src.event_model import EventMILPScheduler
from src.model import (
    CorrectedAOnlyScheduler,
    EndpointSplitC13Scheduler,
    KhaledPrintedC13Scheduler,
    OptionAExecutableScheduler,
    OptionBProtectedScheduler,
)


PROFILE_BUILDERS = {
    "khaled_printed": KhaledPrintedC13Scheduler,
    "endpoint_split": EndpointSplitC13Scheduler,
    "corrected_a_interval": CorrectedAOnlyScheduler,
    "option_a": OptionAExecutableScheduler,
    "option_b": OptionBProtectedScheduler,
    "event_historical_unverified": EventMILPScheduler,
}
SOURCE_FILES = (
    ROOT / "src" / "model.py",
    ROOT / "src" / "event_model.py",
    ROOT / "src" / "benchmark_validation.py",
    ROOT / "experiments" / "run_profile_matrix.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_revision() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def input_profile(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "P": len(data["Aircrafts"]),
        "H": max(int(float(flight[4]) // 1440) + 1 for flight in data["Flights"]),
        "F": len(data["Flights"]),
        "sha256": sha256(path),
    }


def create_scheduler(profile: str, path: Path, a_calendar_dmax: int | None):
    builder = PROFILE_BUILDERS[profile]
    if profile in {"khaled_printed", "endpoint_split"}:
        if a_calendar_dmax is None:
            raise ValueError(f"{profile} requires --a-calendar-dmax")
        return builder(str(path), a_calendar_dmax=a_calendar_dmax)
    if profile == "corrected_a_interval":
        return builder(str(path), a_calendar_dmax=a_calendar_dmax)
    if profile in {"option_a", "option_b"}:
        return builder(str(path), a_calendar_dmax=a_calendar_dmax)
    return builder(str(path))


def run_one(args, path: Path) -> tuple[dict, dict | None]:
    scheduler = create_scheduler(args.profile, path, args.a_calendar_dmax)
    started = time.perf_counter()
    model = scheduler.build_model(objective=args.objective)
    build_s = time.perf_counter() - started
    profile = input_profile(path)
    row = {
        "stem": path.stem,
        "file": path.name,
        "P": profile["P"],
        "H": profile["H"],
        "F": profile["F"],
        "profile_id": scheduler.PROFILE_ID,
        "formulation_id": scheduler.FORMULATION_ID,
        "a_calendar_dmax": args.a_calendar_dmax,
        "solver": args.solver,
        "solver_version": args.solver_version,
        "threads": args.threads,
        "time_limit_s": args.time_limit,
        "status": "unsupported",
        "objective": "",
        "dual_bound": "",
        "primal_bound": "",
        "gap_pct": "",
        "cpu_s": "",
        "wall_s": "",
        "build_s": round(build_s, 6),
        "vars": 0,
        "constraints": 0,
        "z_vars": 0,
        "replay_status": "not_run",
        "replay_errors": "",
        "unsupported_errors": "",
        "has_solution": False,
        "input_sha256": profile["sha256"],
        "error": "",
    }
    certificate = None
    if model is None:
        result = scheduler.solve(solver_name=args.solver)
        row["unsupported_errors"] = ";".join(result.get("errors", []))
        return row, certificate

    row["vars"] = len(list(model.component_data_objects(Var, active=True)))
    row["constraints"] = len(list(model.component_data_objects(Constraint, active=True)))
    row["z_vars"] = len(model.Z) if hasattr(model, "Z") else 0
    solve_started = time.perf_counter()
    result = scheduler.solve(
        solver_name=args.solver,
        executable=args.executable,
        time_limit=args.time_limit,
        warm_start=False,
        solver_options={"threads": args.threads} if args.solver.startswith("cplex") else None,
    )
    row.update({
        "status": result["status"],
        "objective": result.get("obj", "") if result.get("obj") is not None else "",
        "dual_bound": result.get("dual_bound", ""),
        "primal_bound": result.get("primal_bound", ""),
        "gap_pct": "" if result.get("gap") is None else 100 * result["gap"],
        "cpu_s": result.get("cpu", ""),
        "wall_s": round(time.perf_counter() - solve_started, 6),
        "has_solution": bool(result.get("solution_loaded") or result.get("has_incumbent")),
    })
    if row["has_solution"]:
        certificate = extract_milp_certificate(scheduler)
        certificate.update({"case": path.stem, "profile_id": scheduler.PROFILE_ID})
        replay = validate_benchmark_certificate(
            scheduler.data,
            certificate,
            capacity_semantics=(
                "simultaneous" if args.profile in {"option_a", "option_b"} else "daily"
            ),
            strict_a_hour_limit=True,
        )
        row["replay_status"] = replay["status"].lower()
        row["replay_errors"] = ";".join(replay["errors"])
    return row, certificate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=sorted(PROFILE_BUILDERS))
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--pattern", default="*.json")
    parser.add_argument("--a-calendar-dmax", type=int, default=None)
    parser.add_argument("--allow-unverified-event", action="store_true")
    parser.add_argument("--solver", default="cplex")
    parser.add_argument("--executable")
    parser.add_argument("--solver-version", default="not-specified")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--time-limit", type=int, default=180)
    parser.add_argument("--objective", choices=("early_check", "check_days"), default="check_days")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.profile == "event_historical_unverified" and not args.allow_unverified_event:
        parser.error("historical event profile requires --allow-unverified-event")

    paths = sorted(path.resolve() for path in args.input_dir.glob(args.pattern))
    if not paths:
        parser.error("no matching inputs")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    certificates = []
    for path in paths:
        row, certificate = run_one(args, path)
        rows.append(row)
        if certificate is not None:
            certificates.append(certificate)
    fieldnames = list(rows[0])
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    schedules_path = args.output.with_suffix(".schedules.json")
    schedules_path.write_text(json.dumps(certificates, indent=2) + "\n", encoding="utf-8")
    snapshot_path = args.output.with_suffix(".sources.zip")
    with zipfile.ZipFile(snapshot_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in SOURCE_FILES:
            archive.write(source, source.relative_to(ROOT).as_posix())
    metadata = {
        "git_revision": git_revision(),
        "python": platform.python_version(),
        "profile": args.profile,
        "a_calendar_dmax": args.a_calendar_dmax,
        "solver": args.solver,
        "solver_version": args.solver_version,
        "executable": args.executable,
        "threads": args.threads,
        "time_limit_s": args.time_limit,
        "inputs": {
            str(path.relative_to(ROOT)): {"sha256": sha256(path)} for path in paths
        },
        "sources": {str(path.relative_to(ROOT)): sha256(path) for path in SOURCE_FILES},
        "result_csv_sha256": sha256(args.output),
        "schedule_sha256": sha256(schedules_path),
        "source_snapshot": snapshot_path.name,
        "source_snapshot_sha256": sha256(snapshot_path),
    }
    args.output.with_suffix(".metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(rows)} profile rows to {args.output}")


if __name__ == "__main__":
    main()
