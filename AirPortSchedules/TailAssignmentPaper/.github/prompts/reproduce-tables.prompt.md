---
mode: agent
description: Reproduce a specific numbered table from Khaled et al. (2018) using the corrected model and save results for paper inclusion.
---

# Task: Reproduce Paper Tables

## Context
Reproduce Tables 5, 6, 10, or 11 from:
  Khaled et al., "A compact optimization model for the tail assignment problem",
  EJOR 264 (2018) 548–557.

Read **AGENTS.md** and `experiments/configs/` before running.

## Table Specifications

### Table 5 — Basic Model, δ = 0.95
- Density: δ = 0.95 (density parameter)
- Aircraft: p ∈ {10, 20, 30, 40}
- Horizon: h ∈ {7, 15, 21, 30} days
- 10 instances per (p, h) combination → 160 total instances
- Report: mean vars, mean constraints, mean/max nodes, residual gap, Gap@root, CPU (with/without presolve)
- Config: `experiments/configs/table5_params.json`

### Table 6 — Basic Model, δ = 1.00
- Same as Table 5 but density = 1.00
- Config: `experiments/configs/table6_params.json`

### Table 10 — Maintenance Model
- Density: δ = 1.00
- Aircraft: p ∈ {10, 20, 30, 40}
- Horizon: h ∈ {15, 21, 30} days
- Two parameter sets: (dmax=4, Tmax=64h) and (dmax=5, Tmax=72h)
- Config: `experiments/configs/table10_params.json`

### Table 11 — Maximum Landings Variant
- Same instances as Table 10 but constraint = max 14 landings (ν=14), dmax=4
- Config: `experiments/configs/table11_params.json`

## Steps to Reproduce a Table

```powershell
# Full reproduction (slow, ~hours for tables 5/6 at p=40)
python experiments/reproduce_tables.py --table 5 --solver cplex --output results/tables/table5_full.csv

# Quick subset (p ≤ 20, h ≤ 15 only — good for validation before full run)
python experiments/reproduce_tables.py --table 5 --quick --solver cplex

# Reproduce with original (broken) constraint (13) for comparison
python experiments/reproduce_tables.py --table 6 --use-paper-c13 \
  --output results/tables/table6_paper_c13.csv

# Reproduce with corrected constraint (13) — this is the default
python experiments/reproduce_tables.py --table 6 \
  --output results/tables/table6_corrected.csv
```

## Expected Output Format

```csv
table,P,H,density,F_mean,vars_mean,cons_mean,nodes_mean,nodes_max,gap_pct_mean,root_gap_mean,cpu_mean_no_presolve,cpu_mean_presolve,obj_mean_no_presolve,obj_mean_presolve,n_optimal
5,10,7,0.95,206,2057,3600,0,0,0.0,0.02,2.62,0.51,1672661,1672662,10
...
```

## Formatting for the Paper

After getting CSV results, format them as LaTeX using:
```python
python experiments/format_table.py --csv results/tables/table5_full.csv --latex paper/sections/
```
This generates a `table5.tex` snippet ready for `\input` in `7_computational.tex`.

## Notes on Discrepancies

The following discrepancies from Khaled et al. (2018) are expected:
1. **CPU times**: Paper used Intel i7-3740QM @ 2.7 GHz (2014 hardware).
   Modern hardware will be faster; times are not directly comparable.
2. **Objective values**: Must match within CPLEX default tolerance (1e-4).
   Any difference > 0.01% in gap or > 1 unit in objective requires investigation.
3. **Constraint (13)**: For Table 6, some instances will show different objectives
   when using the corrected vs. original formulation. This is expected and is the
   main contribution of the paper.
4. **Instance generation**: Original paper used a proprietary real-world dataset
   from an Asian low-cost carrier. Our generator replicates the statistical
   properties but not the exact instances. Reproducibility is demonstrated on
   our generated instances, not the original ones.
