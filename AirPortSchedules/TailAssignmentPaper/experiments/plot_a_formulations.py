"""Plot A-only formulation timing versus horizon.

Produces wall-time and CPU-time horizon plots for legacy vs ordered A-only
formulations from compare_a_formulations.py output.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

LABELS = {
    "legacy_a": "Legacy (A only)",
    "ordered_a_event": "Ordered event (A only)",
}
COLORS = {"legacy_a": "#155e75", "ordered_a_event": "#b45309"}
MARKERS = {"legacy_a": "o", "ordered_a_event": "s"}


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
    parser.add_argument("--input", default="results/tables/formulation_a_comparison_latest.csv")
    parser.add_argument("--output-dir", default="paper/figures")
    args = parser.parse_args()

    rows = read_rows(Path(args.input))
    out = Path(args.output_dir)
    plot_metric(rows, "wall_s", "Solve wall time (s)", out / "ordered_a_wall_vs_horizon.png")
    plot_metric(rows, "cpu_s", "Solve CPU time (s)", out / "ordered_a_cpu_vs_horizon.png")
    print(f"Wrote A-only timing plots to {out.resolve()}")


if __name__ == "__main__":
    main()
