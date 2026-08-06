"""experiments/phase3_scalability.py
Phase-3 scalability boundary study.

Measures how MILP model size (variables, constraints) and solve behaviour
scale with fleet size p, planning horizon h, and density across the
DataCplex benchmark instances.  Both the classical (no-maintenance) and
integrated (full maintenance) formulations are measured so the cost of
adding maintenance constraints can be quantified.

The DataCplex instances are solvable with full MILP (confirmed baseline:
density=0.5, p=10, h=7 yields optimal 827858 in seconds). They provide
the p × h grid needed to characterise the scalability boundary.

Output
------
  results/tables/phase3/phase3_scalability.csv   — per-instance metrics
  results/tables/phase3/phase3_size_growth.csv   — model-size summary by (p, h)

Usage
-----
  python experiments/phase3_scalability.py --solver cbc --time-limit 120
  python experiments/phase3_scalability.py --quick              # density=0.5 only
  python experiments/phase3_scalability.py --dry-run
"""

import argparse
import csv
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATCH_SCRIPT = os.path.join(ROOT, 'experiments', 'run_batch.py')
PYTHON = sys.executable

INSTANCE_DIR = os.path.join(ROOT, 'data', 'instances')
OUTPUT_DIR   = os.path.join(ROOT, 'results', 'tables', 'phase3')

# DataCplex instances cover (density, p, h) combinations.
# Only density ∈ {0.5, 0.95, 1.0} are present; p ∈ {10, 20}; h ∈ {7,15,21,30}.
METHODS = [
    {'label': 'classical_milp',  'mode': 'milp', 'extra_flags': '--no-maintenance'},
    {'label': 'integrated_milp', 'mode': 'milp', 'extra_flags': ''},
]


def _run_batch(method: dict, solver: str, time_limit: int,
               pattern: str, output_dir: str, dry_run: bool) -> str:
    label = method['label']
    cmd = [
        PYTHON, BATCH_SCRIPT,
        '--mode',       method['mode'],
        '--method',     label,
        '--input-dir',  INSTANCE_DIR,
        '--output-dir', output_dir,
        '--pattern',    pattern,
        '--label',      f'p3_{label}',
        '--solver',     solver,
        '--time-limit', str(time_limit),
    ]
    if method['extra_flags']:
        cmd += [f'--extra-flags={method["extra_flags"]}']

    if dry_run:
        print(f'[DRY] {" ".join(cmd)}')
        return ''

    print(f'\n=== Phase-3 method: {label} ===')
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=False,
                          timeout=time_limit * len(os.listdir(INSTANCE_DIR)) + 300)
    elapsed = time.perf_counter() - t0
    print(f'--- {label} done in {elapsed:.1f}s, returncode={proc.returncode} ---')
    return os.path.join(output_dir, f'_batch_p3_{label}.csv')


def _parse_stem(stem: str) -> dict:
    """Extract density, p, h from DataCplex stem string."""
    m = re.search(r'density=([\d.]+)_p=(\d+)_h=(\d+)', stem)
    if m:
        return {'density': float(m.group(1)), 'p': int(m.group(2)), 'h': int(m.group(3))}
    return {}


def _merge_and_annotate(csv_paths: list[str], out_path: str) -> None:
    """Merge per-method CSVs, add parsed (density, p, h) columns."""
    all_rows = []
    fieldnames = None
    for p in csv_paths:
        if not p or not os.path.exists(p):
            continue
        with open(p, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if fieldnames is None:
                fieldnames = ['density', 'p', 'h'] + list(reader.fieldnames)
            for row in reader:
                parsed = _parse_stem(row.get('stem', ''))
                all_rows.append({'density': parsed.get('density', ''),
                                 'p': parsed.get('p', ''),
                                 'h': parsed.get('h', ''), **row})

    if not all_rows:
        print('No rows to merge.', file=sys.stderr)
        return

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_rows)
    print(f'\nScalability table written to {out_path}  ({len(all_rows)} rows)')


def _write_size_summary(merged_path: str, out_path: str) -> None:
    """Write a (method, p, h, density) × (vars, constraints, status, cpu_s) summary."""
    if not os.path.exists(merged_path):
        return
    rows = []
    with open(merged_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            rows.append({
                'method':      row.get('method', ''),
                'density':     row.get('density', ''),
                'p':           row.get('p', ''),
                'h':           row.get('h', ''),
                'status':      row.get('status', ''),
                'num_vars':    row.get('num_vars', ''),
                'num_constraints': row.get('num_constraints', ''),
                'cpu_s':       row.get('cpu_s', ''),
                'wall_s':      row.get('wall_s', ''),
                'objective':   row.get('objective', ''),
                'gap_pct':     row.get('gap_pct', ''),
            })
    rows.sort(key=lambda r: (r['method'], float(r['p'] or 0),
                             float(r['h'] or 0), float(r['density'] or 0)))
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # Print compact summary table
    print('\n=== Phase-3 scalability summary ===')
    print(f'{"method":<20} {"d":>5} {"p":>4} {"h":>4}  {"status":<12} '
          f'{"vars":>8}  {"cons":>8}  {"cpu_s":>7}')
    print('-' * 75)
    for r in rows:
        print(f'{r["method"]:<20} {r["density"]:>5} {r["p"]:>4} {r["h"]:>4}  '
              f'{r["status"]:<12} {r["num_vars"]:>8}  {r["num_constraints"]:>8}  '
              f'{r["cpu_s"]:>7}')


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--solver', default=os.environ.get('TAP_PYOMO_SOLVER', 'cbc'),
                        help='MILP solver (default: TAP_PYOMO_SOLVER or cbc)')
    parser.add_argument('--time-limit', type=int, default=120,
                        help='Per-instance MILP time limit in seconds (default: 120)')
    parser.add_argument('--quick', action='store_true',
                        help='Run density=0.5 instances only')
    parser.add_argument('--methods', nargs='+',
                        default=[m['label'] for m in METHODS],
                        choices=[m['label'] for m in METHODS],
                        help='Methods to run (default: both)')
    parser.add_argument('--output-dir', default=OUTPUT_DIR)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    pattern = 'DataCplex_density=0.5*.json' if args.quick else 'DataCplex*.json'
    os.makedirs(args.output_dir, exist_ok=True)

    active = [m for m in METHODS if m['label'] in args.methods]
    csv_paths = []
    for method in active:
        p = _run_batch(method, args.solver, args.time_limit,
                       pattern, args.output_dir, args.dry_run)
        csv_paths.append(p)

    if not args.dry_run:
        merged = os.path.join(args.output_dir, 'phase3_scalability.csv')
        _merge_and_annotate(csv_paths, merged)
        summary = os.path.join(args.output_dir, 'phase3_size_growth.csv')
        _write_size_summary(merged, summary)


if __name__ == '__main__':
    main()
