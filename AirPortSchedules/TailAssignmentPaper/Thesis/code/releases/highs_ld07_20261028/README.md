# HiGHS LD07 Reproduction Snapshot

This is a copy of the maintained code on `thesis_version` at commit
`46cf8fc`, not an overwrite of the older thesis source trees.
The copied model uses legacy endpoint-split C13 by default, not the strict
C13 implementation discussed in earlier sessions on another revision.

## Contents

- `src/`: maintained model and supporting modules.
- `experiments/` and `tests/`: experiment runners and regression tests.
- `data/ld07_p30_f574_h7_r1.json`: the exact 574-flight, 30-aircraft, 7-day input.
- `requirements.txt`: runtime dependencies, including `highspy`.
- `manifest.json`: producing revision and hashes of the packaged Python files.

Verified interpreter/backend versions in the producing workspace:
Python 3.12, Pyomo 6.10.1, HiGHS 1.15.1.

## Run From This Snapshot Directory

With a Python environment containing the dependencies:

```powershell
python -m pip install -r requirements.txt
python src/model.py --mode milp --solver highs `
  --data data/ld07_p30_f574_h7_r1.json --time-limit 6000 `
  --out results/tables/milp_summaryld0727.txt --no-show --tee
```

When using the existing workspace virtual environment, from the workspace root:

```powershell
Push-Location Thesis/code/releases/highs_ld07_20261028
& ../../../../.venv/Scripts/python.exe src/model.py --mode milp --solver highs `
  --data data/ld07_p30_f574_h7_r1.json --time-limit 6000 `
  --out results/tables/milp_summaryld0727.txt --no-show --tee
Pop-Location
```

The requested `--out Outputs/milp_summaryld0727.txt` is also supported;
`results/tables/` is the repository's preferred output location.

## Interpretation

`--time-limit 6000` configures 6000 native solver seconds (100 minutes).
Model construction, transfer, result loading and plotting add wall time.
`--no-show` suppresses the plot window; `--tee` displays native solver progress.
A timeout without an incumbent is inconclusive, not proof of infeasibility.
This snapshot does not contain a completed 6000-second benchmark result.

Existing optional `--aircraft-routing-reachability --tight-c13-m` flags reduce
this input's model from 197700 variables / 199380 constraints to
166111 variables / 165757 constraints in a construction-only check.
This is not a measured solve-time speedup. Keep the deferral cap, active check
types and C13 variant fixed when benchmarking performance.