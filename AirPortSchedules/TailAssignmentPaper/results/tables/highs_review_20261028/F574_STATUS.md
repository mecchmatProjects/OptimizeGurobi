# LD07 574-Flight Diagnostic Status

Input: `data/ld07_p30_f574_h7_r1.json` (30 aircraft, 574 flights, 7 days).
Model: current `thesis_version` legacy endpoint-split C13/C13b, full checks,
three-day deferral. No claim is made for the strict-C13 revision.

## Completed Attempts

| Attempt | Native budget | Actual wall time | Result |
| --- | ---: | ---: | --- |
| HiGHS 1.15.1, reachability + tight C13-M | 120 s | 153.06 s | Time limit; no incumbent; root LP unfinished; zero nodes |
| CPLEX 12.9, same reduced model, default CLI warm-start switch | 120 s | 138.97 s | Native log: time limit; no integer solution |
| CPLEX 12.9, same reduced model, `--no-warm-start` | 300 s | 318.69 s | Time limit; no integer solution; 9 nodes; native lower bound 853547.65162 |
| Greedy, ferries allowed | 120 s hard budget | 3.66 s | Covers 574/574, but includes ferries; not a compact-MILP certificate |
| Greedy, no ferries | 120 s hard budget | 3.17 s | Covers 533/574; 41 unassigned |
| Repair, no ferries | 120 s hard budget | 3.31 s | Covers 533/574; 41 unassigned |

CPLEX's no-incumbent timeout is displayed as `unknown` by the current Pyomo
shell result path. The native logs explicitly identify time limits, not
infeasibility. The listed lower bound is not an achievable objective.

Reachability and tight-M reduce the constructed model from 197700 variables /
199380 constraints to 166111 variables / 165757 constraints. The presolved
HiGHS model still contains roughly 88000 binaries, so the construction-size
reduction does not establish a solve-time improvement.

The earlier 600-second baseline was interrupted and is not a completed
benchmark. No completed 6000-second run or feasible compact-MILP schedule has
been obtained for this input. The code accepting/building an instance is not
the same as successfully solving it.

## Avoid An Unbounded Wait

`--time-limit` is a native solver limit, not a process deadline. Construction,
transfer and result handling add wall time. Use the tested external wrapper
for a separate wall limit (timeout exit code 124):

```powershell
python experiments/run_bounded_milp.py --wall-time-limit 6300 `
  --log results/tables/highs_review_20261028/f574_highs_long.log -- `
  --mode milp --solver highs --data data/ld07_p30_f574_h7_r1.json `
  --time-limit 6000 --aircraft-routing-reachability --tight-c13-m `
  --out results/tables/highs_review_20261028/f574_highs_long_summary.txt `
  --no-show --tee
```

6300 seconds is 105 minutes. The wrapper captures native progress immediately
and writes a `.run.json` record when the child exits or is forcibly stopped.
A forced stop cannot promise to recover an in-memory incumbent. Its process
status `completed` means the child exited normally, not that optimization
finished optimally; consult the native log and model summary.