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

### Solver requirement for unrestricted long models

Both `CPLEX.exe` and `CPLEXamp.exe` in
`F:\Progs\IBM.ILOG.CPLEX.for.AMPL.v12.6-EAT` are **the same 32-bit binary**:
their SHA256 hashes are identical and both PE machine headers are `0x014C`.
Changing only the executable name cannot change memory limits. Despite its
name, this `CPLEX.exe` is the same AMPL/ASL driver, not the interactive CPLEX
CLI; it would still require the `cplexamp` Pyomo interface. A diagnostic
run of the unrestricted L-30 LP (941,430 variables and 29,436,650 nonzeros)
confirmed `internalSolverError` with the retained solution-file message
`ran out of memory`. This is not a normal time limit. Increasing the time
budget does not remove the 32-bit address-space limit. The locally installed
CPLEX Python backend is Community Edition and fails above its size limit.

The usable CPLEX 12.9 installation has now been found at
`F:\LT\IJOC_SDDP_for_Multi-Echelon_Lot-Sizing_with_Component_Substitution\cplex\CPLEX_Studio\cplex\bin\x64_win64\cplex.exe`.
Metadata confirms version 12.9, and the 14-day integrated LPs with up to
304,960 variables solved optimally. Use `--solver cplex` with this executable,
not `cplexamp` and not the separate size-restricted Python package. This is
the recommended local backend for the controlled comparisons below. It does
not guarantee optimality or sufficient RAM on every 30-day model.

HiGHS remains an explicit alternative. Never mix solver versions, thread
settings, caps or revised source hashes in a paired comparison.

### Baseline-commit reproduction with CPLEX 12.9

The routine protocol below now matches the model defaults of commit `828d3f0`
("updates from Gurobi side"): **three-day A/B deferral**, automatic CPLEX
threads, no routing preflight and no optional strengthening flags in the Step 4
baseline. To match its LP procedure, explicitly select
`--lp-relaxation legacy-unit-bounds` as in Stages A/B below. The earlier version
of this guide recommended `none` and four
threads; that was a different, larger protocol, not a restoration of the old
one. Explicit `none` remains a supported unrestricted research setting, never
silently converted back to three days.

The actual original source and current source were compared on md14:
three-day models have identical variable bounds, objective and constraint
hashes, 52,460 variables, 55,452 constraints and 42,700 triggers. With `none`,
the current model has 89,220 variables, 70,132 constraints and 79,460 triggers.
Recorded construction CPU was 2.97 versus 2.92 seconds for original/current
cap-three models in this one check; it is not a statistically established solve
speedup. Source-backed evidence is in
`results/tables/review_20261003_perf/baseline_828d3f0_model_parity.csv`.

Matching a model does not guarantee identical optimizer time. If an archived
run used Gurobi, CPLEX 12.9 is a different solver; reproduce the solver/version,
algorithm, budget and hardware as well before attributing a difference to code.

The LP procedures also differ. Commit `828d3f0` replaced every binary variable's
bounds with `[0,1]` during relaxation, including variables whose upper bound was
zero in the model. The current standard transformation preserves those zero
bounds. Integer models match, but the old LP is weaker and may optimize faster
or give a lower bound of different strength. The initial integer-model parity
check alone did not prove LP parity; the regression now checks both procedures
against the actual original source.

`legacy-unit-bounds` explicitly reproduces that older, expanded relaxation.
Its optimum is still a lower bound for the integer model, but it is not the
objective of the bound-preserving LP relaxation. Do not describe differences
as a code-only speedup or label its gap as the standard integrality gap. The
default remains `preserve-bounds` for new scientific runs; legacy mode is an
opt-in reproduction setting and is recorded in CSV and metadata.

Let existing jobs finish before collecting new timings. Run exactly one large
job at a time. Do not execute every command block in this guide as one script.
The stages below have separate output files and purposes.

1. Run regression tests and choose one protocol: solver, threads, cap, checks,
	input pattern and time budget. Record the actual settings, not just a name
	such as `uncapped`. Keep all four checks unless check scope is the experiment.
