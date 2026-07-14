---
mode: agent
description: Execute a parameterised experiment grid over TAP instances and save structured CSV results for the paper.
---

# Task: Run Experiments

## Context
You are running computational experiments to validate or extend results for the
paper "Correcting and Extending the Compact Tail Assignment Model".

Read **AGENTS.md** before executing any commands.

## Available Scripts

```powershell
# Single instance
python src/model.py --mode milp \
  --data data/instances/DataCplex_density=1_p=10_h=7_test_0.json \
  --solver cplex --time-limit 300

# Batch over a folder
python src/model.py --mode batch --input-dir data/instances/ \
  --solver cplex --time-limit 300 --output-dir results/tables/

# Parameterised grid (reproduce one paper table)
python experiments/reproduce_tables.py --table 5 --solver cplex
python experiments/reproduce_tables.py --table 6 --solver cplex
python experiments/reproduce_tables.py --table 10 --solver cplex --dmax 4
python experiments/reproduce_tables.py --table 11 --solver cplex

# Quick subset (h=7,15 only; p=10,20 only — faster for debugging)
python experiments/reproduce_tables.py --table 5 --quick --solver cplex

# Compare original vs corrected constraint (13)
python experiments/reproduce_tables.py --table 6 \
  --use-paper-c13 --output results/tables/table6_paper_c13.csv
python experiments/reproduce_tables.py --table 6 \
  --output results/tables/table6_corrected_c13.csv
```

## Experiment Workflow

1. Check solver is available:
   ```python
   python -c "from pyomo.opt import SolverFactory; print(SolverFactory('cplex').available())"
   ```
2. If instances are missing, generate them:
   ```powershell
   python src/generate_instances.py --density 1.0 --p 10 --h 7 --count 10 --output-dir data/instances/
   ```
3. Run the experiment for the requested table.
4. Verify the output CSV exists in `results/tables/`.
5. Compare against `results/reference/output3_batch_summary.csv` for overlap rows.

## Expected Output CSV Columns
```
stem, P, H, F, vars, constraints, nodes, nodes_max, gap_pct, cpu_s, objective, status
```

## Key Experiment Groups for the Paper

| Experiment | Config file | Purpose |
|------------|------------|---------|
| Table 5 reproduction | configs/table5_params.json | δ=0.95, p∈{10,20,30,40}, h∈{7,15,21,30} |
| Table 6 reproduction | configs/table6_params.json | δ=1.00, same grid |
| Table 10 reproduction | configs/table10_params.json | Maintenance: dmax=4/5, Tmax=64/72h |
| Table 11 reproduction | configs/table11_params.json | Maintenance: ν=14 landings, dmax=4 |
| C13 correction comparison | (inline flags) | Same grid, toggle `use_paper_c13` |
| Heuristic gap study | (run_batch.py) | Compare heuristic vs MILP objective gap |

## Reporting
After running, summarise results as:
- Mean and max CPU times per (p, h) group.
- Mean and max MIP gap.
- Number of instances solved to optimality within time limit.
- For C13 correction: fraction of instances where correction changes the objective.
