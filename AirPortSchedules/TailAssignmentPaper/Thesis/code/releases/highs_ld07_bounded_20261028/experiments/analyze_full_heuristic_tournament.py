"""Summarize the full seven-heuristic tournament without hiding semantic gaps."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "results/tables/exact_feasible/full_seven_method_tournament.csv"
OUTPUT = ROOT / "results/tables/exact_feasible/full_seven_method_summary.csv"


def main():
    data = pd.read_csv(INPUT)
    integrated = data[data["method"] == "integrated_milp"][["label", "total_cost"]]
    integrated = integrated.rename(columns={"total_cost": "milp_total_cost"})
    heuristics = data[~data["method"].isin(["classical_milp", "integrated_milp"])].copy()
    heuristics = heuristics.merge(integrated, on="label", how="left")
    heuristics["complete"] = heuristics["status"].eq("complete")
    heuristics["cost_difference_pct"] = (
        (heuristics["total_cost"] - heuristics["milp_total_cost"])
        / heuristics["milp_total_cost"] * 100.0
    )
    heuristics["comparison_note"] = "comparable total-cost difference"
    heuristics.loc[heuristics["cost_difference_pct"] < 0, "comparison_note"] = (
        "heuristic lower; inspect feasible-set semantics"
    )

    summary = heuristics.groupby("method", as_index=False).agg(
        instances=("label", "count"),
        complete_instances=("complete", "sum"),
        mean_coverage_pct=("coverage_pct", "mean"),
        mean_total_cost=("total_cost", "mean"),
        median_wall_s=("wall_s", "median"),
        mean_cost_difference_pct=("cost_difference_pct", "mean"),
    )
    summary["complete_rate_pct"] = (
        summary["complete_instances"] / summary["instances"] * 100.0
    )
    summary = summary.round(3)
    summary.to_csv(OUTPUT, index=False)
    print(summary.to_string(index=False))
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