2. Start with 14-day LPs. They are an economical correctness and throughput
	baseline; do not pay for four LP/MILP solves per instance just to obtain a
	lower bound. Use exact `*h14*.json` rather than the ambiguous `*h1*.json`.
3. Build the 30-day models without solving and review their sizes before
	attempting LPs. The build-only pass is a one-time resource check, not a step
	to repeat before every run. `built` proves construction only.
4. Run 30-day LPs without routing preflight for this tested family. Preflight
	is useful only if enough proven infeasible instances are eliminated to repay
	its cost; the recorded 14-day pair showed no benefit.
5. Run the full matched heuristic/LP/MILP variant study only when all those
	measurements are required. Use three isolated repeats for timing claims,
	alternating baseline/combined order as described below.
6. Run classical routing separately. Validate the returned CSVs and metadata
	before generating thesis tables; retain failures and time-limited results.

Initialize these variables in the same PowerShell terminal as the commands:

```powershell
$py = '.\.venv\Scripts\python.exe'
$exe = 'F:\LT\IJOC_SDDP_for_Multi-Echelon_Lot-Sizing_with_Component_Substitution\cplex\CPLEX_Studio\cplex\bin\x64_win64\cplex.exe'
$threads = 0
$cap = '3'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$dest = "results/tables/cplex129_baseline828_${stamp}_cap${cap}_t${threads}"
if (-not (Test-Path $py)) { throw 'Run from the workspace root with .venv installed.' }
if (-not (Test-Path $exe)) { throw 'The CPLEX 12.9 executable was not found.' }
New-Item -ItemType Directory -Force $dest | Out-Null
& $py -m pytest tests -q
if ($LASTEXITCODE -ne 0) { throw 'Regression tests failed; do not start experiments.' }
```

For CPLEX, `--threads 0` means automatic, matching the previous no-override
policy; it does not disable threads. Positive values such as `1` or `4` are
separate resource/solver ablations, with new output directories. HiGHS and
Gurobi require positive values in this wrapper; omit their thread flag to use
backend defaults. Do not run different thread counts concurrently. The native
10,000-second budget applies per solve, not to
construction, model transfer, the whole instance or the full batch.

#### Stage A: economical 14-day LP baseline
```powershell
& $py experiments/step4_lp_lower_bounds.py --input-dir data/Long_family --pattern '*h14*.json' --formulation integrated --solver cplex --executable $exe --threads $threads --time-limit 10000 --max-hour-check-deferral-days $cap --lp-relaxation legacy-unit-bounds --output "$dest/lp_h14_legacy_r1.csv" 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object "$dest/lp_h14_legacy_r1.console.log"
if ($LASTEXITCODE -ne 0) { throw 'LP run failed; inspect the CSV and log before continuing.' }
```

Step 4's original commit defaults to the full trigger-aircraft domain. The
baseline command deliberately omits `--sparse-z` to match it. As a separate
exact domain-reduction ablation, `--sparse-z` removes maintenance triggers on
incompatible assignment arcs, matching the model class's default sparse-domain
setting; it is not a deferral cap.
Keep that flag fixed across repeats and preflight comparisons. Do not add the
experimental `--reachability` restriction to an equivalence comparison.
`--tight-c13-m` and `--strong-conflicts` remain optional ablations; do not assume
that additional constraints always reduce total time.

For a controlled relaxation-strength comparison, run the identical command
with `--lp-relaxation preserve-bounds` and a new `lp_h14_preserve_r1.csv` output.
Keep the cap, threads, budget, input hashes and all model flags fixed. Compare
both bound values and total wall time, not timing alone. Repeat in alternating
order before drawing a solver-performance conclusion.

#### Stage B: 30-day structural check and LPs

```powershell
& $py experiments/run_strengthening_bounds.py --input-dir data/Long_family --pattern '*h30*.json' --solver cplex --executable $exe --threads $threads --max-hour-check-deferral-days $cap --build-only --output "$dest/build_h30.csv"
if ($LASTEXITCODE -ne 0) { throw 'Model construction failed.' }

# Run only after reviewing build_h30.csv and available memory.
& $py experiments/step4_lp_lower_bounds.py --input-dir data/Long_family --pattern '*h30*.json' --formulation integrated --solver cplex --executable $exe --threads $threads --time-limit 10000 --max-hour-check-deferral-days $cap --lp-relaxation legacy-unit-bounds --output "$dest/lp_h30_legacy_r1.csv" 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object "$dest/lp_h30_legacy_r1.console.log"
if ($LASTEXITCODE -ne 0) { throw 'LP run failed; inspect the CSV and log.' }
```

