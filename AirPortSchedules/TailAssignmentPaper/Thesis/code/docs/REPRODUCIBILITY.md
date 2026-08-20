# Computational Reproduction Guide

Run every command below from the repository root in Windows PowerShell.

## 1. Environment

```powershell
py -3 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

HiGHS is the current exact backend for the fresh exact-feasible, LP, sensitivity,
and arc/path results. The dependency is supplied by `highspy` in
`requirements.txt`.

## 2. Constructive feasible instances

The commands below create routing-first instances. They are preferable to the
legacy random grid whenever exact MILP feasibility is required.

```powershell
.\.venv\Scripts\python.exe src\generate_feasible_instances.py 0.5 4 7 1 --maintenance-families A --output-dir data\feasible_family_smoke\A
.\.venv\Scripts\python.exe src\generate_feasible_instances.py 0.5 4 7 1 --maintenance-families AB --output-dir data\feasible_family_smoke_ab\AB
.\.venv\Scripts\python.exe src\generate_feasible_instances.py 0.5 4 7 1 --maintenance-families ABCD --output-dir data\feasible_family_smoke_abcd\ABCD
```

Do not overwrite canonical files merely to rerun the paper. Use a temporary
output directory when testing generator changes.

## 3. Phase 2 heuristic comparison

Quick Tier-1 run:

```powershell
.\.venv\Scripts\python.exe experiments\phase2_comparison.py --quick --solver highs --time-limit 300
```

Full 25-instance run:

```powershell
.\.venv\Scripts\python.exe experiments\phase2_comparison.py --solver highs --time-limit 300
```

Outputs are written below `results/tables/phase2/`. Chapter 7 Tables
`phase2_summary`, `phase2_quick_objectives`, and `phase2_full` are manually
typeset summaries of those CSV files. The Phase-1 matrix and summary use the
canonical JSON files in `data/phase1_25_forced/`; they are descriptive data
inventories, not solver-generated tables.

## 4. Exact-feasible comparison

```powershell
.\.venv\Scripts\python.exe experiments\run_exact_feasible.py
.\.venv\Scripts\python.exe experiments\analyze_exact_feasible.py
```

Authoritative output:

```text
results/tables/exact_feasible/comparison.csv
```

This CSV supplies Chapter 7 Table `exact_feasible_comp`. The driver uses HiGHS
with a 120 s per-instance limit for both classical and integrated MILPs.

## 5. LP lower bounds

```powershell
.\.venv\Scripts\python.exe experiments\step4_lp_lower_bounds.py
.\.venv\Scripts\python.exe experiments\step4_analyze_bounds.py
```

Authoritative output:

```text
results/tables/step4_lp_lower_bounds.csv
```

This CSV supplies Table `lp_lower_bounds`. The experiment uses HiGHS with a
30 s limit for each LP relaxation.

## 6. Phase 3 scalability

Quick density-0.5 run:

```powershell
.\.venv\Scripts\python.exe experiments\phase3_scalability.py --quick --solver highs --time-limit 120
```

Full available DataCplex grid:

```powershell
.\.venv\Scripts\python.exe experiments\phase3_scalability.py --solver highs --time-limit 120
```

Outputs:

```text
results/tables/phase3/phase3_scalability.csv
results/tables/phase3/phase3_size_growth.csv
```

These supply Table `phase3_size` and Figure `phase3_scalability`. The current
script writes CSVs; the figure values are manually plotted in the LaTeX/TikZ
source from `phase3_size_growth.csv`.

## 7. Phase 4 sensitivity

```powershell
.\.venv\Scripts\python.exe experiments\step5_sensitivity_analysis.py
.\.venv\Scripts\python.exe experiments\step5_analyze_sensitivity.py
```

Authoritative output:

```text
results/tables/step5_sensitivity_analysis.csv
```

The driver runs 60 HiGHS models (four curated exact-feasible bases, one-factor
threshold/duration/capacity variants, 120 s each). It supplies Table
`sensitivity`. Certified infeasible variants are parameter frontier results,
not solver timeouts.

## 8. Phase 5 arc versus path

Generate 10 repeated paired observations per instance:

```powershell
.\.venv\Scripts\python.exe experiments\step6_arc_vs_path.py --repeats 10 --solver highs --time-limit 120 --output results\tables\step6_arc_vs_path.csv
```

Aggregate the observations and generate every Phase-5 figure:

```powershell
.\.venv\Scripts\python.exe experiments\step6_analyze_arc_vs_path.py --input results\tables\step6_arc_vs_path.csv --figure-dir paper\figures
```

Outputs:

```text
results/tables/step6_arc_vs_path.csv
results/tables/step6_arc_vs_path_aggregate.csv
results/tables/step6_arc_vs_path_summary.csv
paper/figures/step6_runtime_comparison.png
paper/figures/step6_speedup_vs_size.png
paper/figures/step6_model_size.png
paper/figures/step6_timing_decomposition.png
paper/figures/step6_route_growth.png
paper/figures/step6_objective_parity.png
```

The aggregate CSV supplies Table `arc_vs_path`. Timings are end-to-end medians
and IQRs over ten complete rebuild-and-solve repeats. The raw CSV is retained
for audit.

## 9. Constraint 13 comparison

Run the two formulations on a targeted instance:

```powershell
.\.venv\Scripts\python.exe src\model.py --mode milp --data data\instances\ABCD_near_threshold_test.json --solver highs --time-limit 300 --use-paper-c13 --no-show
.\.venv\Scripts\python.exe src\model.py --mode milp --data data\instances\ABCD_near_threshold_test.json --solver highs --time-limit 300 --no-show
```

Run the analytical loophole instance:

```powershell
.\.venv\Scripts\python.exe src\model.py --mode milp --data data\instances\c13_loophole_test.json --solver highs --time-limit 300 --use-paper-c13 --no-show
.\.venv\Scripts\python.exe src\model.py --mode milp --data data\instances\c13_loophole_test.json --solver highs --time-limit 300 --no-show
```

Table `c13_comparison` is manually typeset from these direct runs. The
constraint-count difference verifies that the toggle is active. The targeted
loophole result must also be checked with the independent maintenance validator
before accepting the paper-C13 schedule.

## 10. Full hierarchy status table

```powershell
.\.venv\Scripts\python.exe experiments\run_batch.py --mode milp --solver highs --time-limit 300 --input-dir data\instances --output-dir results\tables --pattern "ABCD_*_test.json" --label hierarchy_highs
```

Output:

```text
results/tables/_batch_hierarchy_highs.csv
```

This supplies Table `hierarchy`. The current expected classification is four
optimal and three certified infeasible cases, with no indexing or solver
errors.

## 11. Legacy heuristic and stress tables

Tables `heu_benchmark`, `heuristic_only`, `boundary_suite`, `heavy_suite`, and
`dense_heavy_suite` are manually typeset from archived CSVs such as:

```text
results/tables/oop_all_methods_compare_v2.csv
results/tables/oop_heavy_suite_cplex.csv
results/tables/oop_dense_suite_cplex.csv
results/tables/_dense_h7.csv
results/tables/_dense_h15.csv
results/tables/_dense_h21.csv
results/tables/_dense_h30.csv
```

They were produced with an earlier CPLEX shell environment. They are retained
as archived evidence and cannot be freshly reproduced with the current machine
unless that CPLEX executable is restored. Solver provenance is stated in the
manuscript captions/text.

## 12. Manuscript build

```powershell
Push-Location prev
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
Pop-Location
```

Expected output is `prev/main.pdf`. A valid final build has no undefined
references, undefined citations, or duplicate labels.
