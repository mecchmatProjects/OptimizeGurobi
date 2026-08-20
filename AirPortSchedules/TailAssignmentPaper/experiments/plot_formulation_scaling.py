"""Plot formulation size and solve-time scaling from comparison CSV results.

The runtime plot deliberately retains non-optimal statuses.  A time-limited
MILP solve is evidence about the computational budget, but is not evidence of
an optimal objective; status is therefore shown in the legend and in the
output summary rather than silently discarded.
"""

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


FORMULATION_LABELS = {
    "legacy_endpoint_split": "Legacy endpoint-split",
    "event_exact_state": "Event-based exact-state",
}
FORMULATION_STYLES = {
    "legacy_endpoint_split": {"color": "#155e75", "marker": "o"},
    "event_exact_state": {"color": "#b45309", "marker": "s"},
}


def read_rows(path: Path) -> list[dict[str, object]]:
    """Read numeric comparison rows while preserving solver status."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = []
        for row in csv.DictReader(handle):
            horizon_match = re.search(r"_h=(\d+)_", row["stem"])
            horizon = int(horizon_match.group(1)) if horizon_match else int(row["H"])
            rows.append(
                {
                    **row,
                    "H": horizon,
                    "vars": int(row["vars"]),
                    "constraints": int(row["constraints"]),
                    "wall_s": float(row["wall_s"]) if row["wall_s"] else None,
                    "status": row["status"],
                }
            )
    return rows


def plot_metric(rows, metric: str, ylabel: str, output: Path, title: str) -> None:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["formulation"]].append(row)

    figure, axis = plt.subplots(figsize=(7.0, 4.4), constrained_layout=True)
    for formulation, label in FORMULATION_LABELS.items():
        series = sorted(grouped[formulation], key=lambda row: row["H"])
        if not series:
            continue
        style = FORMULATION_STYLES[formulation]
        values = [row[metric] for row in series]
        axis.plot(
            [row["H"] for row in series],
            values,
            linewidth=2,
            label=label,
            color=style["color"],
            marker=style["marker"],
        )
        if metric == "wall_s":
            for row in series:
                if row["status"] != "optimal":
                    axis.annotate(
                        row["status"],
                        (row["H"], row[metric]),
                        textcoords="offset points",
                        xytext=(4, 5),
                        fontsize=7,
                    )

    axis.set_xlabel("Planning horizon $h$ (days)")
    axis.set_ylabel(ylabel)
    axis.set_title(title)
    axis.grid(True, which="both", alpha=0.25)
    axis.legend(frameon=False)
    if metric in {"vars", "constraints", "wall_s"}:
        axis.set_yscale("log")
    figure.savefig(output, dpi=220)
    plt.close(figure)


def plot_relative_factors(rows, output: Path) -> None:
    """Plot event/legacy ratios for construction and solved wall time."""
    grouped = defaultdict(dict)
    for row in rows:
        grouped[row["H"]][row["formulation"]] = row

    horizons = sorted(grouped)
    build_ratios = []
    wall_ratios = []
    for horizon in horizons:
        legacy = grouped[horizon]["legacy_endpoint_split"]
        event = grouped[horizon]["event_exact_state"]
        build_ratios.append(float(event["build_s"]) / float(legacy["build_s"]))
        wall_ratios.append(float(event["wall_s"]) / float(legacy["wall_s"]))

    figure, axis = plt.subplots(figsize=(7.0, 4.4), constrained_layout=True)
    axis.axhline(1.0, color="#444444", linewidth=1, linestyle="--")
    axis.plot(horizons, build_ratios, marker="o", linewidth=2,
              color="#155e75", label="Build-time ratio")
    axis.plot(horizons, wall_ratios, marker="s", linewidth=2,
              color="#b45309", label="Solve wall-time ratio")
    axis.set_xlabel("Planning horizon $h$ (days)")
    axis.set_ylabel("Event-based / legacy time")
    axis.set_title("Relative event-based time (ratio 1 = equal)")
    axis.grid(True, alpha=0.25)
    axis.legend(frameon=False)
    figure.savefig(output, dpi=220)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="results/tables/formulation_correctness_after_optimization.csv",
        help="Comparison CSV produced by compare_formulations.py.",
    )
    parser.add_argument(
        "--output-dir",
        default="paper/figures",
        help="Directory for generated PNG figures.",
    )
    args = parser.parse_args()

    rows = read_rows(Path(args.input))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_metric(
        rows,
        "wall_s",
        "Wall-clock solve time (s)",
        output_dir / "formulation_runtime_vs_horizon.png",
        "Solve-time scaling on the expanded feasible-instance grid",
    )
    plot_metric(
        rows,
        "vars",
        "Active variables",
        output_dir / "formulation_variables_vs_horizon.png",
        "Model-size scaling on the expanded feasible-instance grid",
    )
    plot_metric(
        rows,
        "constraints",
        "Active constraints",
        output_dir / "formulation_constraints_vs_horizon.png",
        "Constraint scaling on the expanded feasible-instance grid",
    )
    plot_relative_factors(
        rows,
        output_dir / "formulation_relative_time_ratio.png",
    )
    print(f"Wrote plots to {output_dir.resolve()}")


if __name__ == "__main__":
    main()