To limit peak workload, replace the wildcard with one exact filename, for
example `md30_p20_h30_r1.json`, and use an instance-specific output name. This
reduces the selected workload without changing that instance's feasible set.

#### Stage C: full bound bracket and strengthening comparison

```powershell
& $py experiments/run_strengthening_bounds.py --input-dir data/Long_family --pattern '*h30*.json' --solver cplex --executable $exe --threads $threads --time-limit 10000 --max-hour-check-deferral-days $cap --tee --output "$dest/bracket_h30_r1.csv" 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object "$dest/bracket_h30_r1.console.log"
if ($LASTEXITCODE -ne 0) { throw 'Bound-study run failed; inspect its retained records.' }
```

This computes a heuristic plus LP/MILP for baseline and combined configurations.
It currently rebuilds each model per solve: do not interpret four solver calls
as a code slowdown relative to a single Step 4 LP. Complete heuristics become
upper bounds only after model-certificate validation; partial costs are not
upper bounds. Baseline and combined integer objectives and bound validity must
be checked before claiming formulation equivalence from the speed results.

Stage C intentionally includes its own LPs; those are matched to its declared
variants and use the bound-preserving transformation. Stages A/B legacy LPs
must not be substituted for these standard LP objectives. Stages A/B are
separate diagnostics/LP-only baselines, not extra
mandatory work every time Stage C is repeated. For a MILP-only targeted study,
use `--mode milp --skip-heuristic`, but report the omitted measurements and do
not substitute LPs from a different configuration.

For isolated variant timings use `--variant baseline` and `--variant combined`
in separate runs with `r1`, `r2`, `r3` output names. Run baseline then combined
for r1, combined then baseline for r2, and baseline then combined for r3. Do not
pool repeats into an analyzer that expects one observation per instance. Report
median/IQR of end-to-end time separately from solver-reported timing.

#### Stage D: classical routing comparison

```powershell
& $py experiments/run_khaled_30day.py --full --input-dir data/Long_family --instances md30_p20_h30_r1.json ld30_p30_h30_r1.json xd30_p40_h30_r1.json --solver cplex --executable $exe --threads $threads --time-limit 10000 --overlap none --output "$dest/classical_h30_r1.csv" 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object "$dest/classical_h30_r1.console.log"
if ($LASTEXITCODE -ne 0) { throw 'Classical run failed; inspect its CSV and log.' }
```

This is a classical-model comparison on these synthetic inputs, not a hardware
or original-data reproduction of Khaled et al. The solver's validated routing
start is distinct from an optimality certificate.

Keep `$dest` unchanged when resuming. Rerunning the initialization block creates
a new timestamped folder and therefore a new experiment, not a resume. Add
`--resume` to the exact original runner command and `-Append` to `Tee-Object`;
do not change the source, flags, threads, cap, pattern or budget. Never use
`--overwrite` on publication evidence.

#### Separate unrestricted study

Use `--max-hour-check-deferral-days none` only when the full remaining horizon
is the intended model, with a new output directory labelled `capnone` and the
same declared solver/thread settings. This is not an equivalent fast-mode
replacement for the original three-day model. Do not infer a code slowdown by
comparing a capped baseline solve with an unrestricted solve. Existing `none`
outputs remain valid measurements of their declared model; do not relabel them
as capped results or change their metadata after the fact.

### Optional alternative: 64-bit HiGHS

Run the following from the workspace root. Each code block requires its setup
variables to be initialized in the **same terminal**. The `&` call operator
is required before `$py`. The output directory is created automatically by the
runner; it is also created here for console capture.

