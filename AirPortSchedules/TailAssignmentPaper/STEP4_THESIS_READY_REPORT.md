# Step 4 LP-Bound Thesis Report

Date: 2026-09-28

## Certified workflow

The Step 4 workflow now performs a non-ferry routing preflight before LP-bound computation. The preflight uses the routing model with C2-C3 and overlap enabled and maintenance disabled. Instances proven infeasible under that routing interpretation are skipped rather than used as LP-bound evidence.

Certified LP runs used:

```text
solver: Gurobi
time limit: 30 seconds per solve
max-hour-check-deferral-days: 3
sparse-z: enabled
reachability: disabled
 tight-c13-m: enabled
formulations: classical, integrated
```

The reachability option is intentionally disabled. Tests showed that its station-level filtering can remove trigger days required by feasible schedules. It remains an experimental option and is not used for thesis-equivalent comparisons.

## Correctness tests

The complete repository `unittest` suite passed:

```text
22 tests run
0 failures
0 errors
```

The focused Step 4 regression tests cover:

- skipping proven non-ferry-infeasible instances;
- continuing with later feasible instances;
- explicitly including infeasible instances for diagnostics;
- CSV provenance through `routing_status`;
- floating-point LP-bound tolerance;
- missing-CSV failure status.

## Exact benchmark grid

Output:

```text
results/tables/step4_thesis_exact_certified.csv
```

Results:

| Measure | Value |
|---|---:|
| LP rows | 16 |
| Optimal rows | 15 |
| Infeasible rows | 1 |
| Available reference checks | 3 |
| Valid reference checks | 3 |

The one infeasible integrated row belongs to the legacy diagnostic instance
`ABCD_multi_check_test_OLD`. It is retained in the CSV for traceability but is
not used as a thesis reference case.

The available exact-reference checks passed with no lower-bound violations.
The standalone validator returned exit code `0`.

## Khaled 30-day classical scale probe

The Long-family M-20, L-30, and X-40 files use zero-based flight IDs. Cost
lookup was corrected in both the heuristic and MILP engines to map IDs to their
actual row in the JSON `Flights`/`Cost_Matrix` arrays. A regression checks every
flight-aircraft cost entry on the M-20 file.

The paper-style classical model was run with maintenance disabled, exact
coverage, C2-C3 continuity/turnaround, no pairwise overlap component, and a
validated path-cover MIP start. The path cover was checked against all active
model rows before solving. Gurobi used a 60-second per-instance limit,
feasibility focus, 25% heuristics, and presolve level 2.

Output:

```text
results/tables/khaled_30day_classical.csv
```

| Tier | Aircraft | Flights | Variables | Constraints | Build (s) | Complete incumbent | Valid lower bound | Gap (%) | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| M | 20 | 840 | 16,800 | 17,640 | 2.9 | 1,150,533.1 | 1,014,693.0 | 11.81 | Time limit |
| L | 30 | 1,260 | 37,800 | 39,060 | 6.0 | 1,735,942.0 | 1,637,103.0 | 5.69 | Time limit |
| X | 40 | 1,680 | 67,200 | 68,880 | 10.8 | 2,296,130.8 | 2,010,885.6 | 12.42 | Time limit |

All three runs assigned every flight in the starting solution. M-20 and X-40
returned raw Gurobi dual values below the analytical bound
`sum_i min_j cost[i,j]`; those values are marked inconsistent and excluded.
Their reported lower bounds use the analytical floor. L-30's raw dual passed
that check. None of these runs proves optimality, so these are bounded incumbent
results, not exact replications of Khaled et al.'s reported optimal solutions.

The run is reproducible with:

```powershell
python experiments/run_khaled_30day.py --time-limit 60
```

## Larger routing-feasible benchmark

A seeded non-ferry-feasible A-family instance was generated with:

```text
10 aircraft
14-day horizon
94 flights
A-family maintenance
```

Instance:

```text
data/feasible_large_A/DataCplex_density=0.5_p=10_h=14_test_0.json
```

Output:

```text
results/tables/step4_thesis_large_A.csv
```

Both classical and integrated LP formulations solved optimally:

| Formulation | LP bound | Variables | Constraints | z variables |
|---|---:|---:|---:|---:|
| Classical | 43,706 | 7,300 | recorded in CSV | 4,560 |
| Integrated | 43,706 | 7,300 | recorded in CSV | 4,560 |

The standalone validator returned exit code `0`.

## 20-aircraft, 39-day regression test

No matching instance was present in the repository, so a deterministic
certificate-backed test was generated from the `med3` family with an explicit
39-day horizon, 20 aircraft, one out-and-back rotation per tail-day, coprime
maintenance periods, and application-compatible checks.

Artifacts:

```text
data/feasible_p20_h39/med3_p20_h39_r1.json
data/feasible_p20_h39/med3_p20_h39_r1.solution.json
data/feasible_p20_h39/med3_p20_h39_r1.validation.json
```

Results using sparse maintenance domains, tight C13-M, and the default
three-day A/B deferral cap:

| Measure | Result |
|---|---:|
| Aircraft | 20 |
| Horizon | 39 days |
| Flights | 1,560 |
| Variables | 254,520 |
| Constraints | 669,912 |
| Instantiated maintenance-trigger variables | 213,960 |
| Build time | 90.7 seconds |
| Gurobi solve time | 31.0 seconds |
| Termination | Optimal |
| Objective | 2,054,196 |
| Generator certificate | Pass |
| MILP certificate verification | Pass (669,912 constraints checked) |

The same result is summarized in `Thesis/tables/strength_p20_h39.tex` and
included in the MILP strengthening chapter. This is a certified full-model
feasibility/scale test, not a baseline-versus-strengthened pairwise comparison.

