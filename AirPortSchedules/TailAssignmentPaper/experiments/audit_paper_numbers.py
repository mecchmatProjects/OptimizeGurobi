"""One-off audit: every number in section 07 must come from the result CSVs."""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEX = (ROOT / "paper/sections/07_computational.tex").read_text(encoding="utf8")

LABEL = {
    "legacy_paper_c13": "Legacy paper",
    "legacy_endpoint_split": "Legacy split",
    "legacy_corrected_strengthened": "Legacy corrected strengthened",
    "event_based_optimized": "Event-based optimized",
    "event_based_flex": "Event-based flexible",
}
problems = []


def load(rel):
    with (ROOT / rel).open(encoding="utf8") as handle:
        return list(csv.DictReader(handle))


def block(label):
    return re.search(rf"label\{{{label}\}}.*?bottomrule", TEX, re.S).group(0)


# 1. horizon table
horizon = block("tab:a_only_horizon_timing")
for row in load("results/tables/formulation_a_comparison_four_strengthened.csv"):
    want = (
        f"{LABEL[row['formulation']]} & optimal & {int(float(row['objective']))} & "
        f"{float(row['cpu_s']):.3f} & {float(row['wall_s']):.3f} & "
        f"{row['vars']} & {row['constraints']}"
    )
    if want not in horizon:
        problems.append(f"horizon H={row['H']}: missing '{want}'")

# 2. fleet table
fleet_rows = {(r["P"], r["formulation"]): r for r in load("results/tables/formulation_a_fleet_four_strengthened.csv")}
fleet = block("tab:a_fleet_timing")
order = list(LABEL)
for line in re.findall(r"^(\d+)\s+&(.+?)\\\\$", fleet, re.M):
    p, rest = line[0], line[1]
    cells = [c.strip() for c in rest.split("&")]
    if len(cells) != 10:
        problems.append(f"fleet P={p}: expected 10 cells, got {len(cells)}")
        continue
    for idx, formulation in enumerate(order):
        src = fleet_rows.get((p, formulation))
        if src is None:
            problems.append(f"fleet P={p}: no CSV row for {formulation}")
            continue
        for offset, metric in ((0, "cpu_s"), (5, "wall_s")):
            if abs(float(cells[idx + offset]) - float(src[metric])) > 5e-7:
                problems.append(
                    f"fleet P={p} {formulation} {metric}: tex={cells[idx + offset]} csv={src[metric]}"
                )

# 3. suite summary table
summary = {r["formulation"]: r for r in load("results/tables/four_method_suite_strengthened_summary.csv")}
suite = block("tab:four_method_suite_summary")
for formulation, label in LABEL.items():
    src = summary[formulation]
    row = re.search(rf"^{re.escape(label)} & (.+?)\\\\$", suite, re.M)
    if row is None:
        problems.append(f"suite summary: missing row for {label}")
        continue
    cells = [c.strip().replace("\\,", "").replace(",", "") for c in row.group(1).split("&")]
    for cell, key in zip(cells, ("mean_vars", "mean_constraints", "mean_cpu_s", "mean_wall_s")):
        if abs(float(cell) - float(src[key])) > 5e-4:
            problems.append(f"suite summary {label} {key}: tex={cell} csv={src[key]}")

# 4. flexible-variant table + percentages
bench = load("results/tables/flexible_event_benchmark.csv")
flex_tab = block("tab:flexible_event")
for formulation, label in (("event_based_optimized", "Event-based optimized"), ("event_based_flex", "Event-based flexible")):
    group = [r for r in bench if r["formulation"] == formulation]
    means = {k: sum(float(r[k]) for r in group) / len(group) for k in ("vars", "constraints", "build_s", "cpu_s", "wall_s")}
    row = re.search(rf"^{re.escape(label)} & (.+?)\\\\$", flex_tab, re.M)
    cells = [c.strip().replace("\\,", "").replace(",", "") for c in row.group(1).split("&")]
    for cell, key in zip(cells, ("vars", "constraints", "build_s", "cpu_s", "wall_s")):
        if abs(float(cell) - means[key]) > 5e-4:
            problems.append(f"tab:flexible_event {label} {key}: tex={cell} csv={means[key]:.6f}")

claim = re.search(
    r"uses ([\d.]+)\\% more variables and ([\d.]+)\\% more constraints,\s*"
    r"with ([\d.]+)\\% higher mean CPU and ([\d.]+)\\% higher mean wall time",
    TEX,
)
if claim is None:
    problems.append("flex percentage sentence not found")
else:
    for key, claimed in zip(("vars", "constraints", "cpu_s", "wall_s"), map(float, claim.groups())):
        fixed = sum(float(r[key]) for r in bench if r["formulation"] == "event_based_optimized")
        flex = sum(float(r[key]) for r in bench if r["formulation"] == "event_based_flex")
        actual = (flex - fixed) / fixed * 100.0
        if abs(actual - claimed) > 0.01:
            problems.append(f"flex percentage {key}: paper={claimed} actual={actual:.2f}")

print("\n".join(problems) if problems else "ALL SECTION 07 NUMBERS MATCH THE CSVs")
