# tail_assignment_bench

OOP benchmark package scaffold for comparing tail assignment methods.

## Included v1 methods

- `greedy_baseline` (adapter to current `Scheduler`)
- `milp_compact` (adapter to current `MILP_Sheduler`)
- `dp_exact_small` (exact tiny-instance exhaustive method)

## Quick run

From repository root:

```powershell
py -3 tail_assignment_bench/run_benchmark.py \
  --instances data/instances/DataCplex_density=0.5_p=10_h=7_test_0.json \
  --methods greedy_baseline dp_exact_small \
  --profile tail_assignment_bench/configs/default_profile.json \
  --out results/tables/oop_bench_smoke.csv \
  --time-limit 30
```

Add `milp_compact` to `--methods` when a solver is configured.

To run only a curated subset of methods, pass a methods config file:

```powershell
py -3 tail_assignment_bench/run_benchmark.py \
  --instances data/instances/ABCD_no_maint_test.json \
  --methods greedy_baseline dijkstra_heuristic aco_heuristic bruteforce_exact dp_exact_small \
  --methods-config tail_assignment_bench/configs/methods_subset.json \
  --profile tail_assignment_bench/configs/default_profile.json \
  --out results/tables/oop_subset_smoke.csv \
  --legacy-out results/tables/oop_subset_smoke_legacy.csv \
  --time-limit 30
```

The methods config is a JSON file with a top-level `methods` array, for example:

```json
{
  "methods": ["greedy_baseline", "dijkstra_heuristic", "aco_heuristic"]
}
```

## Output

CSV columns:

- `stem`
- `method`
- `status`
- `objective`
- `score`
- `unassigned`
- `gap_pct`
- `wall_s`
- `cpu_s`
- `violations`
