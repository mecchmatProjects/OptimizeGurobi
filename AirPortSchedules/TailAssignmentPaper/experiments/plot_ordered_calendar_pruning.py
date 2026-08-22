"""Plot calendar-pruning gains for the ordered ABCD formulation.

Reads paired pruning-on/off benchmark CSVs and writes a two-panel figure with
solver CPU and wall-time gains by planning horizon. Positive values mean that
pruning is faster.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt



def read_rows(path: Path) -> dict[int, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {int(row["H"]): row for row in csv.DictReader(handle)}



def gain(off: str, on: str) -> float:
    return 100.0 * (float(off) - float(on)) / float(off)



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--on",
        default="results/tables/ordered_calendar_pruning_on_cplex.csv",
        help="Benchmark CSV with calendar pruning enabled.",
    )
    parser.add_argument(
        "--off",
        default="results/tables/ordered_calendar_pruning_off_cplex.csv",
        help="Benchmark CSV with calendar pruning disabled.",
    )
    parser.add_argument("--output", default="paper/figures/ordered_calendar_pruning_gains.png")
    args = parser.parse_args()

    on_rows = read_rows(Path(args.on))
    off_rows = read_rows(Path(args.off))
    horizons = sorted(set(on_rows) & set(off_rows))
    horizons = [
        horizon
        for horizon in horizons
        if on_rows[horizon]["status"] == "optimal"
        and off_rows[horizon]["status"] == "optimal"
    ]
    if not horizons:
        raise ValueError("No horizon has optimal results in both benchmark files")

    cpu_gains = [gain(off_rows[h]["cpu_s"], on_rows[h]["cpu_s"]) for h in horizons]
    wall_gains = [gain(off_rows[h]["wall_s"], on_rows[h]["wall_s"]) for h in horizons]

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.8), sharex=True, constrained_layout=True)
    series = ((axes[0], cpu_gains, "CPU-time gain (%)"), (axes[1], wall_gains, "Wall-time gain (%)"))
    for axis, values, ylabel in series:
        axis.axhline(0.0, color="#6b7280", linewidth=0.9)
        axis.plot(
            horizons,
            values,
            color="#0f766e",
            marker="o",
            linewidth=2,
            markersize=5,
        )
        axis.set_xlabel("Planning horizon h (days)")
        axis.set_ylabel(ylabel)
        axis.grid(True, alpha=0.25)

    fig.suptitle("Calendar-candidate pruning gain")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220)
    plt.close(fig)
    print(f"Wrote calendar-pruning gain plot to {output.resolve()}")


if __name__ == "__main__":
    main()
