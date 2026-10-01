"""Audit section 07 numbers and figures against the final benchmark CSV."""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEX = (ROOT / "paper/sections/07_computational.tex").read_text(encoding="utf8")
CSV = ROOT / "results/tables/five_method_longflight_final.csv"
LABELS = {
    "legacy_paper_c13": "Legacy paper",
    "legacy_endpoint_split": "Legacy split",
    "legacy_corrected_strengthened": "Legacy corrected",
    "event_based_optimized": "Event optimized",
    "event_based_flex": "Event flex",
}

with CSV.open(encoding="utf8", newline="") as handle:
    rows = list(csv.DictReader(handle))
performance = [row for row in rows if row["case"].startswith("perf_")]
problems = []

match = re.search(r"label\{tab:longflight_results\}(.*?)\\bottomrule", TEX, re.S)
if match is None:
    problems.append("long-flight result table not found")
else:
    table = match.group(1)
    for row in performance:
        expected = (
            f"{row['P']} & {row['H']} & {row['F']} & {LABELS[row['formulation']]} & "
            f"{row['status']} & {int(float(row['objective']))} & "
            f"{float(row['cpu_s']):.2f} & {float(row['wall_s']):.2f} & "
            f"{row['vars']} & {row['constraints']}"
        )
        if expected not in table:
            problems.append(f"missing result row: {expected}")

summary_match = re.search(r"label\{tab:longflight_aggregates\}(.*?)\\bottomrule", TEX, re.S)
if summary_match is None:
    problems.append("long-flight aggregate table not found")
else:
    summary_table = summary_match.group(1)
    for formulation, label in LABELS.items():
        group = [row for row in performance if row["formulation"] == formulation]
        optimal = [row for row in group if row["status"] == "optimal"]
        expected = (
            f"{label} & {len(optimal)}/{len(group)} & "
            f"{sum(float(row['vars']) for row in group)/len(group):.1f} & "
            f"{sum(float(row['constraints']) for row in group)/len(group):.1f} & "
            f"{sum(float(row['cpu_s']) for row in optimal)/len(optimal):.3f} & "
            f"{sum(float(row['wall_s']) for row in optimal)/len(optimal):.3f}"
        )
        if expected not in summary_table:
            problems.append(f"missing aggregate row: {expected}")

for filename in (
    "ordered_a_wall_vs_horizon_extended_p10.png",
    "ordered_a_cpu_vs_horizon_extended_p10.png",
    "a_variables_vs_fleet_extended_h30.png",
    "a_constraints_vs_fleet_extended_h30.png",
    "a_cpu_vs_fleet_extended_h30.png",
    "a_wall_vs_fleet_extended_h30.png",
):
    if not (ROOT / "paper/figures" / filename).is_file():
        problems.append(f"missing generated figure: {filename}")

print("\n".join(problems) if problems else "SECTION 07 TABLES AND FIGURES MATCH THE FINAL CSV")
