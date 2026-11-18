---
# VS Code Copilot — repository-scoped instructions
# File: .github/copilot-instructions.md
# Applies to all Copilot interactions in this workspace.
---

## Project Context

This repository contains:
1. A Pyomo MILP + greedy heuristic for the **Tail Assignment Problem** (TAP).
2. A LaTeX scientific paper correcting and extending Khaled et al. (2018).
3. Experiment harnesses that reproduce/validate the paper's computational tables.

**Always read AGENTS.md first** before making code suggestions. It contains the
constraint index, variable naming, the constraint (13) correction, and code conventions.

## Code Assistant Rules

### Python (src/, experiments/)
- All optimization code uses **Pyomo** with `ConcreteModel`. Never suggest PuLP or CVXPY.
- Variable naming: `m.x[i,j]`, `m.z[i,j,d,c]`, `m.y[j,d,c]`, `m.mega[j,d,c]`.
- Never hardcode solver names; always accept a `solver_name` parameter defaulting to `'cplex'`.
- Constraint methods follow the pattern `_add_c{N}_{description}(self)`.
- All results CSV files go to `results/tables/`, figures to `results/figures/`.
- Prefer `pandas` for tabular results, `matplotlib` for plots.
- Use `tqdm` for progress bars in any loop over instances.
- Do not add `print()` statements inside model-building methods; use `logging`.

### LaTeX (paper/)
- Use `elsarticle` document class (Elsevier EJOR format).
- All equations use `align` or `equation` environments (never `eqnarray`).
- Cite with `\cite{khaled2018compact}` for the base paper.
- Tables use `booktabs` (`\toprule`, `\midrule`, `\bottomrule`).
- Figures use `\includegraphics` from `paper/figures/`.
- Each section is `\input`'d from `sections/{N}_{name}.tex`.

### Mathematical Notation (docs/ and paper/)
- Flights: set $\mathcal{F}$, index $i$
- Aircraft: set $\mathcal{P}$, index $j$
- Airports: set $\mathcal{A}$, index $k$
- Days: set $\mathcal{D}$, index $d$
- Check types: set $\mathcal{C} = \{A, B, C, D\}$, index $c$
- Decision variables: $x_{ij}$, $z_{ijdc}$, $y_{jdc}$, $\gamma_{jdc}$ (mega)
- Big-M: $M_{dd'}$ (computed per day-pair, not a global constant)

## Constraint (13) — Use Explicit Profiles

Do not silently replace the published row or the historical endpoint split with
a claimed correction. Preserve them as named controlled profiles:

- `khaled_printed`: original single row on the printed day-pair domain;
- `endpoint_split`: the historical two-row alternative, not an exact fix;
- `corrected_a_interval`: all day pairs plus an opening prefix for exact A-hour
  coverage under the day-boundary policy;
- `option_a` / `option_b`: corrected A-only hour rows plus their timing policy.

For corrected A-only code, use strict interval rows and opening prefixes:

```python
m.c13.add(t_sum <= T_max + M * interior_checks)
m.c13b.add(initial + prefix <= T_max + M0 * earlier_checks)
```

The corrected prefix relaxes only on checks strictly before its end day. Its
big-M must include pre-horizon exposure. Validate profile-specific results with
the independent certificate replay, not with row satisfaction alone.

## Experiment Conventions

- All table-reproduction scripts accept `--quick` (runs h=7,15 only; p=10,20 only)
  and `--full` (complete Khaled et al. grid).
- Output CSV columns must always include:
  `stem, P, H, F, vars, constraints, nodes_max, gap_pct, cpu_s, objective`.
- Validate results against `results/reference/output3_batch_summary.csv`.

## Do Not

- Do not suggest adding features not asked for.
- Do not suggest changing the `stable_seed` formula.
- Do not suggest using `Model_28Oct.py`; it is a legacy file kept for archival.
- Do not write debug/temporary scripts to `src/`; use `experiments/` or a notebook.