```powershell
$py = '.\.venv\Scripts\python.exe'
$dest = 'results/tables/review_20261002'
if (-not (Test-Path $py)) { throw 'Run from the workspace root with .venv installed.' }
New-Item -ItemType Directory -Force $dest | Out-Null

# Structural check only: no solver is started.
& $py experiments/run_strengthening_bounds.py --input-dir data/Long_family --pattern '*h30*.json' --solver highs --threads 1 --max-hour-check-deferral-days none --build-only --output "$dest/strength_uncapped_highs_build.csv"

# Full unchanged unrestricted model: explicit 64-bit backend and one thread.
& $py experiments/run_strengthening_bounds.py --input-dir data/Long_family --pattern '*h30*.json' --solver highs --threads 1 --time-limit 10000 --max-hour-check-deferral-days none --tee --output "$dest/strength_uncapped_highs.csv" 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object "$dest/strength_uncapped_highs.console.log"

# Classical routing comparison on the same three instances.
& $py experiments/run_khaled_30day.py --full --input-dir data/Long_family --instances md30_p20_h30_r1.json ld30_p30_h30_r1.json xd30_p40_h30_r1.json --solver highs --threads 1 --time-limit 10000 --overlap none --output "$dest/khaled_30day_classical_highs.csv" 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object "$dest/khaled_30day_classical_highs.console.log"
```

For a bounded launch check before the full batch:

```powershell
& .\.venv\Scripts\python.exe experiments/run_strengthening_bounds.py --input-dir data/Long_family --pattern ld30_p30_h30_r1.json --solver highs --threads 1 --time-limit 60 --max-hour-check-deferral-days none --mode lp --variant baseline --skip-heuristic --tee --output results/tables/review_20261002/highs_launch_check.csv
```

The same 941,430-variable LP was verified to reach HiGHS presolve and terminate
normally on a short budget, rather than fail with the CPLEX memory error. That
check supplied no certified bound or optimal solution. Construction and solver
transfer took several minutes outside the internal solver budget. The X-40
model is larger and can still exhaust physical/virtual memory; no formulation
or solver can be guaranteed to finish within the machine's resources. Release
unneeded applications before long runs, and keep experiments sequential.

Routine progress and application logging now use stdout to reduce PowerShell
5.1's misleading `NativeCommandError` wrapping of stderr. Real failures remain
recorded in the CSV. Check `$LASTEXITCODE` after each launch; do not execute the
next job after a nonzero exit.

These jobs are manual long experiments, not part of ordinary pytest. The
10,000-second budget applies to each solver call, not the complete batch.
For the separate three-day sensitivity study, replace `none` with `3` and use
`strength_capped3_highs.csv`. These are different feasible sets, not interchangeable
baseline runs. PNGs belong in `results/figures/`; thesis-generated figures are
copied/generated into `Thesis/figures/` by the analyzer.

### Routing preflight on/off comparison

This is an optional ablation, not the recommended routine workflow. The screen
solves a maintenance-free routing LP and skips only proven
LP infeasibility. It cannot certify integer feasibility. Time limits, unknown
statuses and errors retain the instance. It is disabled by default until paired
total-wall measurements justify a performance claim. An optimal classical
preflight result is reused if the classical LP itself was requested.

```powershell
$py = '.\.venv\Scripts\python.exe'
$exe = 'F:\LT\IJOC_SDDP_for_Multi-Echelon_Lot-Sizing_with_Component_Substitution\cplex\CPLEX_Studio\cplex\bin\x64_win64\cplex.exe'
$threads = 4
$dest = 'results/tables/review_20261003_preflight_cplex129_t4'
New-Item -ItemType Directory -Force $dest | Out-Null
$common = @('--input-dir', 'data/Long_family', '--pattern', '*h30*.json',
			'--formulation', 'integrated', '--solver', 'cplex',
			'--executable', $exe, '--threads', "$threads", '--time-limit', '10000',
			'--max-hour-check-deferral-days', 'none', '--sparse-z', '--tee')

# Start with r1. Repeat for r2/r3, reversing order on alternate repeats.
& $py experiments/step4_lp_lower_bounds.py @common --include-routing-infeasible --output "$dest/lp_uncapped_off_r1.csv" 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object "$dest/lp_uncapped_off_r1.console.log"
if ($LASTEXITCODE -ne 0) { throw 'Preflight-off run failed.' }
& $py experiments/step4_lp_lower_bounds.py @common --routing-preflight --preflight-time-limit 60 --output "$dest/lp_uncapped_on_r1.csv" 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object "$dest/lp_uncapped_on_r1.console.log"
if ($LASTEXITCODE -ne 0) { throw 'Preflight-on run failed.' }
```

