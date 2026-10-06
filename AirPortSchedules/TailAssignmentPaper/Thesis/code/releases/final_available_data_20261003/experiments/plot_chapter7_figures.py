"""Generate Chapter 7 performance-focused figures from tournament CSV data."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = ROOT / "paper" / "figures"

HEURISTIC_ORDER = [
    "greedy",
    "insertion",
    "greedy+insertion",
    "repair",
    "local_search",
    "dijkstra",
    "aco",
]
HEURISTIC_LABELS = ["Greedy", "Insertion", "G+I", "Repair", "Local search", "Dijkstra", "ACO"]
ALL_METHOD_ORDER = ["integrated_milp", "classical_milp"] + HEURISTIC_ORDER
ALL_METHOD_LABELS = ["Integrated\nMILP", "Classical\nMILP"] + HEURISTIC_LABELS

METHOD_COLORS = {
    "integrated_milp": "#264653",
    "classical_milp": "#2a9d8f",
    "greedy": "#e76f51",
    "insertion": "#f4a261",
    "greedy+insertion": "#e9c46a",
    "repair": "#8ab17d",
    "local_search": "#457b9d",
    "dijkstra": "#6d597a",
    "aco": "#d62828",
}

INSTANCE_ORDER = [
    "feas_A_p4h7_d05",
    "feas_AB_p4h7_d05",
    "feas_ABCD_p4h7_d05",
    "feas_A_p4h7_d08",
    "feas_A_p6h10_d05",
    "ABCD_cap_botl",
    "ABCD_hier",
    "ABCD_near_thr",
    "ABCD_no_maint",
]
INSTANCE_LABELS = [
    "A p4h7 d05",
    "AB p4h7 d05",
    "ABCD p4h7 d05",
    "A p4h7 d08",
    "A p6h10 d05",
    "ABCD capacity",
    "ABCD hierarchy",
    "ABCD threshold",
    "ABCD no maint",
]


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def save(fig, name: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG_DIR / name, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _set_plot_style() -> None:
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "legend.fontsize": 8,
            "figure.titlesize": 12,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def plot_runtime_by_instance(df: pd.DataFrame) -> None:
    _set_plot_style()
    fig, ax = plt.subplots(figsize=(11.5, 5.5))
    x = np.arange(len(INSTANCE_ORDER))
    width = 0.09
    for idx, method in enumerate(ALL_METHOD_ORDER):
        vals = []
        for label in INSTANCE_ORDER:
            row = df[(df["label"] == label) & (df["method"] == method)]
            vals.append(float(row.iloc[0]["wall_s"]))
        ax.bar(
            x + (idx - len(ALL_METHOD_ORDER) / 2) * width,
            vals,
            width,
            label=ALL_METHOD_LABELS[idx],
            color=METHOD_COLORS[method],
            edgecolor="white",
            linewidth=0.3,
        )
    ax.set_xticks(x, INSTANCE_LABELS, rotation=30, ha="right")
    ax.set_yscale("log")
    ax.set_ylabel("Wall time (s, log scale)")
    ax.set_title("Instance-matched runtime comparison: heuristics versus MILP")
    ax.grid(axis="y", linestyle=":", alpha=0.35)
    ax.legend(ncol=3, loc="lower center", bbox_to_anchor=(0.5, -0.44), frameon=False)
    save(fig, "ch7_runtime_by_instance.png")


def plot_runtime_distribution(df: pd.DataFrame) -> None:
    _set_plot_style()
    fig, ax = plt.subplots(figsize=(10.8, 5.2))
    series = []
    labels = []
    for method, label in zip(ALL_METHOD_ORDER, ALL_METHOD_LABELS):
        vals = df[df["method"] == method]["wall_s"].astype(float).to_numpy()
        series.append(vals)
        labels.append(label)
    bp = ax.boxplot(
        series,
        tick_labels=labels,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "black", "linewidth": 1.2},
        whiskerprops={"linewidth": 1.0},
        capprops={"linewidth": 1.0},
    )
    for patch, method in zip(bp["boxes"], ALL_METHOD_ORDER):
        color = METHOD_COLORS[method]
        patch.set_facecolor(color)
        patch.set_alpha(0.8)
        patch.set_edgecolor("black")
        patch.set_linewidth(0.6)
    ax.set_yscale("log")
    ax.set_ylabel("Wall time (s, log scale)")
    ax.set_title("Runtime distribution by method on the nine-instance benchmark")
    ax.grid(axis="y", linestyle=":", alpha=0.35)
    ax.tick_params(axis="x", rotation=25)
    save(fig, "ch7_runtime_distribution.png")


def plot_modes_tradeoff(df: pd.DataFrame) -> None:
    _set_plot_style()
    rows = []
    for method in ALL_METHOD_ORDER:
        m = df[df["method"] == method].copy()
        if method in HEURISTIC_ORDER:
            complete = (m["status"] == "complete").mean() * 100.0
        else:
            complete = (m["status"] == "optimal").mean() * 100.0
        rows.append(
            {
                "method": method,
                "label": ALL_METHOD_LABELS[ALL_METHOD_ORDER.index(method)],
                "median_wall": m["wall_s"].astype(float).median(),
                "mean_cov": m["coverage_pct"].astype(float).mean(),
                "complete_rate": complete,
                "mean_cost": m["total_cost"].astype(float).mean(),
            }
        )
    summary = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(8.8, 5.8))
    sizes = 90 + 0.0012 * summary["mean_cost"].to_numpy()
    point_colors = [METHOD_COLORS[m] for m in summary["method"]]
    scatter = ax.scatter(
        summary["median_wall"],
        summary["mean_cov"],
        s=sizes,
        c=point_colors,
        alpha=0.9,
        edgecolors="black",
        linewidths=0.6,
    )
    offset_map = {
        "Integrated\nMILP": (6, 5),
        "Classical\nMILP": (6, -12),
        "Greedy": (4, 6),
        "Insertion": (4, -12),
        "G+I": (4, 14),
        "Repair": (4, -20),
        "Local search": (4, 20),
        "Dijkstra": (4, -4),
        "ACO": (4, 8),
    }
    for _, row in summary.iterrows():
        dx, dy = offset_map.get(row["label"], (4, 3))
        ax.annotate(
            row["label"],
            (row["median_wall"], row["mean_cov"]),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=8,
        )
    ax.set_xscale("log")
    ax.set_xlabel("Median wall time (s, log scale)")
    ax.set_ylabel("Mean coverage (%)")
    ax.set_title("Mode comparison trade-off: runtime, coverage, completion, and cost")
    ax.grid(linestyle=":", alpha=0.35)

    complete_rates = summary["complete_rate"].to_numpy()
    size_refs = [100, 180, 260]
    labels = []
    for s in size_refs:
        approx_cost = int(round((s - 90) / 0.0012 / 1000) * 1000)
        labels.append(f"~{approx_cost:,}")
    handles = [
        plt.scatter([], [], s=s, color="#bdbdbd", edgecolors="black", linewidths=0.5)
        for s in size_refs
    ]
    legend1 = ax.legend(handles, labels, title="Mean cost", loc="lower left", frameon=False)
    ax.add_artist(legend1)

    rate_text = " | ".join(f"{r['label'].replace(chr(10),' ')}={r['complete_rate']:.1f}%" for _, r in summary.iterrows())
    ax.text(0.01, 0.02, f"Complete/optimal rates: {rate_text}", transform=ax.transAxes, fontsize=7)
    save(fig, "ch7_modes_tradeoff.png")


def main() -> None:
    rows = read_csv(ROOT / "results" / "tables" / "exact_feasible" / "full_seven_method_tournament.csv")
    df = pd.DataFrame(rows)
    df["wall_s"] = pd.to_numeric(df["wall_s"], errors="coerce")
    df["total_cost"] = pd.to_numeric(df["total_cost"], errors="coerce")
    cov = pd.to_numeric(df["coverage_pct"], errors="coerce")
    assigned = pd.to_numeric(df["assigned"], errors="coerce")
    flights = pd.to_numeric(df["flights"], errors="coerce")
    df["coverage_pct"] = cov.fillna((100.0 * assigned / flights).replace([np.inf, -np.inf], np.nan))

    plot_runtime_by_instance(df)
    plot_runtime_distribution(df)
    plot_modes_tradeoff(df)
    print(f"Saved figures to {FIG_DIR}")


if __name__ == "__main__":
    main()
