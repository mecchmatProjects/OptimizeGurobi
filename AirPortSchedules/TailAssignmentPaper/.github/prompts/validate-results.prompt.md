---
mode: agent
description: Validate computed results against reference baselines and against claimed values in the paper.
---

# Task: Validate Results

## Context
This project claims to reproduce and correct Khaled et al. (2018).
Validation ensures:
  (a) Our code reproduces their original results (within solver tolerance).
  (b) The constraint-(13) correction changes results in the expected direction.
  (c) Our extended model results are self-consistent.

Read **AGENTS.md** before proceeding.

## Validation Steps

### Step 1: Load and align results

```python
import pandas as pd

ref  = pd.read_csv('results/reference/output3_batch_summary.csv')
new  = pd.read_csv('results/tables/<your_output>.csv')

# Align on (stem, mode) or on (P, H, density)
merged = ref.merge(new, on=['stem'], suffixes=('_ref', '_new'))
```

### Step 2: Check objective agreement

For rows where `status == 'optimal'` in both:
```python
diff = (merged['objective_new'] - merged['objective_ref']).abs()
tol  = 1e-3  # CPLEX default tolerance
print(f"Max objective deviation: {diff.max():.6f}")
print(f"Rows within tolerance:   {(diff < tol).sum()} / {len(merged)}")
```

### Step 3: Check C13 correction impact

```python
paper    = pd.read_csv('results/tables/table6_paper_c13.csv')
corrected = pd.read_csv('results/tables/table6_corrected_c13.csv')
merged   = paper.merge(corrected, on='stem', suffixes=('_paper','_corrected'))
changed  = merged[merged['objective_paper'] != merged['objective_corrected']]
print(f"Instances where correction changes objective: {len(changed)} / {len(merged)}")
print(changed[['stem','objective_paper','objective_corrected','gap_pct_corrected']])
```

**Expected**: corrected formulation should be more restrictive (higher or equal
objective value) on instances where the original was feasible but violating.

### Step 4: Sanity checks on maintenance schedule

For each solved instance, verify:
- Every aircraft that has reached `Maintenance_Thresholds.A` (minutes) between
  two maintenance events has a scheduled A-check in between.
- `y[j,d,A] = 1` implies no flight assigned to aircraft `j` during the duration
  window `[t_end, t_end + Maintenance_Durations.A]` on day `d`.
- Initial accumulated hours (`Initial_Checks`) are correctly subtracted from
  the first maintenance window.

Use `src/diagnostics.py --mode scan` to check any instance that appears
infeasible or has an unexpectedly high gap.

### Step 5: Check model size matches paper tables

From Table 5, row (p=10, h=7, δ=0.95):
  Expected: ~2057 variables, ~3600 constraints (without maintenance).
From Table 6, row (p=40, h=21, δ=1.00):
  Expected: ~52,256 variables, ~53,562 constraints (without maintenance).

```python
python src/inspect_model.py --data data/instances/DataCplex_density=1_p=10_h=7_test_0.json
```

## Validation Criteria

| Check | Pass condition |
|-------|---------------|
| Objective reproduction | |objective_new − objective_ref| < 1 (absolute) or < 0.01% |
| Gap reproduction | |gap_new − gap_ref| < 0.01% |
| CPU trend | new_cpu ≤ 2× ref_cpu (hardware differences expected) |
| C13 correction | ≥ 1 instance shows different objective (proves the bug exists) |
| Maintenance schedule validity | 0 violations across all solved instances |
| Model size | Variables within ±5% of paper table values |

## Reporting Format

Write a validation summary to `results/tables/validation_report.csv` with columns:
```
check, n_tested, n_passed, n_failed, max_deviation, notes
```