Each output has a `.metadata.json` and `.log` sidecar. Step 4 additionally writes
an `.audit.csv`, including skipped instances and preflight time. Completed rows
are flushed immediately. Append `--resume` to the original command to continue
with matching source/input hashes, solver version and options. Completed
time-limited attempts are retained; errors can be retried. Use a fresh output
name for a new budget/configuration. `--overwrite` intentionally discards the
old file and must not be used on archived evidence.

Solver failures such as `internalSolverError` are not completed attempts and
are retried by compatible resume. The bound/classical runners stop on the
first failure by default and return a nonzero exit; `--continue-on-solver-error`
is an explicit diagnostic override. The CSV now includes solver messages and
return codes. For file-based solver diagnostics add `--keepfiles`; artifacts
are stored below the output's `.solver/` directory. Use `--mode lp` or `milp`
and `--variant baseline` or `combined` to isolate one case.

The source/schema repairs mean that the old failed CPLEX CSV cannot be resumed
with the new code. Preserve it and use a new filename. Never bypass source/hash
checks to mix different implementations. When resuming a new compatible run,
use `Tee-Object -Append` to retain its earlier console output.

Compare total wall time, including preflight and both model builds, and report
skipped/missing/error/timeout counts. Solver time alone does not establish a
preflight speedup. Infeasible-heavy families may benefit while feasible-only
families pay screening overhead.

### Performance investigation and timing definitions (2026-10-03)

The recorded CPLEX 12.9 14-day repeat-2 pair has identical input hashes, caps,
model sizes and integrated LP objectives. Preflight-off totals 296.81 seconds;
preflight-on totals 331.25 seconds, approximately 11.6% more. No instance was
skipped. The screens themselves account for 18.57 seconds; the remaining
difference includes ordinary target-solve timing variation. This pair does not
support enabling preflight by default. It remains opt-in; omit
`--routing-preflight` for known-feasible families when filtering has no value.

Routing-only construction now skips unused maintenance caches. An alternating
three-repeat construction check on md14 (20 aircraft, 14 days) reduced median
process CPU time from 0.781 to 0.641 seconds and removed 63,280 unused C8 cache
entries. Routing constraint hashes, variable counts and constraint counts are
identical. These measurements are in
`results/tables/review_20261003/performance_routing_build.csv`; they were recorded
while another solver job was active and are not an isolated solver-speed study.

Integrated-only preflight now uses a constant objective: it establishes routing
LP feasibility without optimizing assignment costs. If the classical cost LP
is requested, the screen still optimizes that cost and its result is reused.
The constant-objective result is never substituted for a classical cost bound.
Step 4 and LP rows in the paired bounds runner also avoid loading every LP variable when finite optimizer bounds are
already available; interfaces omitting those bounds retain the solution-load
fallback. Exact routing/integrated constraint parity and bound tests cover these
changes. Integrated constraints, check requirements, cap defaults and solver
parameters have not been weakened or silently changed.

Timing columns mean:

- `build_s`: construction/preparation (Step 4 also includes LP relaxation and
	model counting before the solver call).
- `runtime_s`: wall time of the complete solver call, including writer/transfer,
	optimization and result parsing/loading; this is not purely optimizer time.
- `solver_reported_s`: the backend's `time` field when available; it is not
	assumed to use identical wall/CPU semantics across all solvers.
- `wall_s`: complete target build-and-solve time.
- `preflight_s`: screening wall time, charged once per instance.
- `total_wall_s`: target wall time plus charged screening overhead.

Earlier CSVs may store backend-reported time in `runtime_s` and may lack input,
option and source hashes. Do not infer a code slowdown from those numbers alone.
Compare the same solver/version, threads, input hashes, cap and model flags,
using end-to-end wall time. A three-day cap and explicit `none` are different
models. A full bound study performs both LP and MILP for two variants, whereas
Step 4 computes only LPs; their complete job durations are not comparable.

