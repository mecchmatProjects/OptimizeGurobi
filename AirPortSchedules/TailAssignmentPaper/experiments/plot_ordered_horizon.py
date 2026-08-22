"""Plot ordered no-w versus legacy versus event ABCD horizon scaling."""

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


def read_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def plot_metric(rows, metric, ylabel, output: Path):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["formulation"]].append(row)

    figure, axis = plt.subplots(figsize=(7.0, 4.4), constrained_layout=True)
    plotted_any = False
    for formulation in LABELS:
        series = sorted(grouped[formulation], key=lambda row: int(row["H"]))
        x_values = []
        y_values = []
        for row in series:
            value = row.get(metric, "")
            if value in ("", None):
                continue
            x_values.append(int(row["H"]))
            y_values.append(float(value))
        if not x_values:
            continue
        axis.plot(
            x_values,
            y_values,
            linewidth=2,
            marker=MARKERS[formulation],
            color=COLORS[formulation],
            label=LABELS[formulation],
        )
        plotted_any = True

    if not plotted_any:
        plt.close(figure)
        return False

    axis.set_xlabel("Planning horizon $h$ (days)")
    axis.set_ylabel(ylabel)
    axis.grid(True, alpha=0.25)
    axis.legend(frameon=False)
    figure.savefig(output, dpi=220)
    plt.close(figure)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="results/tables/formulation_abcd_horizon_scaling_latest.csv")
    parser.add_argument("--output-dir", default="paper/figures")
    args = parser.parse_args()

    rows = read_rows(Path(args.input))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    plot_metric(rows, "vars", "Active variables", output_dir / "ordered_abcd_variables_vs_horizon.png")
    plot_metric(rows, "constraints", "Active constraints", output_dir / "ordered_abcd_constraints_vs_horizon.png")
    plot_metric(rows, "build_s", "Model-build time (s)", output_dir / "ordered_abcd_build_vs_horizon.png")
    plot_metric(rows, "wall_s", "Solve wall time (s)", output_dir / "ordered_abcd_wall_vs_horizon.png")
    if not plot_metric(rows, "cpu_s", "Solve CPU time (s)", output_dir / "ordered_abcd_cpu_vs_horizon.png"):
        print("Skipped CPU plot: no numeric cpu_s values in input CSV")

    print(f"Wrote ordered horizon plots to {output_dir.resolve()}")


if __name__ == "__main__":
    main()
