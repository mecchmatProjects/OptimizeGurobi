"""Plot the paired profile timing study with replay status visible."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
PROFILES = (
    "khaled_printed",
    "endpoint_split",
    "corrected_a_interval",
    "option_a",
    "option_b",
)
LABELS = {
    "khaled_printed": "Khaled",
    "endpoint_split": "Split",
    "corrected_a_interval": "Corrected",
    "option_a": "Option A",
    "option_b": "Option B",
}
COLORS = {
    "khaled_printed": "#355070",
    "endpoint_split": "#6d597a",
    "corrected_a_interval": "#2a9d8f",
    "option_a": "#e9c46a",
    "option_b": "#f4a261",
}
CELL_MARKERS = {(3, 4): "o", (3, 5): "s", (5, 4): "^", (5, 5): "D"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_profile_rows(directory: Path, suffix: str, profiles=PROFILES) -> dict[str, dict[str, dict]]:
    by_profile = {}
    for profile in profiles:
        path = directory / f"profile_timing_{profile}_cplex129_{suffix}.csv"
        metadata_path = path.with_suffix(".metadata.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if sha256(path) != metadata["result_csv_sha256"]:
            raise ValueError(f"result CSV hash mismatch: {path}")
        if metadata["profile"] != profile:
            raise ValueError(f"profile metadata mismatch: {path}")
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        keyed = {
            f"{row['stem']}_repeat_{int(row.get('repeat', 0) or 0)}": row
            for row in rows
        }
        if len(keyed) != len(rows):
            raise ValueError(f"duplicate instances in {path}")
        by_profile[profile] = keyed

    reference = by_profile[next(iter(by_profile))]
    for profile, rows in by_profile.items():
        if set(rows) != set(reference):
            raise ValueError(f"instance set mismatch for {profile}")
        if any(rows[stem]["input_sha256"] != reference[stem]["input_sha256"] for stem in reference):
            raise ValueError(f"input hash mismatch for {profile}")
    return by_profile


def plot_profile_distributions(by_profile, output: Path) -> None:
    profiles = tuple(by_profile)
    cells = sorted({(int(row["P"]), int(row["H"])) for row in by_profile[profiles[0]].values()})
    figure, axes = plt.subplots(2, 2, figsize=(10.5, 7.2), sharey=True, constrained_layout=True)
    rng = random.Random(18042018)
    for axis, (fleet, horizon) in zip(axes.flat, cells):
        pass_counts = []
        for position, profile in enumerate(profiles):
            rows = [
                row for row in by_profile[profile].values()
                if int(row["P"]) == fleet and int(row["H"]) == horizon
            ]
            passed = [row for row in rows if row["replay_status"] == "pass"]
            failed = [row for row in rows if row["replay_status"] != "pass"]
            pass_counts.append(len(passed))
            pass_x = [position + rng.uniform(-0.09, 0.09) for _ in passed]
            fail_x = [position + rng.uniform(-0.09, 0.09) for _ in failed]
            axis.scatter(
                pass_x,
                [float(row["wall_s"]) for row in passed],
                s=24,
                color=COLORS[profile],
                alpha=0.82,
                marker="o",
                zorder=2,
            )
            axis.scatter(
                fail_x,
                [float(row["wall_s"]) for row in failed],
                s=42,
                color="#c0392b",
                alpha=0.9,
                marker="x",
                zorder=3,
            )
            times = [float(row["wall_s"]) for row in rows]
            mean = sum(times) / len(times)
            sd = (sum((value - mean) ** 2 for value in times) / (len(times) - 1)) ** 0.5
            axis.errorbar(
                position,
                mean,
                yerr=sd,
                fmt="D",
                markersize=5,
                color="#202020",
                markerfacecolor="white",
                capsize=3,
                linewidth=1.1,
                zorder=4,
            )
        axis.set_title(f"{fleet} aircraft, {horizon} days", fontsize=10)
        axis.set_xticks(range(len(profiles)))
        axis.set_xticklabels(
            [f"{LABELS[name]}\n{count} pass" for name, count in zip(profiles, pass_counts)],
            fontsize=8,
        )
        axis.set_xlim(-0.5, len(profiles) - 0.5)
        axis.grid(axis="y", color="#d9d9d9", linewidth=0.7)
        axis.set_axisbelow(True)
    for axis in axes[:, 0]:
        axis.set_ylabel("Solver wall time (s)")
    handles = [
        Line2D([0], [0], marker="o", linestyle="", color=COLORS[profile], label=LABELS[profile])
        for profile in profiles
    ]
    handles.append(Line2D([0], [0], marker="x", linestyle="", color="#c0392b", label="Replay failed"))
    handles.append(Line2D([0], [0], marker="D", linestyle="", color="#202020",
                          markerfacecolor="white", label="Mean $\\pm$ SD"))
    figure.legend(handles=handles, loc="outside lower center", ncol=4, frameon=False)
    figure.suptitle("A-only profile runtimes on matched certified inputs", fontsize=12)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=300, bbox_inches="tight")
    figure.savefig(output.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(figure)


def plot_option_pair(by_profile, output: Path) -> None:
    cells = sorted({(int(row["P"]), int(row["H"])) for row in by_profile["option_a"].values()})
    figure, axes = plt.subplots(2, 2, figsize=(7.8, 7.0), constrained_layout=True)
    for axis, cell in zip(axes.flat, cells):
        fleet, horizon = cell
        pairs = []
        for stem, row_a in by_profile["option_a"].items():
            row_b = by_profile["option_b"][stem]
            if (int(row_a["P"]), int(row_a["H"])) == cell:
                pairs.append((row_a, row_b))
        x_values = [float(left["wall_s"]) for left, _right in pairs]
        y_values = [float(right["wall_s"]) for _left, right in pairs]
        lower = min(x_values + y_values) * 0.9
        upper = max(x_values + y_values) * 1.1
        axis.plot([lower, upper], [lower, upper], color="#777777", linestyle="--", linewidth=1)
        axis.scatter(
            x_values,
            y_values,
            marker=CELL_MARKERS[cell],
            s=34,
            color="#2a9d8f",
            alpha=0.8,
            edgecolor="white",
            linewidth=0.4,
        )
        axis.set_xlim(lower, upper)
        axis.set_ylim(lower, upper)
        axis.set_aspect("equal", adjustable="box")
        axis.set_title(f"{fleet} aircraft, {horizon} days", fontsize=10)
        axis.set_xlabel("Option A wall time (s)")
        axis.set_ylabel("Option B wall time (s)")
        axis.grid(color="#e0e0e0", linewidth=0.6)
    figure.suptitle("Paired Option A/B runtimes (all objectives equal; all replays pass)", fontsize=11)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=300, bbox_inches="tight")
    figure.savefig(output.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "results" / "tables")
    parser.add_argument("--suffix", default="20261118")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "paper" / "figures")
    parser.add_argument("--profiles", nargs="+", choices=PROFILES, default=list(PROFILES))
    parser.add_argument("--option-pair-only", action="store_true")
    args = parser.parse_args()
    selected = set(args.profiles)
    rows = load_profile_rows(args.directory, args.suffix, tuple(args.profiles))
    if not args.option_pair_only:
        plot_profile_distributions(rows, args.output_dir / f"profile_timing_{args.suffix}.png")
    if {"option_a", "option_b"} <= selected:
        plot_option_pair(rows, args.output_dir / f"option_a_b_paired_timing_{args.suffix}.png")
    elif args.option_pair_only:
        parser.error("--option-pair-only requires --profiles option_a option_b")
    print(f"Wrote timing plots to {args.output_dir}")


if __name__ == "__main__":
    main()