The baseline-commit investigation additionally found the implicit cap-three
behaviour and the unit-bound LP reset described above. Changing the cap or LP
relaxation policy changes the optimized problem even when input files and
solver names match. Always check `lp_relaxation` before pooling Step 4 bounds.

For targeted experiments the bound-study runner already supports `--mode lp`
or `milp`, `--variant baseline` or `combined`, and `--skip-heuristic`. Use those
only when those measurements are not required; label their outputs accordingly.
Avoid running concurrent large experiments when collecting comparable timings.

The performance repairs change source hashes and add a timing column. Let any
currently active run finish without mixing its outputs with new runs. Use a new
output path for the revised code, such as a `review_20261003_perf` directory;
do not bypass resume checks on earlier source/schema files.

### CPLEX LP algorithm pilot (same model, explicit solver options)

The completed cap-three/legacy-bound 21-day run spent 1,445 of 1,482 seconds
inside CPLEX on L-30 and 1,717 of 1,784 seconds on X-40. Construction took
16 and 30 seconds. The dominant remaining bottleneck is optimizer work, not
Python construction. Different LP algorithms are therefore a controlled next
experiment, not an assumed speed fix.

Step 4 now accepts `--lp-method auto`, `primal`, `dual`, `barrier` or
`concurrent` with `--solver cplex`. Omission leaves the backend default alone.
Methods map to CPLEX LPMethod values 0, 1, 2, 4 and 6. Both CSV and metadata
record the method. Dual simplex and concurrent optimization passed the known
14,000-objective small-case check. On md14, auto/dual/concurrent 30-second probes
returned `unknown` and no certified bounds; those short attempts establish
neither a winner nor infeasibility. Their records are retained under
`results/tables/review_20261003_perf/lp_method_md14_*.csv`.

`--barrier-no-crossover` is available only with `--lp-method barrier`, but it
is experimental: CPLEX 12.9 accepted the parameter and then returned an
unreliable result on a known-feasible smoke case. Do not use it as a routine
speed recommendation or treat a contradictory barrier result as a new model
infeasibility certificate. Barrier factorization can also increase memory use.

For the next bounded test, run one algorithm on the same completed L-30 case.
Do not start this alongside another solve. Use a new output folder and retain
all raw logs even if the run reaches its budget or reports `unknown`.

```powershell
$py = '.\.venv\Scripts\python.exe'
$exe = 'F:\LT\IJOC_SDDP_for_Multi-Echelon_Lot-Sizing_with_Component_Substitution\cplex\CPLEX_Studio\cplex\bin\x64_win64\cplex.exe'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$pilot = "results/tables/lp_methods_${stamp}_cap3_legacy_tauto"
New-Item -ItemType Directory -Force $pilot | Out-Null

# Start with dual simplex, keeping all model and relaxation settings fixed.
& $py experiments/step4_lp_lower_bounds.py --input-dir data/Long_family --pattern ld21_p30_h21_r1.json --formulation integrated --solver cplex --executable $exe --threads 0 --time-limit 600 --max-hour-check-deferral-days 3 --lp-relaxation legacy-unit-bounds --lp-method dual --tee --output "$pilot/ld21_dual.csv" 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object "$pilot/ld21_dual.console.log"
```

Then test `--lp-method concurrent` and `--lp-method auto` sequentially with
distinct `ld21_concurrent.csv` and `ld21_auto.csv` outputs, the same 600-second
budget and console logs. If a method reaches proven optimality, check its bound
against the recorded 1,082,558.4339646741 within solver tolerance before claiming
a runtime improvement. A timeout with no certified bound is not a faster solve.
Compare total wall time and solver-reported time separately; repeat a promising
comparison in alternating order before choosing a production method. If no
method finishes within the pilot budget, a longer isolated pilot or a different
solver is needed; do not select a winner by an unavailable objective.

The existing `--tight-c13-m` option can separately test a strengthened, better
scaled LP. Keep its results separate: a changed big-M can strengthen the LP
relaxation even if the integer feasible set is preserved. It is not the same
legacy LP algorithm comparison and is not enabled silently.

