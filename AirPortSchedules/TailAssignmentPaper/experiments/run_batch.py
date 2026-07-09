"""experiments/run_batch.py
Run a set of instance files through src/model.py (MILP and/or heuristic mode)
and collect results into a unified CSV summary.

Usage examples
--------------
# Run heuristic only on all data/instances/*.json:
  python experiments/run_batch.py --mode heuristic --input-dir data/instances \\
         --output-dir results/tables --label my_run

# Run MILP (CPLEX, 5-min limit) on a specific subset:
  python experiments/run_batch.py --mode milp --solver cplex --time-limit 300 \\
         --pattern "DataCplex_density=1*h=7*" \\
         --input-dir data/instances --output-dir results/tables

# Run both modes:
  python experiments/run_batch.py --mode both --solver cplex --time-limit 300 \\
         --input-dir data/instances --output-dir results/tables

# Constraint-13 comparison (requires --c13 flag forwarded to model):
  python experiments/run_batch.py --mode milp --solver cplex --time-limit 600 \\
         --extra-flags "--use-paper-c13" --label c13_paper \\
         --input-dir data/instances --output-dir results/tables/c13
  python experiments/run_batch.py --mode milp --solver cplex --time-limit 600 \\
         --label c13_corrected \\
         --input-dir data/instances --output-dir results/tables/c13
"""

import argparse
import csv
import fnmatch
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_SCRIPT = os.path.join(ROOT, 'src', 'model.py')
PYTHON = sys.executable


def find_instances(input_dir: str, pattern: str) -> list[str]:
    """Return sorted list of JSON files in input_dir matching shell pattern."""
    paths = []
    for fname in sorted(os.listdir(input_dir)):
        if fname.endswith('.json') and fnmatch.fnmatch(fname, pattern):
            paths.append(os.path.join(input_dir, fname))
    return paths


def run_one(instance_path: str, mode: str, solver: str, time_limit: int,
            output_dir: str, extra_flags: list[str]) -> dict:
    """Invoke src/model.py for a single instance and return result dict."""
    stem = os.path.splitext(os.path.basename(instance_path))[0]
    out_prefix = os.path.join(output_dir, stem)

    cmd = [
        PYTHON, MODEL_SCRIPT,
        '--mode', mode,
        '--data', instance_path,
        '--out', out_prefix,
        '--no-show',
    ]
    if mode in ('milp', 'both'):
        cmd += ['--solver', solver, '--time-limit', str(time_limit)]
    cmd += extra_flags

    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=time_limit * 2 + 120,   # safety margin
        )
        elapsed = time.perf_counter() - start
        stdout = proc.stdout
        stderr = proc.stderr
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - start
        stdout = ''
        stderr = 'subprocess timeout'
        returncode = -1

    # ---- parse stdout for key metrics ----
    result = {
        'stem': stem,
        'mode': mode,
        'returncode': returncode,
        'wall_s': round(elapsed, 2),
    }

    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith('Status'):
            result['status'] = line.split(':', 1)[-1].strip()
        elif line.startswith('Obj'):
            try:
                result['objective'] = float(line.split(':', 1)[-1].strip())
            except ValueError:
                pass
        elif line.startswith('Gap'):
            try:
                result['gap_pct'] = float(
                    line.split(':', 1)[-1].strip().rstrip('%'))
            except ValueError:
                pass
        elif line.startswith('CPU'):
            try:
                result['cpu_s'] = float(
                    line.split(':', 1)[-1].strip().rstrip('s').strip())
            except ValueError:
                pass
        elif line.startswith('Vars'):
            try:
                result['num_vars'] = int(line.split(':', 1)[-1].strip())
            except ValueError:
                pass
        elif line.startswith('Constraints') or line.startswith('Const'):
            try:
                result['num_constraints'] = int(
                    line.split(':', 1)[-1].strip())
            except ValueError:
                pass
        elif 'flights' in line.lower() and 'assigned' in line.lower():
            # e.g. "Flights: 230  Assigned: 230  Unassigned: 0"
            parts = line.split()
            for i, p in enumerate(parts):
                if p.lower() == 'flights:' and i + 1 < len(parts):
                    try:
                        result['flights'] = int(parts[i + 1])
                    except ValueError:
                        pass
                if p.lower() == 'assigned:' and i + 1 < len(parts):
                    try:
                        result['assigned'] = int(parts[i + 1])
                    except ValueError:
                        pass
                if p.lower() == 'unassigned:' and i + 1 < len(parts):
                    try:
                        result['unassigned'] = int(parts[i + 1])
                    except ValueError:
                        pass

    if returncode != 0 and 'status' not in result:
        result['status'] = 'ERROR'
        result['error'] = stderr[:300]

    return result


def write_summary(rows: list[dict], output_dir: str, label: str) -> str:
    """Write results as CSV and return the path."""
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f'_batch_{label}.csv')

    fieldnames = [
        'stem', 'mode', 'flights', 'assigned', 'unassigned',
        'status', 'objective', 'gap_pct', 'cpu_s', 'wall_s',
        'num_vars', 'num_constraints', 'returncode',
    ]
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description='Batch runner for tail assignment experiments.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--mode', default='both',
                        choices=['heuristic', 'milp', 'both'],
                        help='Solver mode (default: both)')
    parser.add_argument('--solver', default='cplex',
                        help='MILP solver name (default: cplex)')
    parser.add_argument('--time-limit', type=int, default=300,
                        help='MILP time limit in seconds (default: 300)')
    parser.add_argument('--input-dir', default='data/instances',
                        help='Directory containing JSON instance files')
    parser.add_argument('--output-dir', default='results/tables',
                        help='Directory to write result files')
    parser.add_argument('--pattern', default='*.json',
                        help='Shell glob pattern for instance file names (default: *.json)')
    parser.add_argument('--label', default='batch',
                        help='Label for the output CSV file')
    parser.add_argument('--extra-flags', default='',
                        help='Extra flags forwarded verbatim to src/model.py')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print commands without running them')
    args = parser.parse_args()

    extra = [f for f in args.extra_flags.split() if f]
    instances = find_instances(args.input_dir, args.pattern)

    if not instances:
        print(f'No instances found in {args.input_dir!r} matching {args.pattern!r}',
              file=sys.stderr)
        sys.exit(1)

    print(f'Found {len(instances)} instance(s). Mode={args.mode}, '
          f'solver={args.solver}, time_limit={args.time_limit}s')

    os.makedirs(args.output_dir, exist_ok=True)
    rows = []
    modes = ['heuristic', 'milp'] if args.mode == 'both' else [args.mode]

    for inst in instances:
        for m in modes:
            if args.dry_run:
                print(f'[DRY] {inst}  mode={m}')
                continue
            print(f'  Running {os.path.basename(inst)}  mode={m} ...', end=' ',
                  flush=True)
            row = run_one(inst, m, args.solver, args.time_limit,
                          args.output_dir, extra)
            rows.append(row)
            status = row.get('status', '?')
            obj = row.get('objective', '-')
            gap = row.get('gap_pct', '-')
            cpu = row.get('cpu_s', row.get('wall_s', '-'))
            print(f'status={status}  obj={obj}  gap={gap}%  cpu={cpu}s')

    if not args.dry_run and rows:
        csv_path = write_summary(rows, args.output_dir, args.label)
        print(f'\nSummary written to {csv_path}')


if __name__ == '__main__':
    main()
