"""Summarize matched fore-benchgen benchmark result CSVs.

The report is descriptive: it aggregates recorded runs without inferring
statistical significance. Coverage is reported before objective values because
partial heuristic schedules are not directly cost-comparable with full MILPs.
"""

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-glob", required=True,
                        help="Glob relative to the repository root for run CSVs.")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "results" / "tables" / "fore_benchgen_summary.csv")
    args = parser.parse_args()

    files = sorted(ROOT.glob(args.input_glob))
    if not files:
        raise SystemExit(f"No result files match {args.input_glob!r}")
    runs = pd.concat((pd.read_csv(path) for path in files), ignore_index=True)
    runs["coverage_pct"] = 100 * runs["assigned"] / runs["F"]

    group_columns = [
        "mode", "P", "H", "topology", "threshold_mode", "cost_model",
        "application_compatible",
    ]
    summary = runs.groupby(group_columns, dropna=False).agg(
        runs=("stem", "count"),
        complete_runs=("status", lambda values: int((values == "complete").sum())),
        optimal_runs=("status", lambda values: int((values == "optimal").sum())),
        mean_assigned=("assigned", "mean"),
        median_assigned=("assigned", "median"),
        mean_coverage_pct=("coverage_pct", "mean"),
        median_coverage_pct=("coverage_pct", "median"),
        mean_cpu_s=("cpu_s", "mean"),
        median_cpu_s=("cpu_s", "median"),
        mean_objective=("objective", "mean"),
    ).reset_index()
    numeric = summary.select_dtypes(include="number").columns
    summary[numeric] = summary[numeric].round(4)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.output, index=False)
    print(f"Wrote {len(summary)} method summaries to {args.output}")


if __name__ == "__main__":
    main()