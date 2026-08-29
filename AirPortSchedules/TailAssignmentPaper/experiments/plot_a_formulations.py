"""Plot A-only formulation timing versus horizon.

Produces wall-time and CPU-time horizon plots for the four A-only formulations
from compare_a_formulations.py output.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

LABELS = {
    "legacy_paper_c13": "Legacy paper row",
    "legacy_endpoint_split": "Legacy endpoint split",
    "legacy_corrected": "Legacy corrected",
    "event_based": "Event-based",
}
COLORS = {
    "legacy_paper_c13": "#7f1d1d",
    "legacy_endpoint_split": "#155e75",
    "legacy_corrected": "#166534",
    "event_based": "#b45309",
}
MARKERS = {
    "legacy_paper_c13": "v",
    "legacy_endpoint_split": "o",
    "legacy_corrected": "^",
    "event_based": "s",
}


def read_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def plot_metric(rows, metric, ylabel, output: Path):
    grouped = defaultdict(list)
    for row in rows:
        if row.get("status") != "optimal":
            continue
        if row.get("formulation") not in LABELS:
            continue
        value = row.get(metric, "")
        if value in ("", None):
            continue
        grouped[row["formulation"]].append(row)

    fig, ax = plt.subplots(figsize=(7.0, 4.2), constrained_layout=True)
    for formulation in LABELS:
        series = sorted(grouped[formulation], key=lambda r: int(r["H"]))
        if not series:
            continue
        ax.plot(
            [int(r["H"]) for r in series],
            [float(r[metric]) for r in series],
            color=COLORS[formulation],
            marker=MARKERS[formulation],
            linewidth=2,
            label=LABELS[formulation],
        )
    ax.set_xlabel("Planning horizon h (days)")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="results/tables/four_method_suite_extended.csv",
    )
    parser.add_argument("--fleet-size", type=int, default=20)
    parser.add_argument("--output-dir", default="paper/figures")
    args = parser.parse_args()

    rows = [
        row for row in read_rows(Path(args.input))
        if row.get("case", "").startswith("perf_")
        and int(row["P"]) == args.fleet_size
    ]
    for row in rows:
        match = re.match(r"perf_p=\d+_h=(\d+)$", row["case"])
        if match:
            row["H"] = match.group(1)
    out = Path(args.output_dir)
    suffix = f"_extended_p{args.fleet_size}"
    plot_metric(rows, "wall_s", "Solve wall time (s)", out / f"ordered_a_wall_vs_horizon{suffix}.png")
    plot_metric(rows, "cpu_s", "Solve CPU time (s)", out / f"ordered_a_cpu_vs_horizon{suffix}.png")
    print(f"Wrote A-only timing plots to {out.resolve()}")


if __name__ == "__main__":
    main()
