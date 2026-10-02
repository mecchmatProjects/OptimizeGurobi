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
.\.venv\Scripts\python.exe experiments\step4_lp_lower_bounds.py --solver highs --time-limit 30 --output results/tables/step4_lp_lower_bounds.csv
.\.venv\Scripts\python.exe experiments\step4_analyze_bounds.py
```

Authoritative output:

```text
results/tables/step4_lp_lower_bounds.csv
```

This CSV supplies Table `lp_lower_bounds`. The experiment uses HiGHS with a
30 s limit for each LP relaxation.

New runs refuse to overwrite an existing CSV without `--overwrite`. Preserve
archived source CSVs: use a new output path instead. The current default cap is
three days; use `--max-hour-check-deferral-days none` for unrestricted runs.

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

## 13. Correctness review and user-run long experiments

Run the bounded regression suite first:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

The default A/B deferral cap remains three days. Explicit `none` means the full
remaining horizon; `0` means same-day checks. A finite cap and the experimental
station-wait reachability filter restrict the model, so do not pool their
results with unrestricted or formulation-equivalent runs. The current combined
bound-study variant excludes that filter; historical combined measurements do
not retroactively describe this new configuration.

### CPLEXamp launch settings

These jobs are manual long experiments, not part of ordinary pytest. The
10,000-second budget applies to each solver call, not the complete batch.
Unrestricted 40-aircraft builds can exhaust RAM. Start with model-size checks;
if necessary select one file instead of the three-file wildcard. Do not silently
introduce a cap after a build failure.

```powershell
$py = '.\.venv\Scripts\python.exe'
$exe = 'F:\Progs\IBM.ILOG.CPLEX.for.AMPL.v12.6-EAT\CPLEXamp.exe'
$dest = 'results/tables/review_20261002'
New-Item -ItemType Directory -Force $dest | Out-Null
Test-Path $exe

# Structural check only: no heuristic or solver run.
& $py experiments/run_strengthening_bounds.py --input-dir data/Long_family --pattern '*h30*.json' --solver cplexamp --executable $exe --time-limit 10000 --max-hour-check-deferral-days none --build-only --output "$dest/strength_uncapped_build.csv"

# Full paired variants: heuristic, LP, and MILP. This can take many hours.
& $py experiments/run_strengthening_bounds.py --input-dir data/Long_family --pattern '*h30*.json' --solver cplexamp --executable $exe --time-limit 10000 --max-hour-check-deferral-days none --tee --output "$dest/strength_uncapped_long.csv" 2>&1 | Tee-Object "$dest/strength_uncapped_long.console.log"

# Classical routing comparison, not reproduction of original paper hardware.
& $py experiments/run_khaled_30day.py --full --input-dir data/Long_family --instances md30_p20_h30_r1.json ld30_p30_h30_r1.json xd30_p40_h30_r1.json --solver cplexamp --executable $exe --time-limit 10000 --overlap none --output "$dest/khaled_30day_classical.csv" 2>&1 | Tee-Object "$dest/khaled_30day_classical.console.log"
```

For the separate three-day sensitivity study, replace `none` with `3` and use
`strength_capped3_long.csv`. These are different feasible sets, not interchangeable
baseline runs. PNGs belong in `results/figures/`; thesis-generated figures are
copied/generated into `Thesis/figures/` by the analyzer.

### Routing preflight on/off comparison

The optional screen solves a maintenance-free routing LP and skips only proven
LP infeasibility. It cannot certify integer feasibility. Time limits, unknown
statuses and errors retain the instance. It is disabled by default until paired
total-wall measurements justify a performance claim. An optimal classical
preflight result is reused if the classical LP itself was requested.

```powershell
$common = @('--input-dir', 'data/Long_family', '--pattern', '*h30*.json',
			'--formulation', 'integrated', '--solver', 'cplexamp',
			'--executable', $exe, '--time-limit', '10000',
			'--max-hour-check-deferral-days', 'none', '--tee')

# Start with r1. Repeat for r2/r3, reversing order on alternate repeats.
& $py experiments/step4_lp_lower_bounds.py @common --include-routing-infeasible --output "$dest/lp_uncapped_off_r1.csv" 2>&1 | Tee-Object "$dest/lp_uncapped_off_r1.console.log"
& $py experiments/step4_lp_lower_bounds.py @common --routing-preflight --preflight-time-limit 60 --output "$dest/lp_uncapped_on_r1.csv" 2>&1 | Tee-Object "$dest/lp_uncapped_on_r1.console.log"
```

Each output has a `.metadata.json` and `.log` sidecar. Step 4 additionally writes
an `.audit.csv`, including skipped instances and preflight time. Completed rows
are flushed immediately. Append `--resume` to the original command to continue
with matching source/input hashes, solver version and options. Completed
time-limited attempts are retained; errors can be retried. Use a fresh output
name for a new budget/configuration. `--overwrite` intentionally discards the
old file and must not be used on archived evidence.

Compare total wall time, including preflight and both model builds, and report
skipped/missing/error/timeout counts. Solver time alone does not establish a
preflight speedup. Infeasible-heavy families may benefit while feasible-only
families pay screening overhead.

### Results returned for later thesis integration

Retain raw CSVs, audit CSVs, metadata and console logs. Record the solver edition
and licence restrictions separately; executable availability alone does not
certify that a long run is permitted. Do not mix the new CPLEXamp observations
with archived HiGHS/Gurobi timings or mix finite and unrestricted caps.

After validating the returned classical CSV, generate its table without solving:

```powershell
& $py experiments/run_khaled_30day.py --table-csv "$dest/khaled_30day_classical.csv" --latex-output Thesis/tables/khaled_30day_classical.tex
```

The Small/Medium bracket currently comes from the archived source CSVs. The
nonzero Medium LP--MILP gaps and zero residual solver gaps are distinct. New
long results must first pass provenance, finite-bound and coverage checks; only
then regenerate plots/tables and update Chapters 6/8. The existing overlap-M20
and P20/H39 tables are excluded from this review's provenance work.

### Code snapshot policy

Use maintained `src/`, `experiments/` and `tests/` for every new experiment.
`Thesis/src/` and `Thesis/code/` are frozen archived copies, not live mirrors.
Package a new release only after validation, without overwriting either tree:

```powershell
& $py experiments/package_thesis_code.py --output Thesis/code/releases/review_20261002 --dry-run
& $py experiments/package_thesis_code.py --output Thesis/code/releases/review_20261002
```

The new release contains a source/environment manifest and per-file SHA256
hashes. Existing directories are rejected rather than overwritten. Solver temp
files, canonical instances, logs and thesis ZIP/Word deliverables are not copied.
