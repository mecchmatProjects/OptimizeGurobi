"""Plot ordered no-w versus legacy versus event ABCD fleet scaling."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

LABELS = {
    "legacy": "Legacy day-indexed",
    "ordered_abcd": "Ordered event (no w)",
    "event_exact": "Standalone event",
}
COLORS = {"legacy": "#155e75", "ordered_abcd": "#b45309", "event_exact": "#166534"}
MARKERS = {"legacy": "o", "ordered_abcd": "s", "event_exact": "^"}


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


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
            marker=MARKERS[formulation],
            color=COLORS[formulation],
            label=LABELS[formulation],
        )
    axis.set_xlabel("Number of aircraft $|P|$")
    axis.set_ylabel(ylabel)
    axis.grid(True, alpha=0.25)
    axis.legend(frameon=False)
    figure.savefig(output, dpi=220)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="results/tables/formulation_abcd_fleet_scaling_repro.csv")
    parser.add_argument("--output-dir", default="paper/figures")
    args = parser.parse_args()
    rows = read_rows(Path(args.input))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_metric(rows, "vars", "Active variables", output_dir / "ordered_abcd_variables_vs_fleet.png")
    plot_metric(rows, "constraints", "Active constraints", output_dir / "ordered_abcd_constraints_vs_fleet.png")
    plot_metric(rows, "build_s", "Model-build time (s)", output_dir / "ordered_abcd_build_vs_fleet.png")
    plot_metric(rows, "wall_s", "Solve wall time (s)", output_dir / "ordered_abcd_wall_vs_fleet.png")
    plot_metric(rows, "cpu_s", "Solve CPU time (s)", output_dir / "ordered_abcd_cpu_vs_fleet.png")
    print(f"Wrote ordered hierarchy plots to {output_dir.resolve()}")


if __name__ == "__main__":
    main()
