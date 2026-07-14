---
mode: agent
description: Draft or extend a section of the TAP scientific paper. Reads existing LaTeX, identifies gaps, and fills them with mathematically precise text.
---

# Task: Write / Extend Paper Section

## Context
You are assisting with the scientific paper:
  "Correcting and Extending the Compact Tail Assignment Model"
  Target venue: European Journal of Operational Research (Elsevier)

Read **AGENTS.md** and **docs/model_math.tex** before writing.

## Paper Structure
paper/sections/
  1_intro.tex          — motivation, airline planning pipeline, TAP definition
  2_literature.tex     — comparison with 3 formulation families
  3_basic_model.tex    — constraints C1–C4, Propositions 1 & 2
  4_maintenance_model.tex — constraints 8–15 + CORRECTION of eq.(13)
  5_hierarchy_extension.tex — A/B/C/D hierarchy; C13b; C14b
  6_heuristics.tex     — greedy/insertion heuristic; complexity
  7_computational.tex  — reproduced + corrected Tables 5/6/10/11; new results
  8_conclusion.tex     — contributions, limitations, future work

## Instructions

1. Read the target section file (e.g., `paper/sections/4_maintenance_model.tex`).
2. Read the corresponding math from `docs/model_math.tex`.
3. If results tables are available, read `results/tables/*.csv` and use the numbers.
4. Draft or expand the section following Elsevier EJOR style.
5. For Section 4 specifically, include:
   - The original constraint (13) from Khaled et al. in an `align` environment.
   - A proof/counter-example showing it is incorrect.
   - The corrected formulation (two-constraint split).
   - Reference to the implementation in `src/model.py`.
6. Use `\cite{khaled2018compact}` for the base paper.
7. Do NOT invent numerical results; only use numbers from `results/tables/`.

## LaTeX Conventions
- Document class: `elsarticle`
- Theorems: `\begin{proposition}...\end{proposition}`
- Tables: `booktabs` with `\toprule / \midrule / \bottomrule`
- Equations: `align` environment, numbered with `\label{eq:c13_original}` etc.
- Cross-references: `\eqref{}` for equations, `\cref{}` for sections/tables.

## Deliverable
Updated `paper/sections/{N}_{name}.tex` with complete, publication-quality LaTeX.
Mention any missing numbers (as `\todo{...}`) that require running experiments first.
