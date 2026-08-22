"""Plot A-only CPU time versus fleet size."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

LABELS = {
    "legacy_a": "Legacy (A only)",
    "compact_a_event": "Compact event (A only)",
    "ordered_a_event": "Ordered event (A only)",
}
COLORS = {
    "legacy_a": "#155e75",
    "compact_a_event": "#6b7280",
    "ordered_a_event": "#b45309",
}
MARKERS = {"legacy_a": "o", "compact_a_event": "^", "ordered_a_event": "s"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="results/tables/formulation_a_fleet_scaling_latest.csv")
    parser.add_argument("--output", default="paper/figures/ordered_a_cpu_vs_fleet.png")
    args = parser.parse_args()

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with Path(args.input).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["status"] == "optimal":
                grouped[row["formulation"]].append(row)

    figure, axis = plt.subplots(figsize=(7.0, 4.2), constrained_layout=True)
    for formulation, label in LABELS.items():
        series = sorted(grouped[formulation], key=lambda row: int(row["P"]))
        if not series:
            continue
        axis.plot(
            [int(row["P"]) for row in series],
            [float(row["cpu_s"]) for row in series],
            color=COLORS[formulation],
            marker=MARKERS[formulation],
            linewidth=2,
            label=label,
        )
    axis.set_xlabel("Number of aircraft $|P|$")
    axis.set_ylabel("Solve CPU time (s)")
    axis.grid(True, alpha=0.25)
    axis.legend(frameon=False)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=220)
    plt.close(figure)
    print(f"Wrote A-only fleet CPU plot to {output.resolve()}")


if __name__ == "__main__":
    main()
