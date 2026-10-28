#!/usr/bin/env python3
"""Aggregate and visualize repeated arc-vs-path benchmark measurements."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

import matplotlib.pyplot as plt
import numpy as np


TIME_COLUMNS = (
    "arc_build_s", "arc_solve_s", "arc_total_s",
    "path_enumeration_s", "path_build_s", "path_solve_s", "path_total_s",
    "speedup_path_vs_arc",
)


def load_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for column in TIME_COLUMNS:
            row[column] = float(row[column])
        for column in (
            "repeat", "flights", "aircraft", "arc_vars", "arc_declared_vars",
            "arc_cons", "path_vars", "path_cons", "path_count_total",
        ):
            row[column] = int(row[column])
        for column in ("path_coverage_valid", "objective_match"):
            row[column] = row[column] == "True"
        row["arc_obj"] = float(row["arc_obj"])
        row["path_obj"] = float(row["path_obj"])
    return rows


def quartiles(values: list[float]) -> tuple[float, float, float]:
    q1, med, q3 = np.percentile(values, [25, 50, 75])
    return float(q1), float(med), float(q3)


def aggregate_rows(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["instance"]].append(row)

    aggregates = []
    for instance, group in grouped.items():
        first = group[0]
        aggregate = {
            "instance": instance,
            "repeats": len(group),
            "flights": first["flights"],
            "aircraft": first["aircraft"],
            "arc_obj": first["arc_obj"],
            "path_obj": first["path_obj"],
            "arc_vars": first["arc_vars"],
            "arc_declared_vars": first["arc_declared_vars"],
            "arc_cons": first["arc_cons"],
            "path_vars": first["path_vars"],
            "path_cons": first["path_cons"],
            "path_count_total": first["path_count_total"],
            "objective_match_all": all(row["objective_match"] for row in group),
            "path_coverage_valid_all": all(row["path_coverage_valid"] for row in group),
        }
        for column in TIME_COLUMNS:
            q1, med, q3 = quartiles([row[column] for row in group])
            aggregate[f"{column}_q1"] = q1
            aggregate[f"{column}_median"] = med
            aggregate[f"{column}_q3"] = q3
        aggregates.append(aggregate)
    return sorted(aggregates, key=lambda row: (row["flights"], row["instance"]))


def write_csv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict], out_path: Path) -> None:
    speedups = [row["speedup_path_vs_arc_median"] for row in rows]
    metrics = [
        ("instances", len(rows)),
        ("repeats_per_instance", min(row["repeats"] for row in rows)),
        ("objective_match_count", sum(row["objective_match_all"] for row in rows)),
        ("coverage_valid_count", sum(row["path_coverage_valid_all"] for row in rows)),
        ("arc_total_median_across_instances_s", median(row["arc_total_s_median"] for row in rows)),
        ("path_total_median_across_instances_s", median(row["path_total_s_median"] for row in rows)),
        ("speedup_mean_arc_over_path", mean(speedups)),
        ("speedup_median_arc_over_path", median(speedups)),
        ("path_faster_count", sum(speedup > 1.0 for speedup in speedups)),
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerows(metrics)


def short_names(rows: list[dict]) -> list[str]:
    return [row["instance"].replace("ABCD_", "").replace("_test", "") for row in rows]


def save_figure(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close()


def plot_runtime_bars(rows: list[dict], out_path: Path) -> None:
    x = np.arange(len(rows))
    width = 0.38
    _, axis = plt.subplots(figsize=(11, 4.8))
    for offset, prefix, label, color in (
        (-width / 2, "arc_total_s", "Arc-based", "#2166ac"),
        (width / 2, "path_total_s", "Path-based", "#b2182b"),
    ):
        medians = np.array([row[f"{prefix}_median"] for row in rows])
        lower = medians - np.array([row[f"{prefix}_q1"] for row in rows])
        upper = np.array([row[f"{prefix}_q3"] for row in rows]) - medians
        axis.bar(x + offset, medians, width, label=label, color=color, yerr=[lower, upper], capsize=3)
    axis.set_xticks(x, short_names(rows), rotation=25, ha="right")
    axis.set_ylabel("Total wall time (s), median and IQR")
    axis.set_title("Repeated arc-based and exhaustive path-based runtimes")
    axis.legend()
    save_figure(out_path)


def plot_speedup_vs_size(rows: list[dict], out_path: Path) -> None:
    _, axis = plt.subplots(figsize=(8, 5))
    axis.axhline(1.0, color="#555555", linestyle="--", linewidth=1.2, label="Runtime parity")
    for row, label in zip(rows, short_names(rows)):
        axis.scatter(row["flights"], row["speedup_path_vs_arc_median"], s=70, color="#1b7837")
        axis.annotate(label, (row["flights"], row["speedup_path_vs_arc_median"]),
                      xytext=(5, 5), textcoords="offset points", fontsize=8)
    axis.set_xlabel("Number of flights")
    axis.set_ylabel("Median speedup = arc total / path total")
    axis.set_title("End-to-end speedup by instance size")
    axis.legend()
    save_figure(out_path)


def plot_model_size(rows: list[dict], out_path: Path) -> None:
    x = np.arange(len(rows))
    width = 0.38
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    axes[0].bar(x - width / 2, [row["arc_vars"] for row in rows], width,
                label="Arc $x$ variables", color="#2166ac")
    axes[0].bar(x + width / 2, [row["path_vars"] for row in rows], width,
                label="Path variables", color="#b2182b")
    axes[0].set_ylabel("Active binary variables")
    axes[0].legend()
    axes[1].bar(x - width / 2, [row["arc_cons"] for row in rows], width,
                label="Arc constraints", color="#67a9cf")
    axes[1].bar(x + width / 2, [row["path_cons"] for row in rows], width,
                label="Path constraints", color="#ef8a62")
    axes[1].set_ylabel("Active constraints")
    axes[1].set_xticks(x, short_names(rows), rotation=25, ha="right")
    axes[1].legend()
    fig.suptitle("Equivalent routing-core model sizes")
    save_figure(out_path)


def plot_timing_decomposition(rows: list[dict], out_path: Path) -> None:
    x = np.arange(len(rows))
    width = 0.36
    _, axis = plt.subplots(figsize=(11, 5.2))
    arc_build = np.array([row["arc_build_s_median"] for row in rows])
    arc_solve = np.array([row["arc_solve_s_median"] for row in rows])
    path_enum = np.array([row["path_enumeration_s_median"] for row in rows])
    path_build = np.array([row["path_build_s_median"] for row in rows])
    path_solve = np.array([row["path_solve_s_median"] for row in rows])
    axis.bar(x - width / 2, arc_build, width, label="Arc build", color="#92c5de")
    axis.bar(x - width / 2, arc_solve, width, bottom=arc_build, label="Arc solve", color="#2166ac")
    axis.bar(x + width / 2, path_enum, width, label="Path enumeration", color="#fddbc7")
    axis.bar(x + width / 2, path_build, width, bottom=path_enum, label="Path build", color="#ef8a62")
    axis.bar(x + width / 2, path_solve, width, bottom=path_enum + path_build,
             label="Path solve", color="#b2182b")
    axis.set_xticks(x, short_names(rows), rotation=25, ha="right")
    axis.set_ylabel("Median wall time (s)")
    axis.set_title("End-to-end runtime decomposition")
    axis.legend(ncol=3)
    save_figure(out_path)


def plot_route_growth(rows: list[dict], out_path: Path) -> None:
    _, axis = plt.subplots(figsize=(8, 5))
    for row, label in zip(rows, short_names(rows)):
        axis.scatter(row["path_count_total"], row["path_total_s_median"], s=70, color="#762a83")
        axis.annotate(label, (row["path_count_total"], row["path_total_s_median"]),
                      xytext=(5, 5), textcoords="offset points", fontsize=8)
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlabel("Enumerated aircraft paths (log scale)")
    axis.set_ylabel("Path total wall time (s, log scale)")
    axis.set_title("Route-pool growth and exhaustive path runtime")
    save_figure(out_path)


def plot_objective_parity(rows: list[dict], out_path: Path) -> None:
    arc = np.array([row["arc_obj"] for row in rows])
    path = np.array([row["path_obj"] for row in rows])
    limits = [min(arc.min(), path.min()), max(arc.max(), path.max())]
    _, axis = plt.subplots(figsize=(6, 5.5))
    axis.plot(limits, limits, linestyle="--", color="#555555", label="Exact parity")
    axis.scatter(arc, path, s=70, color="#01665e")
    for x_value, y_value, label in zip(arc, path, short_names(rows)):
        axis.annotate(label, (x_value, y_value), xytext=(5, 5), textcoords="offset points", fontsize=8)
    axis.set_xlabel("Arc-based objective")
    axis.set_ylabel("Path-based objective")
    axis.set_title("Objective-equivalence check")
    axis.legend()
    save_figure(out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("results/tables/step6_arc_vs_path.csv"))
    parser.add_argument("--figure-dir", type=Path, default=Path("paper/figures"))
    args = parser.parse_args()

    aggregates = aggregate_rows(load_rows(args.input))
    write_csv(aggregates, Path("results/tables/step6_arc_vs_path_aggregate.csv"))
    write_summary(aggregates, Path("results/tables/step6_arc_vs_path_summary.csv"))
    plot_runtime_bars(aggregates, args.figure_dir / "step6_runtime_comparison.png")
    plot_speedup_vs_size(aggregates, args.figure_dir / "step6_speedup_vs_size.png")
    plot_model_size(aggregates, args.figure_dir / "step6_model_size.png")
    plot_timing_decomposition(aggregates, args.figure_dir / "step6_timing_decomposition.png")
    plot_route_growth(aggregates, args.figure_dir / "step6_route_growth.png")
    plot_objective_parity(aggregates, args.figure_dir / "step6_objective_parity.png")


if __name__ == "__main__":
    main()
