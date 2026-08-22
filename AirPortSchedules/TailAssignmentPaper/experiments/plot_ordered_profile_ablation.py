"""Plot ordered profile ablation gains by horizon and solver.

Positive gain means clique+tight is faster than pairwise+coarse.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt

COLORS = {"HiGHS": "#155e75", "CPLEX": "#b45309"}
MARKERS = {"HiGHS": "o", "CPLEX": "s"}


def read_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def as_h_map(rows):
    return {int(row["H"]): row for row in rows}


def gains(clique_rows, pairwise_rows, metric):
    c_map = as_h_map(clique_rows)
    p_map = as_h_map(pairwise_rows)
    horizons = sorted(set(c_map) & set(p_map))
    values = []
    for h in horizons:
        c_val = float(c_map[h][metric])
        p_val = float(p_map[h][metric])
        gain = ((p_val - c_val) / p_val * 100.0) if p_val else 0.0
        values.append(gain)
    return horizons, values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--highs-clique", default="results/tables/ordered_ablation_clique_tight.csv")
    parser.add_argument("--highs-pairwise", default="results/tables/ordered_ablation_pairwise_coarse.csv")
    parser.add_argument("--cplex-clique", default="results/tables/ordered_ablation_clique_tight_cplex.csv")
    parser.add_argument("--cplex-pairwise", default="results/tables/ordered_ablation_pairwise_coarse_cplex.csv")
    parser.add_argument("--output", default="paper/figures/ordered_profile_ablation_gains.png")
    args = parser.parse_args()

    highs_c = read_rows(Path(args.highs_clique))
    highs_p = read_rows(Path(args.highs_pairwise))
    cplex_c = read_rows(Path(args.cplex_clique))
    cplex_p = read_rows(Path(args.cplex_pairwise))

    h_horizons, h_build = gains(highs_c, highs_p, "build_s")
    _, h_wall = gains(highs_c, highs_p, "wall_s")
    c_horizons, c_build = gains(cplex_c, cplex_p, "build_s")
    _, c_wall = gains(cplex_c, cplex_p, "wall_s")

    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.4), constrained_layout=True)

    # Build gain subplot
    ax = axes[0]
    ax.axhline(0.0, color="#6b7280", linewidth=1, linestyle="--")
    ax.plot(h_horizons, h_build, marker=MARKERS["HiGHS"], color=COLORS["HiGHS"], linewidth=2, label="HiGHS")
    ax.plot(c_horizons, c_build, marker=MARKERS["CPLEX"], color=COLORS["CPLEX"], linewidth=2, label="CPLEX")
    ax.set_title("Build-time gain")
    ax.set_xlabel("Planning horizon h (days)")
    ax.set_ylabel("Gain (%)")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)

    # Wall gain subplot
    ax = axes[1]
    ax.axhline(0.0, color="#6b7280", linewidth=1, linestyle="--")
    ax.plot(h_horizons, h_wall, marker=MARKERS["HiGHS"], color=COLORS["HiGHS"], linewidth=2, label="HiGHS")
    ax.plot(c_horizons, c_wall, marker=MARKERS["CPLEX"], color=COLORS["CPLEX"], linewidth=2, label="CPLEX")
    ax.set_title("Solve wall-time gain")
    ax.set_xlabel("Planning horizon h (days)")
    ax.set_ylabel("Gain (%)")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=220)
    plt.close(fig)
    print(f"Wrote ablation gain plot to {out_path.resolve()}")


if __name__ == "__main__":
    main()
