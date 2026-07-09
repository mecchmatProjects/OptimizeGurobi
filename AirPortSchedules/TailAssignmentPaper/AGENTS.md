# AGENTS.md — Tail Assignment Paper Project

## Project Identity
This is a scientific computing project that reproduces, corrects, and extends
the compact MILP formulation for the **Tail Assignment Problem** (Khaled et al.,
*European Journal of Operational Research* 264, 2018, pp. 548–557).

## Repository Map
```
src/model.py                  Pyomo MILP + greedy/insertion heuristic (main entry point)
src/generate_instances.py     Deterministic JSON instance generator
src/convert_data.py           DAT ↔ JSON converter
src/diagnostics.py            IIS finder + constraint-group deactivation scan
experiments/run_batch.py      Batch runner over a parameterised instance grid
experiments/reproduce_tables.py  Reproduce paper Tables 5, 6, 10, 11
experiments/configs/          JSON parameter grids (one file per table)
data/instances/               Problem instances (JSON, naming: DataCplex_density=D_p=P_h=H_test_I.json)
results/tables/               CSV outputs from experiments (git-ignored, re-runnable)
results/reference/            Baseline batch summary for validation
paper/main.tex                Master LaTeX document
paper/sections/               One .tex file per section (1_intro.tex … 8_conclusion.tex)
paper/refs.bib                BibTeX references
docs/model_math.tex           Formal mathematical derivations of the MILP
docs/heuristic_math.tex       Formal derivation of the greedy/insertion heuristic
```

## Key Mathematical Entities

| Symbol | Meaning |
|--------|---------|
| `F`    | Set of flight legs, indexed by `i` |
| `P`    | Set of aircraft (tail numbers), indexed by `j` |
| `A`    | Set of airports, indexed by `k` |
| `x[i,j]` | Binary: flight `i` assigned to aircraft `j` |
| `z[i,j,d,c]` | Binary: check `c` triggered after flight `i` for aircraft `j` on day `d` |
| `y[j,d,c]` | Binary: aircraft `j` undergoes check `c` on day `d` |
| `mega[j,d,c]` | Binary: aircraft `j` has check of level ≥ `c` on day `d` (hierarchy) |
| `c_ij` | Cost of assigning flight `i` to aircraft `j` |
| `Δt`   | Minimum ground turn time between flights |
| `T_max`| Maximum cumulative flight hours between A/B checks |
| `d_max`| Maximum calendar days between C/D checks |

## Constraint (13) — The Correction (Central Paper Claim)

**Khaled et al. (2018) original** (eq. 13):
```
  Σ_{i ∈ F_{d,d'}} x_{ij} t_i  ≤  T_max + M*(2 − y_{jd} − y_{jd'}) + M * Σ_{r∈[d+1,d'−1]} y_{jr}
```
**Problem**: When `y[j,d]=0` (no check at start) and `y[j,d']=0` (no check at end),
the big-M term `M*(2−0−0) = 2M` makes the constraint vacuous even in the case where
two consecutive maintenance windows bound the interval. Flights in between are
incorrectly allowed to exceed `T_max`.

**Corrected formulation** (two constraints, each anchored at one endpoint):
```
  Σ x_{ij} t_i  ≤  T_max + M * y_sum + M * y[j,d]      (anchored at start)
  Σ x_{ij} t_i  ≤  T_max + M * y_sum + M * y[j,d']     (anchored at end)
```
where `y_sum = Σ_{r ∈ [d+1,d'−1]} y_{jr}` (any intermediate check).

Implementation: `src/model.py`, `MILP_Sheduler._add_c13_hr_accumulation()`,
toggle via `use_paper_c13=True/False`.

## Code Conventions

- **Solver**: CPLEX via Pyomo (`SolverFactory('cplex')`). Always pass `time_limit`.
- **Instance naming**: `DataCplex_density={d}_p={p}_h={h}_test_{idx}.json`.
  `density` ∈ {0.5, 0.75, 0.8, 1.0}, `p` = # aircraft, `h` = horizon in days.
- **Outputs**: Every script writes to `results/tables/` (CSV) or `results/figures/` (PNG).
  Never write to `data/` or `src/`.
- **Random seeds**: use `stable_seed(density, p, h, index)` in `src/generate_instances.py`
  for reproducibility.
- **Constraint toggles**: All `MILP_Sheduler.build_model()` flags default to `True`.
  To reproduce the *basic* model (C1–C4 only), pass `use_maintenance=False`.

## How to Run (Quick Reference)

```powershell
# Activate environment
.\venv\Scripts\Activate.ps1

# Single instance, full maintenance model
python src/model.py --mode milp \
  --data data/instances/DataCplex_density=1_p=10_h=7_test_0.json \
  --solver cplex --time-limit 60

# Batch over a folder
python src/model.py --mode batch --input-dir data/instances/ --solver cplex

# Reproduce Table 5 (quick subset)
python experiments/reproduce_tables.py --table 5 --quick --solver cplex

# Diagnose infeasibility
python src/diagnostics.py --data data/instances/ABCD_all_checks_test.json --mode both
```

## Agent Task Prompts

Located in `.github/prompts/`:
- `write-paper.prompt.md`        — draft / extend paper sections
- `run-experiments.prompt.md`    — execute experiment grids, interpret outputs
- `validate-results.prompt.md`   — compare results against reference baselines
- `reproduce-tables.prompt.md`   — reproduce specific Khaled et al. tables

## Paper Sections Overview

| File | Content |
|------|---------|
| `1_intro.tex` | Motivation, airline planning pipeline, TAP definition |
| `2_literature.tex` | Comparison with set-partitioning, multi-commodity flow, time-space network models |
| `3_basic_model.tex` | Basic MILP: constraints C1–C4, Proposition 1 & 2, illustrative example |
| `4_maintenance_model.tex` | Extended model with maintenance; **constraint (13) correction** |
| `5_hierarchy_extension.tex` | Full A/B/C/D hierarchy; C13b (pre-horizon hours); C14b (multi-day checks) |
| `6_heuristics.tex` | Greedy/insertion heuristic; complexity; gap analysis |
| `7_computational.tex` | Reproduced Tables 5/6/10/11; corrected results; new instance classes |
| `8_conclusion.tex` | Summary of contributions, limitations, future work |

## Solver Environment

- **CPLEX 22.x** is the reference solver (matches Khaled et al.).
- All time limits quoted in the paper use wall-clock seconds, not CPU ticks.
- `--no-presolve` flag in CPLEX corresponds to `solver.options['preprocessing presolve'] = 0`
  in `run_batch.py`. Paper Tables 5/6 report results with and without presolve.

## Do NOT

- Do NOT commit large LP/log files.
- Do NOT modify `data/instances/` files — they are the canonical test set.
- Do NOT change the `stable_seed` formula in `src/generate_instances.py`;
  doing so invalidates reproducibility claims.
- Do NOT use `Model_28Oct.py` (legacy); use `src/model.py` exclusively.
