"""Analyze exact-feasible comparison results."""
import pandas as pd

c = pd.read_csv("results/tables/exact_feasible/comparison.csv")

print("\n=== Exact-Feasible Instance Comparison ===\n")
for label in sorted(c["label"].unique()):
    sub = c[c["label"] == label].set_index("method")
    p = int(sub.iloc[0]["p"])
    fl = int(sub.iloc[0]["flights"])
    print(f"{label:22s} (p={p:2d}, f={fl:3d}):")
    for m in ["classical_milp", "integrated_milp", "greedy", "local_search"]:
        if m in sub.index:
            row = sub.loc[m]
            obj = row["obj"]
            status = row["status"]
            asgn = row["assigned_str"]
            wall = row["wall_s"]
            obj_str = str(int(obj)) if pd.notna(obj) else "-"
            print(f"  {m:20s}: {status:12s} obj={obj_str:8s} asgn={asgn:8s} {wall:6.1f}s")

print("\n=== Optimality Gaps (vs. Integrated MILP) ===")
for label in sorted(c["label"].unique()):
    sub = c[c["label"] == label]
    milp_rows = sub[sub["method"] == "integrated_milp"]
    if len(milp_rows) == 0:
        continue
    milp_obj = milp_rows.iloc[0]["obj"]
    if pd.isna(milp_obj):
        continue
    for method in ["classical_milp", "greedy", "local_search"]:
        heur_rows = sub[sub["method"] == method]
        if len(heur_rows) == 0:
            continue
        heur_obj = heur_rows.iloc[0]["obj"]
        if pd.notna(heur_obj) and heur_obj != milp_obj:
            gap = 100 * (heur_obj - milp_obj) / milp_obj
            print(f"{label:22s} {method:20s} vs MILP: {gap:+7.1f}%")