### Results returned for later thesis integration

Retain raw CSVs, audit CSVs, metadata and console logs. Record the solver edition
and licence restrictions separately; executable availability alone does not
certify that a long run is permitted. Do not mix the new CPLEXamp observations
with archived HiGHS/Gurobi timings or mix finite and unrestricted caps. New
HiGHS rows also remain separate from historical measurements and failed CPLEX
attempts. Select the corresponding raw filename when generating a table.

After validating the returned classical CSV, generate its table without solving:

```powershell
& $py experiments/run_khaled_30day.py --table-csv "$dest/classical_h30_r1.csv" --latex-output Thesis/tables/khaled_30day_classical.tex
```

This final command assumes `$dest` still names the recommended CPLEX run
directory. If you used the optional HiGHS protocol or an ablation directory,
select that validated CSV explicitly rather than relying on variables from
another section.

The Small/Medium bracket currently comes from the archived source CSVs. The
nonzero Medium LP--MILP gaps and zero residual solver gaps are distinct. New
long results must first pass provenance, finite-bound and coverage checks; only
then regenerate plots/tables and update Chapters 6/8. The existing overlap-M20
and P20/H39 tables are excluded from this review's provenance work.

### Available-data finalization (2026-10-03)

The finalized available-data manuscript is `Thesis/main.pdf`, built from the
maintained `Thesis/main.tex` and its section inputs. It includes generated
CPLEX LP tables and the runtime plot sourced from completed CSVs, with capped
legacy and unrestricted protocols labelled separately. The unsupported
hand-entered long-family Gurobi LP table and unaudited classical 60-second
table are excluded from the numerical conclusions. Archived CPLEX observations
are retained with their restrictive configuration and provenance caveats.

The production classical batch at
`results/tables/thesis_final_20261003/classical_h30.csv` now contains completed
M-20 and L-30 records. Both reached the native time limit with finite brackets,
not proven optima. This revision freezes those rows and their metadata in
`results/tables/thesis_final_20261003/classical_h30_available_20261003.csv`
and regenerates the classical table with status, wall time and residual gap.
Input hashes, bound order and gap arithmetic are validated by the generator.
The live CSV is not changed; later rows cannot silently change this edition's
frozen table source. No X-40 row was available at the revision cutoff, and the
paired integrated 30-day study remains missing. Chapters 8/9 explicitly retain
those limitations. Finalizing the available-data edition does not certify all
planned experiments as complete or justify stopping the running batch.

The source-backed LP summary and generation manifest are
`results/tables/thesis_final_20261003/lp_evidence.csv` and its manifest sidecar.
Regenerate those artifacts with `experiments/step4_analyze_bounds.py --run
LABEL=CSV` for each declared study. Do not pool different caps, LP policies or
solver configurations. The code snapshot below freezes the maintained source
without replacing the older thesis archives.

The earlier `final_available_data_20261003` code release remains unchanged.
The revised partial-classical-evidence edition has its own snapshot and PDF
under the `final_available_data_20261003_rev2` release, rather than overwriting
the old release manifest. Regenerate the revised classical table without
running a solver:

```powershell
& .\.venv\Scripts\python.exe experiments/run_khaled_30day.py --table-csv results/tables/thesis_final_20261003/classical_h30_available_20261003.csv --latex-output Thesis/tables/khaled_30day_classical.tex
```

### Code snapshot policy

Use maintained `src/`, `experiments/` and `tests/` for every new experiment.
`Thesis/src/` and `Thesis/code/` are frozen archived copies, not live mirrors.
Package a new release only after validation, without overwriting either tree:

```powershell
& .\.venv\Scripts\python.exe experiments/package_thesis_code.py --output Thesis/code/releases/final_available_data_20261003_rev2 --dry-run
& .\.venv\Scripts\python.exe experiments/package_thesis_code.py --output Thesis/code/releases/final_available_data_20261003_rev2
```

The new release contains a source/environment manifest and per-file SHA256
hashes. Existing directories are rejected rather than overwritten. Solver temp
files, canonical instances, logs and thesis ZIP/Word deliverables are not copied.
