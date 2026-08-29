"""Plot A-only CPU time versus fleet size."""

from __future__ import annotations

import argparse
import csv
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="results/tables/formulation_a_fleet_four_latest.csv",
    )
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