## Performance evidence

On the same feasible 10-aircraft/14-day instance, the sparse aircraft domain and tight C13-M configuration reduced the model from approximately:

```text
7,300 variables to 4,620 variables
4,560 trigger variables to 1,880 trigger variables
```

Both baseline and optimized versions returned `optimal` with the same MILP objective value `56,690`, supporting semantic equivalence for this tested instance.

The actual `z_vars` count now reports the instantiated Pyomo `m.Z` domain rather than the constructor's theoretical upper bound.

## Safe maintenance-domain preprocessing check

On `md30_p20_h30_r1.json`, a build-only comparison of the full integrated
model produced:

| Configuration | Variables | Constraints | z variables | Build time |
|---|---:|---:|---:|---:|
| Default domains | 147,620 | 313,740 | 123,620 | 27.57s |
| Sparse z + day-state bounds + aircraft reachability + tight C13-M | 139,363 | 293,224 | 116,327 | 28.86s |

This is a 5.6% reduction in variables, 6.5% fewer rows, and 5.9% fewer
trigger variables. Build time did not improve in this sample, so this supports a
smaller solver model but not faster construction. On the curated
`ABCD_all_checks_test` case, the same options preserved the proven objective
`9,600` while reducing $z$ from 220 to 44. These options are opt-in and do not
replace the existing default formulation.

## Interpretation and limitations

The dense random instance
`DataCplex_density=1_p=10_h=7_test_0.json` is skipped because its non-ferry routing preflight is proven infeasible. This is a routing-model eligibility result, not an LP solver failure.

The thesis tables should therefore use:

1. exact ABCD rows that pass the routing and integrated-model checks;
2. seeded feasible-family rows such as the 10-aircraft/14-day A-family case;
3. separate diagnostic tables for routing-infeasible or legacy infeasible instances.

The current thesis-ready CSVs are reproducible with the Step 4 runner and the
Gurobi executable path documented above.

## Khaled 30-day classical routing stage

The M-20, L-30, and X-40 30-day Long-family files use zero-based flight IDs.
Both `Scheduler` and `MILP_Sheduler` now map a flight ID to its actual row in
the JSON flight/cost arrays. The classical MILP now omits maintenance variables
and objective links entirely when maintenance is disabled. This reduces M-20
classical construction from 147,620 unused-inclusive variables to 16,800
assignment variables.

A sparse bipartite path-cover start was added in
`experiments/run_khaled_30day.py`. Each produced assignment covers every flight
and is checked against active C1-C3 and overlap rows before it is passed to
Gurobi. The paper-style run disables maintenance and pairwise overlap, retaining
the compact paper routing constraints. Gurobi was given 60 seconds per
instance, feasibility focus, 25% heuristics, and presolve.

Output:

```text
results/tables/khaled_30day_classical.csv
```

| Tier | Aircraft | Flights | Variables | Constraints | Build (s) | Complete incumbent | Valid lower bound | Gap (%) | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| M | 20 | 840 | 16,800 | 17,640 | 2.9 | 1,150,533.1 | 1,014,693.0 | 11.81 | Time limit |
| L | 30 | 1,260 | 37,800 | 39,060 | 6.0 | 1,735,942.0 | 1,637,103.0 | 5.69 | Time limit |
| X | 40 | 1,680 | 67,200 | 68,880 | 10.8 | 2,296,130.8 | 2,010,885.6 | 12.42 | Time limit |

All three have complete feasible incumbents; none is proven optimal. Raw Gurobi
duals for M-20 and X-40 fell below the valid floor `sum_i min_j cost[i,j]`, so
they are flagged inconsistent and excluded from the reported gaps. The table
uses that analytical floor instead. L-30's solver dual passes the floor check.
These are useful incumbent and bounded-gap results, but do not yet match the
paper's exact-optimality claims. CPLEX, which is unavailable in this
environment, and longer budgets are still needed for direct computational
replication.

## Clique-overlap pilot

The optional `--clique-overlap` formulation groups mutually conflicting
extended flight intervals into maximal cliques and adds one at-most-one row per
aircraft/clique. The 20-second fixed-budget comparison used the same validated
path-cover start for every pairwise/clique run:

| Tier | Formulation | Constraints | Build (s) | Incumbent at limit | Valid lower bound | Gap (%) |
|---|---|---:|---:|---:|---:|---:|
| M-20 | Pairwise | 170,460 | 4.40 | 1,160,575.8 | 1,014,693.0 | 12.57 |
| M-20 | Cliques | 23,480 | 3.00 | 1,160,575.8 | 1,014,693.0 | 12.57 |
| L-30 | Pairwise | 582,030 | 11.62 | 1,745,535.1 | 1,511,232.3 | 13.42 |
| L-30 | Cliques | 50,730 | 7.87 | 1,745,535.1 | 1,511,232.3 | 13.42 |
| X-40 | Pairwise | 1,330,920 | 21.23 | 2,309,321.6 | 2,010,885.6 | 12.92 |
| X-40 | Cliques | 88,240 | 12.22 | 2,310,431.0 | 2,010,885.6 | 12.96 |

Clique rows reduced constraints by 86.2%, 91.3%, and 93.4% for M-20, L-30,
and X-40, and reduced build times by about 32%, 32%, and 42%. All runs timed
out; the short-budget results do not prove optimality or a general solve-time
speedup. M-20 clique overlap improved its incumbent in a separate 25-second
probe, but that unequal-budget result is not mixed into this table. Pairwise
remains the default pending longer and replicated tests.

Raw solver dual values below the independent assignment-cost floor were
rejected. For those runs, the report uses the valid lower bound
`sum_i min_j cost[i,j]`; this prevents bad aborted-result metadata from being
presented as a mathematical bound.
