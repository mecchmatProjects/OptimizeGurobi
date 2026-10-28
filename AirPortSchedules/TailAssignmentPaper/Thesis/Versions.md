# Thesis Code Version History

Updated 2026-10-28. Git retains the deleted files and their complete history.
The current repository-root `src/`, `experiments/`, and `tests/` are the
maintained source of truth. The portable `Thesis/code/` package is retained;
its Python files under those three directories were synchronized from the
repository root on 2026-10-28. The original `Thesis/code/src/` snapshot was
introduced by `4946358` (2026-08-20) and last updated before synchronization
by `8eefb0d` (2026-09-08). The package's existing non-Python material was not
changed; seven JSON test fixtures were copied into `Thesis/code/data/` so the
packaged tests can run there.

## Removed Snapshots

| Removed path | Path created in Git | Source version / creation date | Recorded source hash | Reason |
| --- | --- | --- | --- | --- |
| `Thesis/src/` | `828d3f0` (2026-10-01) | Traced source history to `d902b3c` (2026-03-05) | N/A | Superseded archived source copy; no longer needed beside the retained portable package. |
| `Thesis/code/releases/final_available_data_20261003/` | `6a96d19` (2026-10-06) | `247b395` (2026-10-02) | `e3d2ea89df03b66ec3f8e9bc76dff96ff56866b39e41d5023722a7b8b4726508` | Superseded archived release. |
| `Thesis/code/releases/final_available_data_20261003_rev2/` | `6a96d19` (2026-10-06) | `247b395` (2026-10-02) | `89c8a2b7235d3a7bd40a01ed8e4f67cb41e7b18e09c05307338e961d84d0eb80` | Superseded archived release. |
| `Thesis/code/releases/final_available_data_20261003_rev3/` | `6a96d19` (2026-10-06) | `247b395` (2026-10-02) | `89c8a2b7235d3a7bd40a01ed8e4f67cb41e7b18e09c05307338e961d84d0eb80` | Superseded archived release; source hash matched revision 2. |
| `Thesis/code/releases/highs_ld07_20261028/` | `d8bf2f4` (2026-10-28) | `46cf8fc` (2026-10-13) | `9f163e79eeaf251203bf66261801ef3914d18d42a33f9f291465567aa75e644b` | Superseded by the bounded LD07 release below. |

## Retained Release

The root `Thesis/code/src/`, `Thesis/code/experiments/`, and
`Thesis/code/tests/` Python files now mirror their repository-root
counterparts. The nested bounded LD07 release below remains a separate,
historical, reproducibility snapshot.

`Thesis/code/releases/highs_ld07_bounded_20261028/` is retained. It was added
by `d8bf2f4` (2026-10-28), packages code from `46cf8fc` (2026-10-13), and has
source hash `102f0cc48c3f570194df2f09cfa4d63ac3a15eaea1ee2c13b8b4a7ee30558acb`.
