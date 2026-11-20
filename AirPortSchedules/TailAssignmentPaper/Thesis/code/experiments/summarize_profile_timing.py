"""Summarize paired CPLEX profile timings without hiding replay failures."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

from scipy.stats import wilcoxon

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


def read_rows(directory: Path, suffix: str, profiles=PROFILES) -> tuple[dict, dict[str, dict]]:
    all_rows = {}
    input_hashes = {}
    protocols = {}
    for profile in profiles:
        path = directory / f"profile_timing_{profile}_cplex129_{suffix}.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        metadata_path = path.with_suffix(".metadata.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        protocols[profile] = tuple(
            metadata[key]
            for key in ("solver", "solver_version", "threads", "time_limit_s", "a_calendar_dmax")
        )
        keyed = {
            (int(row["P"]), int(row["H"]), row["stem"], int(row.get("repeat", 0) or 0)): row
            for row in rows
        }
        if len(keyed) != len(rows):
            raise ValueError(f"duplicate profile/input rows in {path}")
        all_rows[profile] = keyed
        input_hashes[profile] = {key: row["input_sha256"] for key, row in keyed.items()}

    if len(set(protocols.values())) != 1:
        raise ValueError(f"solver protocol differs across profile runs: {protocols}")
    reference_keys = set(all_rows["corrected_a_interval"])
    reference_hashes = input_hashes["corrected_a_interval"]
    for profile in profiles:
        if set(all_rows[profile]) != reference_keys:
            raise ValueError(f"input grid mismatch for profile {profile}")
        if input_hashes[profile] != reference_hashes:
            raise ValueError(f"input hash mismatch for profile {profile}")
    return all_rows, reference_hashes


def holm_adjust(rows):
    adjusted = {}
    ordered = sorted(enumerate(float(row["wilcoxon_p_two_sided"]) for row in rows), key=lambda item: item[1])
    running = 0.0
    for rank, (index, p_value) in enumerate(ordered):
        candidate = min(1.0, p_value * (len(ordered) - rank))
        running = max(running, candidate)
        adjusted[index] = running
    return adjusted


def summarize(directory: Path, suffix: str, output: Path, profiles=PROFILES) -> tuple[Path, Path]:
    rows_by_profile, input_hashes = read_rows(directory, suffix, profiles)
    groups = sorted({(key[0], key[1]) for key in input_hashes})
    summary_rows = []
    paired_rows = []

    for fleet, horizon in groups:
        keys = sorted(
            key for key in input_hashes if key[:2] == (fleet, horizon)
        )
        baseline = rows_by_profile["corrected_a_interval"]
        for profile in profiles:
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
            log_ratios = [math.log(ratio) for ratio in ratios]
            p_value = wilcoxon(log_ratios, zero_method="wilcox", alternative="two-sided").pvalue
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
                "median_wall_ratio": statistics.median(ratios) if ratios else "",
                "wilcoxon_p_two_sided": p_value if ratios else "",
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
        option_log_ratios = [math.log(ratio) for ratio in option_ratios]
        option_p_value = wilcoxon(
            option_log_ratios, zero_method="wilcox", alternative="two-sided"
        ).pvalue
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
            "median_wall_ratio": statistics.median(option_ratios) if option_ratios else "",
            "wilcoxon_p_two_sided": option_p_value if option_ratios else "",
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

    comparison_profiles = sorted({row["profile"] for row in paired_rows})
    for comparison in comparison_profiles:
        subset = [row for row in paired_rows if row["profile"] == comparison]
        adjusted = holm_adjust(subset)
        for index, row in enumerate(subset):
            row["holm_p_four_cells"] = adjusted[index]

    output.parent.mkdir(parents=True, exist_ok=True)
    paired_output = output.with_name(output.stem + "_paired.csv")
    for path, rows in ((output, summary_rows), (paired_output, paired_rows)):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    metadata = {
        "profiles": list(profiles),
        "reference_profile": "corrected_a_interval",
        "input_hashes": {
            f"{key[2]}_repeat_{key[3]}": value
            for key, value in sorted(input_hashes.items())
        },
        "source_csv_hashes": {
            profile: digest(directory / f"profile_timing_{profile}_cplex129_{suffix}.csv")
            for profile in profiles
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
    parser.add_argument("--profiles", nargs="+", choices=PROFILES, default=list(PROFILES))
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "tables" / "profile_timing_summary_20261118.csv",
    )
    args = parser.parse_args()
    summary, paired = summarize(args.directory, args.suffix, args.output, tuple(args.profiles))
    print(f"Wrote per-profile timing summary: {summary}")
    print(f"Wrote paired comparison to corrected profile: {paired}")


if __name__ == "__main__":
    main()
