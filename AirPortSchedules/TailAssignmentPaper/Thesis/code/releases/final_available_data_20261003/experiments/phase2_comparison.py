"""experiments/phase2_comparison.py
Phase-2 Classical vs Integrated comparison experiment.

Runs three methods on the Phase-1 25-instance set and merges results into a
single comparison CSV (results/tables/phase2_comparison.csv).

Three methods
-------------
  classical_milp    MILP, no maintenance constraints (--no-maintenance)
                    Baseline comparable to Khaled et al. (2018) basic model.
  integrated_milp   MILP, full corrected maintenance model (default flags)
                    Our corrected + extended formulation.
  greedy_heuristic  Greedy+insertion heuristic (no solver required)
  repair_heuristic  Repair-based heuristic that greedily inserts flights and
                    then iteratively improves placements (no solver required)

Usage
-----
  python experiments/phase2_comparison.py --solver cbc --time-limit 300
  python experiments/phase2_comparison.py --quick              # Tier-1 only (5 instances)
  python experiments/phase2_comparison.py --dry-run
"""

import argparse
import csv
import os
import subprocess
import sys
import time

try:
    from pyomo.environ import SolverFactory
except Exception:  # pragma: no cover - optional dependency in some environments
    SolverFactory = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATCH_SCRIPT = os.path.join(ROOT, 'experiments', 'run_batch.py')
PYTHON = sys.executable

INSTANCE_DIR = os.path.join(ROOT, 'data', 'phase1_25_forced')
OUTPUT_DIR   = os.path.join(ROOT, 'results', 'tables', 'phase2')

# Tier-1 instances (p=8, h=7) for --quick mode
QUICK_PATTERN = 'I1*'

METHODS = [
    {
        'label':      'classical_milp',
        'mode':       'milp',
        'extra_flags': '--no-maintenance',
        'needs_solver': True,
    },
    {
        'label':      'integrated_milp',
        'mode':       'milp',
        'extra_flags': '',
        'needs_solver': True,
    },
    {
        'label':      'greedy_heuristic',
        'mode':       'heuristic',
        'extra_flags': '',
        'needs_solver': False,
    },
    {
        'label':      'repair_heuristic',
        'mode':       'heuristic',
        'extra_flags': '--heuristic repair',
        'needs_solver': False,
    },
    {
        'label':      'local_search_heuristic',
        'mode':       'heuristic',
        'extra_flags': '--heuristic local_search',
        'needs_solver': False,
    },
]


def _resolve_solver(requested_solver: str) -> str:
    """Return an available Pyomo solver, falling back when needed."""
    if not requested_solver:
        requested_solver = 'cplex_direct'

    candidate_order = [requested_solver]
    for fallback in ('cplex_direct', 'cplex', 'cbc'):
        if fallback not in candidate_order:
            candidate_order.append(fallback)

    for name in candidate_order:
        try:
            if SolverFactory is not None and SolverFactory(name).available():
                return name
        except Exception:
            continue
    return requested_solver


def _run_batch(method: dict, solver: str, time_limit: int,
               pattern: str, output_dir: str, dry_run: bool) -> str:
    """Run run_batch.py for one method; return path to the per-method CSV."""
    label = method['label']
    csv_label = label
    cmd = [
        PYTHON, BATCH_SCRIPT,
        '--mode',       method['mode'],
        '--method',     label,
        '--input-dir',  INSTANCE_DIR,
        '--output-dir', output_dir,
        '--pattern',    pattern,
        '--label',      csv_label,
    ]
    if method['needs_solver']:
        cmd += ['--solver', solver, '--time-limit', str(time_limit)]
    if method['extra_flags']:
        cmd += [f'--extra-flags={method["extra_flags"]}']

    if dry_run:
        print(f'[DRY] {" ".join(cmd)}')
        return ''

    print(f'\n=== method: {label} ===')
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=False,
                          timeout=time_limit * 30 + 300)
    elapsed = time.perf_counter() - t0
    print(f'--- {label} done in {elapsed:.1f}s, returncode={proc.returncode} ---')
    return os.path.join(output_dir, f'_batch_{csv_label}.csv')


def _merge(csv_paths: list[str], out_path: str) -> None:
    """Merge per-method CSVs into one comparison CSV."""
    all_rows = []
    fieldnames = None
    for p in csv_paths:
        if not p or not os.path.exists(p):
            continue
        with open(p, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if fieldnames is None:
                fieldnames = reader.fieldnames
            all_rows.extend(reader)

    if not all_rows:
        print('No rows to merge — check individual method CSVs.', file=sys.stderr)
        return

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_rows)
    print(f'\nMerged comparison written to {out_path}  ({len(all_rows)} rows)')


def _print_summary(out_path: str) -> None:
    """Print a compact per-method status summary table."""
    if not os.path.exists(out_path):
        return
    from collections import defaultdict
    counts = defaultdict(lambda: defaultdict(int))
    with open(out_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            m = row.get('method', '?')
            s = row.get('status', '?')
            counts[m][s] += 1

    print('\n=== Phase-2 summary ===')
    print(f'{"method":<22}  {"optimal":>7}  {"infeasible":>10}  {"error":>7}  {"other":>6}')
    print('-' * 60)
    for method in [m['label'] for m in METHODS]:
        c = counts.get(method, {})
        opt  = c.get('optimal', 0)
        inf  = c.get('infeasible', 0)
        err  = c.get('ERROR', 0)
        rest = sum(v for k, v in c.items() if k not in ('optimal', 'infeasible', 'ERROR'))
        print(f'{method:<22}  {opt:>7}  {inf:>10}  {err:>7}  {rest:>6}')


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--solver', default=os.environ.get('TAP_PYOMO_SOLVER', 'cplex_direct'),
                        help='MILP solver (default: TAP_PYOMO_SOLVER or cplex_direct)')
    parser.add_argument('--time-limit', type=int, default=300,
                        help='Per-instance MILP time limit in seconds (default: 300)')
    parser.add_argument('--quick', action='store_true',
                        help='Run Tier-1 instances only (pattern I1*.json)')
    parser.add_argument('--methods', nargs='+',
                        default=[m['label'] for m in METHODS],
                        choices=[m['label'] for m in METHODS],
                        help='Subset of methods to run (default: all three)')
    parser.add_argument('--output-dir', default=OUTPUT_DIR,
                        help=f'Output directory (default: {OUTPUT_DIR})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print commands without executing')
    args = parser.parse_args()

    pattern = QUICK_PATTERN if args.quick else '*.json'
    os.makedirs(args.output_dir, exist_ok=True)

    resolved_solver = _resolve_solver(args.solver)
    if resolved_solver != args.solver:
        print(f'Using solver fallback: {args.solver} -> {resolved_solver}')

    active = [m for m in METHODS if m['label'] in args.methods]
    csv_paths = []
    for method in active:
        p = _run_batch(method, resolved_solver, args.time_limit,
                       pattern, args.output_dir, args.dry_run)
        csv_paths.append(p)

    if not args.dry_run:
        merged = os.path.join(args.output_dir, 'phase2_comparison.csv')
        _merge(csv_paths, merged)
        _print_summary(merged)


if __name__ == '__main__':
    main()
