"""Plot four A-only formulations against fleet size."""

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
LINESTYLES = {
    "legacy_paper_c13": "--",
    "legacy_endpoint_split": "-",
    "legacy_corrected": "-",
    "event_based": "-",
}
MARKERS = {
    "legacy_paper_c13": "v",
    "legacy_endpoint_split": "o",
    "legacy_corrected": "^",
    "event_based": "s",
}


def read_rows(path, horizon):
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    expected = set(LABELS)
    observed = {row["formulation"] for row in rows}
    if observed != expected:
        raise ValueError(
            f"Expected formulations {sorted(expected)}, found {sorted(observed)}"
        )
    rows = [
        row for row in rows
        if (match := re.match(r"perf_p=\d+_h=(\d+)$", row["case"]))
        and int(match.group(1)) == horizon
    ]
    fleet_sizes = {int(row["P"]) for row in rows}
    if fleet_sizes != {10, 20, 30, 40, 50}:
        raise ValueError(f"Expected fleet sizes {{10, 20, 30, 40, 50}}, found {fleet_sizes}")
    return rows


def plot_metric(rows, metric, ylabel, output):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["formulation"]].append(row)
    figure, axis = plt.subplots(figsize=(7.0, 4.4), constrained_layout=True)
    for formulation in LABELS:
        series = sorted(grouped[formulation], key=lambda row: int(row["P"]))
        axis.plot(
            [int(row["P"]) for row in series],
            [float(row[metric]) for row in series],
            linewidth=2,
            linestyle=LINESTYLES[formulation],
            marker=MARKERS[formulation],
            markerfacecolor="white" if formulation == "legacy_paper_c13" else COLORS[formulation],
            markeredgewidth=1.5,
            color=COLORS[formulation],
            label=LABELS[formulation],
            zorder=4 if formulation == "legacy_paper_c13" else 3,
        )
    axis.set_xlabel("Number of aircraft $|P|$")
    axis.set_ylabel(ylabel)
    axis.grid(True, alpha=0.25)
    axis.legend(frameon=False)
    figure.savefig(output, dpi=220)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="results/tables/four_method_suite_extended.csv")
    parser.add_argument("--horizon", type=int, default=30)
    parser.add_argument("--output-dir", default="paper/figures")
    args = parser.parse_args()
    rows = read_rows(Path(args.input), args.horizon)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_extended_h{args.horizon}"
    plot_metric(rows, "vars", "Active variables", output_dir / f"a_variables_vs_fleet{suffix}.png")
    plot_metric(rows, "constraints", "Active constraints", output_dir / f"a_constraints_vs_fleet{suffix}.png")
    plot_metric(rows, "build_s", "Model-build time (s)", output_dir / f"a_build_vs_fleet{suffix}.png")
    plot_metric(rows, "wall_s", "Solve wall time (s)", output_dir / f"a_wall_vs_fleet{suffix}.png")
    plot_metric(rows, "cpu_s", "Solve CPU time (s)", output_dir / f"a_cpu_vs_fleet{suffix}.png")
    print(f"Wrote A-only fleet plots to {output_dir.resolve()}")


if __name__ == "__main__":
    main()
