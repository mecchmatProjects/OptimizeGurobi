"""Rerun archived Gurobi experiment grids with CPLEX, preserving old evidence.

Run from the project root with --executable pointing to CPLEX Studio cplex.exe.
Completed, audited batches are reused unless --rerun is supplied. Input files
are never generated or modified. Missing historical CSVs are reported, not
reconstructed from schedules.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
from contextlib import contextmanager
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import run_four_method_suite as suite
from experiments.report_uniform_study import audit_schedule, load_and_audit

TABLES = ROOT / "results" / "tables"
CORE = (
    "uniform_multiseed10_20261021",
    "uniform_flexible_20261021",
    "five_method_20261021",
    "repaired_prefix_lp_20261021",
    "repaired_prefix_mip_20261021",
    "uniform_night_p5_20261021",
    "uniform_night_p10_20261021",
    "historical_multiseed_20261021",
    "uniform_multiseed_20261021",
)
EXTENDED = (
    "a_only_large_20261021",
    "uniform_large_20261021",
    "a_only_p4050_20261022",
)
PRE_MIDNIGHT_FIX_SOURCES = {
    "experiments\\run_four_method_suite.py": "21aebe5cb5476c5f7ef512167e48c2d1cf0819f9ac93ad4d41e8c5df6f909721",
    "experiments\\refresh_cplex_study.py": "bb24c7952d139418fc79c9104de55461d757a8903872ac9b3aaa756a000a68e2",
    "experiments\\report_uniform_study.py": "82a211d0509df839d3b863068f60f0048c3c9e2afb327250e0c5712f74aaad23",
    "src\\validate_maintenance.py": "9f8494b6e191e329c75d82f5e9ce7168895327c5f261e857c5bf912692a776d8",
}
MIDNIGHT_FIXED_VALIDATOR_SHA256 = "034ec4d364a6bd378e73b9aa05b4c24843071618297b48e479ac6041d30a5b88"


def repair_midnight_checkpoint(path: Path) -> None:
    """Migrate only known pre-fix replay evidence; never discard a solve."""
    original_bytes = path.read_bytes()
    checkpoint = json.loads(original_bytes)
    sources = checkpoint["signature"]["sources"]
    current = {str(source.relative_to(ROOT)): suite.sha256_file(source)
               for source in suite.PROVENANCE_SOURCES}
    if sources == current:
        return
    if set(sources) != set(current):
        raise ValueError("Cannot migrate checkpoint with a different source inventory")
    for relative, previous in sources.items():
        if previous != current[relative] and PRE_MIDNIGHT_FIX_SOURCES.get(relative) != previous:
            raise ValueError(f"Unreviewed source change during checkpoint repair: {relative}")
    for relative, expected in checkpoint["signature"]["inputs"].items():
        if digest(Path(relative).read_bytes()) != expected:
            raise ValueError(f"Input changed during checkpoint repair: {relative}")
    corrections = []
    for row in checkpoint["rows"]:
        if row["formulation"] not in {"uniform_flexible_day", "uniform_flexible_event"}:
            raise ValueError("Midnight migration supports only saved uniform flexible schedules")
        if not row["has_solution"] or row["replay_error"] or row["status"] == "ERROR":
            raise ValueError("Cannot repair a missing or errored incumbent")
        schedule = row["_schedule"]
        events = {(event["flight"], event["aircraft"]): event for event in schedule["events"]}
        old_violations = schedule["violations"]
        for violation in old_violations:
            if violation["type"] != "maintenance_start_day_link":
                raise ValueError(f"Non-midnight replay defect must not be migrated: {violation}")
            event = events[violation["flight"], violation["aircraft"]]
            corrected_day = int((event["start"] + 1e-6) // 1440) + 1
            if (
                violation["actual_start_day"] != int(event["start"] // 1440) + 1
                or violation["selected_days"] != [corrected_day]
                or corrected_day != violation["actual_start_day"] + 1
            ):
                raise ValueError(f"Real day-link defect must not be migrated: {violation}")
        data_path = next(Path(relative) for relative in checkpoint["signature"]["inputs"]
                         if Path(relative).stem == row["case"])
        data = json.loads(data_path.read_text(encoding="utf-8"))
        policy = {
            "time_grid_minutes": 1, "maximum_start_deferral_minutes": 1440,
            "night_start_minute": None,
        }
        problems = audit_schedule(data, schedule, policy, row["objective"])
        if problems:
            raise ValueError(f"Independent saved-schedule audit failed during migration: {problems}")
        if old_violations:
            corrections.append({"case": row["case"], "formulation": row["formulation"],
                                "previous_violations": old_violations})
        schedule["violations"] = []
        row.update(replay_status="pass", replay_violation_count=0, replay_violation_types="")
    backup = path.with_suffix(".pre_midnight_fix.json")
    if backup.exists():
        if backup.read_bytes() != original_bytes:
            raise ValueError(f"Existing repair backup differs: {backup}")
    else:
        with backup.open("xb") as handle:
            handle.write(original_bytes)
            handle.flush()
            os.fsync(handle.fileno())
    checkpoint["migration"] = {
        "reason": "Tolerance-aware midnight day classification; no optimization model changes",
        "original_checkpoint_sha256": digest(original_bytes),
        "original_sources": sources,
        "backup": backup.name,
        "revalidated_schedules": len(checkpoint["rows"]),
        "corrections": corrections,
    }
    checkpoint["signature"]["sources"] = current
    atomic_json(path, checkpoint)
    print(f"Revalidated {len(checkpoint['rows'])} saved schedules; repaired midnight classification "
          f"in {len(corrections)} row(s). Original checkpoint retained at {backup}", flush=True)


@contextmanager
def execution_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("Another CPLEX refresh is running; do not launch concurrent runs.") from error
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_json(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_input(path: Path, expected: str) -> str:
    content = path.read_bytes()
    if digest(content) == expected:
        return "exact"
    lf = content.replace(b"\r\n", b"\n")
    if expected in {digest(lf), digest(lf.replace(b"\n", b"\r\n"))}:
        return "line_endings_only"
    raise ValueError(f"Scientific input differs from archived run: {path}")


def inventory(name: str) -> tuple[dict, dict]:
    path = TABLES / f"gurobi_{name}.metadata.json"
    run = json.loads(path.read_text(encoding="utf-8"))["runs"][-1]
    inputs = {
        relative: verify_input(ROOT / relative, record["sha256"])
        for relative, record in run["inputs"].items()
    }
    csv_path = TABLES / f"gurobi_{name}.csv"
    available = csv_path.is_file()
    if available and digest(csv_path.read_bytes()) != run["result_csv_sha256"]:
        raise ValueError(f"Historical CSV hash mismatch: {csv_path}")
    changes = [
        relative for relative, expected in run["sources"].items()
        if digest((ROOT / relative).read_bytes()) != expected
    ]
    model_changes = [
        relative for relative in changes
        if Path(relative).name != "run_four_method_suite.py"
        and not (
            relative == "src\\validate_maintenance.py"
            and run["sources"][relative] == PRE_MIDNIGHT_FIX_SOURCES[relative]
            and suite.sha256_file(ROOT / relative) == MIDNIGHT_FIXED_VALIDATOR_SHA256
        )
    ]
    if model_changes:
        raise ValueError(f"Archived mathematical/validation sources changed: {model_changes}")
    return run, {
        "historical_metadata": str(path.relative_to(ROOT)),
        "historical_csv_available": available,
        "input_verification": inputs,
        "source_differences": changes,
        "expected_rows": len(inputs) * len(run["configuration"]["methods"]),
        "original_configuration": run["configuration"],
    }


def audit_batch(path: Path, original: dict, executable: Path, version: str) -> list[dict]:
    run = json.loads(path.with_suffix(".metadata.json").read_text(encoding="utf-8"))["runs"][-1]
    config = run["configuration"]
    expected = dict(original["configuration"])
    for key in ("methods", "threads", "time_limit_s", "presolve_configuration",
                "warm_start", "legacy_max_hour_check_deferral_days", "lp_relaxation"):
        if config[key] != expected[key]:
            raise ValueError(f"CPLEX configuration mismatch for {key}: {path}")
    if config["solver"] != "cplex" or config["solver_version"] != version or config["executable"] != str(executable):
        raise ValueError(f"CPLEX backend changed: {path}; choose a new --tag or --rerun")
    for relative, expected_hash in run["sources"].items():
        if digest((ROOT / relative).read_bytes()) != expected_hash:
            raise ValueError(f"Current sources differ from completed batch: {relative}")
    if set(run["inputs"]) != set(original["inputs"]):
        raise ValueError(f"CPLEX input grid changed: {path}")
    for relative, record in run["inputs"].items():
        if digest((ROOT / relative).read_bytes()) != record["sha256"]:
            raise ValueError(f"CPLEX input bytes changed: {relative}")
    for suffix, key in ((".csv", "result_csv_sha256"), (".schedules.json", "schedule_sha256"),
                        (".sources.zip", "source_snapshot_sha256")):
        if digest(path.with_suffix(suffix).read_bytes()) != run[key]:
            raise ValueError(f"CPLEX artifact hash mismatch: {path.with_suffix(suffix)}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    wanted = {(Path(relative).stem, method) for relative in original["inputs"]
              for method in config["methods"]}
    if Counter((row["case"], row["formulation"]) for row in rows) != Counter(wanted):
        raise ValueError(f"Incomplete/duplicated CPLEX grid: {path}")
    for row in rows:
        if row["status"] == "ERROR" or row["error"] or row["replay_error"]:
            raise ValueError(f"CPLEX run failed: {row}")
        unsafe = row["formulation"] in {"legacy_paper_c13", "legacy_endpoint_split"}
        if row["has_solution"] == "True" and not config["lp_relaxation"]:
            if row["replay_status"] not in ({"pass", "fail"} if unsafe else {"pass"}):
                raise ValueError(f"Unaccepted incumbent: {row}")
    if all(method.startswith("uniform_") for method in config["methods"]):
        load_and_audit(path)
    elif "legacy_hour_prefix" in config["methods"]:
        load_and_audit(path, allow_day_boundary=True)
    return rows


def summarize(rows: list[dict]) -> dict:
    groups = defaultdict(list)
    for row in rows:
        groups[row["formulation"]].append(row)
    return {
        method: {
            "runs": len(items),
            "statuses": dict(Counter(row["status"] for row in items)),
            "incumbents": sum(row["has_solution"] == "True" for row in items),
            "replay": dict(Counter(row["replay_status"] for row in items)),
            "mean_wall_s": statistics.mean(float(row["wall_s"]) for row in items),
        }
        for method, items in groups.items()
    }


def render_ten_seed(rows: list[dict], tag: str, version: str) -> str:
    groups = defaultdict(dict)
    for row in rows:
        groups[int(row["P"]), int(row["H"])][row["case"], row["formulation"]] = row
    lines = [
        r"\subsubsection{CPLEX replication of the ten-seed uniform study}",
        r"\label{subsec:cplex_refresh}",
        f"The same 40 inputs were rerun with CPLEX~{version} through Pyomo's",
        r"shell interface, one thread, presolve enabled, no warm start, and a",
        r"180-second limit per solve. The defaults of this CPLEX version were",
        r"retained, including its MIP-gap tolerance. Each returned incumbent",
        r"passed chronological replay and the independent saved-decision audit.",
        r"The original Gurobi raw CSV is absent from this checkout, although its",
        r"metadata, schedules and source archive remain available. Accordingly,",
        r"these results are a new CPLEX replication, not a hash-verified paired",
        r"comparison of solver runtimes or objective values.",
        r"\begin{table}[t]\centering\small",
        r"\caption{Ten-seed CPLEX replication. Optimal runs out of ten and wall",
        r"time as mean $\pm$ sample standard deviation on optimal runs only.",
        r"Paired denotes instances where both encodings terminated optimally.}",
        r"\label{tab:cplex_ten_seed}",
        r"\begin{tabular}{rr r l r l r}\toprule",
    ]
    lines.append(r"$|P|$ & $H$ & Day opt. & Day (s) & Event opt. & Event (s) & Paired \\\midrule")
    for (fleet, horizon), items in sorted(groups.items()):
        timings = []
        counts = []
        for encoding in ("day", "event"):
            series = [float(row["wall_s"]) for (case, method), row in items.items()
                      if method == f"uniform_flexible_{encoding}" and row["status"] == "optimal"]
            counts.append(len(series))
            timings.append(
                f"${statistics.mean(series):.2f}\\pm{statistics.stdev(series):.2f}$"
                if len(series) > 1 else "--"
            )
        paired = 0
        for case in {key[0] for key in items}:
            day, event = (items[case, f"uniform_flexible_{encoding}"] for encoding in ("day", "event"))
            if day["status"] == event["status"] == "optimal":
                if not math.isclose(float(day["objective"]), float(event["objective"]), rel_tol=0, abs_tol=1e-5):
                    raise ValueError(f"Uniform encoding objective mismatch: {case}")
                paired += 1
        lines.append(f"{fleet} & {horizon} & {counts[0]}/10 & {timings[0]} & {counts[1]}/10 & {timings[1]} & {paired}/10 " + r"\\")
    lines.extend([
        r"\bottomrule\end{tabular}\end{table}",
        r"Equality is checked only on jointly optimal pairs; time-limited",
        r"incumbents are not counted as proven optima. These workstation timings",
        r"are descriptive and do not establish a solver-independent ranking.",
        rf"Raw results: \path{{cplex129_{tag}_uniform_multiseed10_20261021.csv}}",
        r"in \path{results/tables/}, with metadata, schedules and source snapshot.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--tag", default="20261023")
    parser.add_argument("--stage", choices=("core", "extended", "all"), default="core")
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--rerun", action="store_true")
    parser.add_argument("--repair-midnight-checkpoint", action="store_true",
                        help="Revalidate and migrate the known pre-fix uniform checkpoint, keeping a backup.")
    args = parser.parse_args()
    with execution_lock(TABLES / "cplex_refresh.lock"):
        execute(args)


def execute(args) -> None:
    if not args.executable.is_file():
        raise ValueError("CPLEX executable does not exist")
    if not args.tag or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in args.tag):
        raise ValueError("--tag must contain only letters, digits, underscores and hyphens")
    probe = subprocess.run([str(args.executable), "-c", "quit"], check=True,
                           capture_output=True, text=True)
    match = re.search(r"Interactive Optimizer (\d+\.\d+\.\d+\.\d+)", probe.stdout)
    if not match:
        raise ValueError(f"Cannot identify CPLEX executable: {probe.stdout}")
    version = match.group(1)
    names = CORE if args.stage == "core" else EXTENDED if args.stage == "extended" else CORE + EXTENDED
    records = {name: inventory(name) for name in names}
    report_path = TABLES / f"cplex129_{args.tag}_{args.stage}_audit.json"
    report = {"solver_version": version, "executable": str(args.executable),
              "python": platform.python_version(), "stage": args.stage,
              "batches": {name: record for name, (_, record) in records.items()}}
    TABLES.mkdir(parents=True, exist_ok=True)
    if report_path.exists() and not args.rerun:
        previous = json.loads(report_path.read_text(encoding="utf-8"))
        for name, record in report["batches"].items():
            old = previous.get("batches", {}).get(name, {})
            for key in ("output", "audit", "summary"):
                if key in old:
                    record[key] = old[key]
    atomic_json(report_path, report)
    if args.inventory_only:
        print(f"Verified inventory: {report_path}", flush=True)
        return
    for name, (original, record) in records.items():
        output = TABLES / f"cplex129_{args.tag}_{name}.csv"
        checkpoint = output.with_suffix(".checkpoint.json")
        config = original["configuration"]
        if args.repair_midnight_checkpoint and checkpoint.exists():
            repair_midnight_checkpoint(checkpoint)
        if args.rerun and checkpoint.exists():
            checkpoint.unlink()
        complete = all(output.with_suffix(suffix).is_file() for suffix in
                       (".csv", ".metadata.json", ".schedules.json", ".sources.zip"))
        if complete and not args.rerun:
            rows = audit_batch(output, original, args.executable, version)
        else:
            inputs = [ROOT / relative for relative in original["inputs"]]
            parents = {path.parent for path in inputs}
            if len(parents) != 1:
                raise ValueError(f"Batch spans multiple input directories: {name}")
            directory = parents.pop()
            if set(directory.glob("perf_*.json")) != set(inputs):
                raise ValueError(f"Archived input selection differs from perf_*.json: {name}")
            print(f"Starting {name}: {record['expected_rows']} solves, {config['time_limit_s']} s limit", flush=True)
            suite.SUITE_DIR = directory
            suite.RESULTS_PATH = output
            suite.SUMMARY_PATH = output.with_name(output.stem + "_summary.csv")
            suite.run_suite(
                "cplex", str(args.executable), config["time_limit_s"], config["threads"],
                version, config["presolve_configuration"], config["warm_start"], "perf_*.json",
                config["legacy_max_hour_check_deferral_days"], config["lp_relaxation"],
                config["methods"], False, checkpoint_path=checkpoint,
            )
            rows = audit_batch(output, original, args.executable, version)
        record["output"] = str(output.relative_to(ROOT))
        record["audit"] = "pass"
        record["summary"] = summarize(rows)
        if name == "uniform_multiseed10_20261021":
            text = render_ten_seed(rows, args.tag, version)
            tex_path = output.with_suffix(".tex")
            tex_path.write_text(text, encoding="ascii")
        atomic_json(report_path, report)
        print(f"AUDITED {name}: {len(rows)} rows", flush=True)
    print(f"CPLEX REFRESH COMPLETE: {report_path}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Completed solves are checkpointed; repeat the same command to resume.", file=sys.stderr)
        sys.exit(130)
