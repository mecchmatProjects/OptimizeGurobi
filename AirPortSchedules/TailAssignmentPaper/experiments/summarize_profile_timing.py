"""Summarize paired CPLEX profile timings without hiding replay failures."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = (
    "khaled_printed",
    "endpoint_split",
    "corrected_a_interval",
    "option_a",
    "option_b",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(directory: Path, suffix: str) -> tuple[dict, dict[str, dict]]:
    all_rows = {}
    input_hashes = {}
    protocols = {}
    for profile in PROFILES:
        path = directory / f"profile_timing_{profile}_cplex129_{suffix}.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        metadata_path = path.with_suffix(".metadata.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        protocols[profile] = tuple(
            metadata[key]
            for key in ("solver", "solver_version", "threads", "time_limit_s", "a_calendar_dmax")
        )
        keyed = {(int(row["P"]), int(row["H"]), row["stem"]): row for row in rows}
        if len(keyed) != len(rows):
            raise ValueError(f"duplicate profile/input rows in {path}")
        all_rows[profile] = keyed
        input_hashes[profile] = {key: row["input_sha256"] for key, row in keyed.items()}

    if len(set(protocols.values())) != 1:
        raise ValueError(f"solver protocol differs across profile runs: {protocols}")
    reference_keys = set(all_rows["corrected_a_interval"])
    reference_hashes = input_hashes["corrected_a_interval"]
    for profile in PROFILES:
        if set(all_rows[profile]) != reference_keys:
            raise ValueError(f"input grid mismatch for profile {profile}")
        if input_hashes[profile] != reference_hashes:
            raise ValueError(f"input hash mismatch for profile {profile}")
    return all_rows, reference_hashes


def summarize(directory: Path, suffix: str, output: Path) -> tuple[Path, Path]:
    rows_by_profile, input_hashes = read_rows(directory, suffix)
    groups = sorted({(key[0], key[1]) for key in input_hashes})
    summary_rows = []
    paired_rows = []

    for fleet, horizon in groups:
        keys = sorted(
            key for key in input_hashes if key[:2] == (fleet, horizon)
        )
        baseline = rows_by_profile["corrected_a_interval"]
        for profile in PROFILES:
            profile_rows = [rows_by_profile[profile][key] for key in keys]
            times = [float(row["wall_s"]) for row in profile_rows]
            summary_rows.append({
                "P": fleet,
                "H": horizon,
                "profile": profile,
                "runs": len(profile_rows),
                "optimal": sum(row["status"] == "optimal" for row in profile_rows),
                "replay_pass": sum(row["replay_status"] == "pass" for row in profile_rows),
                "replay_fail": sum(row["replay_status"] == "fail" for row in profile_rows),
                "unsupported": sum(row["status"] == "unsupported" for row in profile_rows),
                "mean_wall_s": statistics.mean(times),
                "sd_wall_s": statistics.stdev(times) if len(times) > 1 else 0.0,
                "median_wall_s": statistics.median(times),
            })

            if profile == "corrected_a_interval":
                continue
            paired = [
                (rows_by_profile[profile][key], baseline[key])
                for key in keys
                if rows_by_profile[profile][key]["status"] == "optimal"
                and baseline[key]["status"] == "optimal"
                and float(rows_by_profile[profile][key]["wall_s"]) > 0
                and float(baseline[key]["wall_s"]) > 0
            ]
            ratios = [float(left["wall_s"]) / float(right["wall_s"]) for left, right in paired]
            same_objective = sum(
                math.isclose(float(left["objective"]), float(right["objective"]), rel_tol=0, abs_tol=1e-5)
                for left, right in paired
            )
            paired_rows.append({
                "P": fleet,
                "H": horizon,
                "profile": profile,
                "baseline": "corrected_a_interval",
                "paired_optimal_n": len(paired),
                "same_objective_n": same_objective,
                "profile_faster_n": sum(ratio < 1 for ratio in ratios),
                "geomean_wall_ratio_profile_over_baseline": (
                    math.exp(statistics.mean(math.log(ratio) for ratio in ratios))
                    if ratios else ""
                ),
                "both_replay_pass_n": sum(
                    left["replay_status"] == right["replay_status"] == "pass"
                    for left, right in paired
                ),
                "paired_replay_failure_n": sum(
                    left["replay_status"] != "pass" or right["replay_status"] != "pass"
                    for left, right in paired
                ),
            })

        option_a = rows_by_profile["option_a"]
        option_b = rows_by_profile["option_b"]
        option_pairs = [
            (option_a[key], option_b[key])
            for key in keys
            if option_a[key]["status"] == "optimal"
            and option_b[key]["status"] == "optimal"
            and float(option_a[key]["wall_s"]) > 0
            and float(option_b[key]["wall_s"]) > 0
        ]
        option_ratios = [
            float(left["wall_s"]) / float(right["wall_s"])
            for left, right in option_pairs
        ]
        paired_rows.append({
            "P": fleet,
            "H": horizon,
            "profile": "option_a_vs_option_b",
            "baseline": "option_b",
            "paired_optimal_n": len(option_pairs),
            "same_objective_n": sum(
                math.isclose(float(left["objective"]), float(right["objective"]), rel_tol=0, abs_tol=1e-5)
                for left, right in option_pairs
            ),
            "profile_faster_n": sum(ratio < 1 for ratio in option_ratios),
            "geomean_wall_ratio_profile_over_baseline": (
                math.exp(statistics.mean(math.log(ratio) for ratio in option_ratios))
                if option_ratios else ""
            ),
            "both_replay_pass_n": sum(
                left["replay_status"] == right["replay_status"] == "pass"
                for left, right in option_pairs
            ),
            "paired_replay_failure_n": sum(
                left["replay_status"] != "pass" or right["replay_status"] != "pass"
                for left, right in option_pairs
            ),
        })

    output.parent.mkdir(parents=True, exist_ok=True)
    paired_output = output.with_name(output.stem + "_paired.csv")
    for path, rows in ((output, summary_rows), (paired_output, paired_rows)):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    metadata = {
        "profiles": list(PROFILES),
        "reference_profile": "corrected_a_interval",
        "input_hashes": {
            key[2]: value for key, value in sorted(input_hashes.items())
        },
        "source_csv_hashes": {
            profile: digest(directory / f"profile_timing_{profile}_cplex129_{suffix}.csv")
            for profile in PROFILES
        },
        "summary_csv_sha256": digest(output),
        "paired_csv_sha256": digest(paired_output),
        "interpretation": (
            "Descriptive paired solve timings. Objective parity is reported only for jointly optimal runs. "
            "Profiles with replay failures are not feasible-quality comparisons."
        ),
    }
    output.with_suffix(".metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return output, paired_output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "results" / "tables")
    parser.add_argument("--suffix", default="20261118")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "tables" / "profile_timing_summary_20261118.csv",
    )
    args = parser.parse_args()
    summary, paired = summarize(args.directory, args.suffix, args.output)
    print(f"Wrote per-profile timing summary: {summary}")
    print(f"Wrote paired comparison to corrected profile: {paired}")


if __name__ == "__main__":
    main()
