"""experiments/reproduce_tables.py
Reproduce and validate Tables 5, 6, 10, 11 from Khaled et al. (2018) plus
the constraint-13 correction experiment, using the configs in experiments/configs/.

This script:
  1. Reads a table config (experiments/configs/table{N}.json or c13_correction.json).
  2. Generates any missing instance files via src/generate_instances.py.
  3. Runs experiments/run_batch.py for each (density, p, h) grid cell.
  4. Aggregates results and writes:
       results/tables/table{N}_reproduced.csv   -- per-row averages
       results/tables/table{N}_vs_paper.csv     -- side-by-side comparison
     for numeric tables, and:
       results/tables/c13_correction.csv        -- for the C13 experiment.

Usage
-----
  python experiments/reproduce_tables.py --table 5 [--quick] [--solver cplex]
  python experiments/reproduce_tables.py --table 6
  python experiments/reproduce_tables.py --table 10
  python experiments/reproduce_tables.py --table 11
  python experiments/reproduce_tables.py --experiment c13_correction

Flags
-----
  --quick     Use only h in {7, 15} and p in {10, 20} (reduces runtime ~10x).
  --solver    MILP solver name (default: cplex).
  --time-limit  Per-instance time limit in seconds (default: from config).
  --instances   How many random instances per grid cell (default: from config,
                typically 10; use 1 for a quick smoke test).
"""

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIGS_DIR = ROOT / 'experiments' / 'configs'
DATA_DIR = ROOT / 'data' / 'instances'
RESULTS_DIR = ROOT / 'results' / 'tables'
PYTHON = sys.executable
GENERATE_SCRIPT = ROOT / 'src' / 'generate_instances.py'
RUN_BATCH_SCRIPT = ROOT / 'experiments' / 'run_batch.py'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config(table_id: str) -> dict:
    """Load a JSON config by table number or experiment name."""
    candidates = [
        CONFIGS_DIR / f'table{table_id}.json',
        CONFIGS_DIR / f'{table_id}.json',
    ]
    for c in candidates:
        if c.exists():
            with open(c) as f:
                return json.load(f)
    raise FileNotFoundError(
        f'No config found for {table_id!r} in {CONFIGS_DIR}')


def ensure_instances(density: float, p: int, h: int,
                     n_instances: int) -> list[str]:
    """Generate instances if not already present; return list of paths."""
    paths = []
    for idx in range(n_instances):
        fname = f'DataCplex_density={density}_p={p}_h={h}_test_{idx}.json'
        fpath = DATA_DIR / fname
        if not fpath.exists():
            print(f'  Generating {fname} ...', end=' ', flush=True)
            cmd = [
                PYTHON, str(GENERATE_SCRIPT),
                str(density), str(p), str(h), '1',
                '--output-dir', str(DATA_DIR),
                '--index', str(idx),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f'FAILED\n{result.stderr[:300]}')
            else:
                print('OK')
        paths.append(str(fpath))
    return [p for p in paths if Path(p).exists()]


def run_grid_cell(density: float, p: int, h: int,
                  n_instances: int, config: dict,
                  solver: str, time_limit: int,
                  extra_flags: list[str],
                  output_dir: Path, label: str) -> list[dict]:
    """Run batch for one (density, p, h) cell and return rows."""
    pattern = f'DataCplex_density={density}_p={p}_h={h}_test_*.json'
    ensure_instances(density, p, h, n_instances)

    cmd = [
        PYTHON, str(RUN_BATCH_SCRIPT),
        '--mode', config.get('mode', 'milp'),
        '--solver', solver,
        '--time-limit', str(time_limit),
        '--input-dir', str(DATA_DIR),
        '--output-dir', str(output_dir),
        '--pattern', pattern,
        '--label', label,
    ] + extra_flags

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f'  WARNING: run_batch returned {result.returncode}')
        print(result.stderr[:300])

    # Read back the CSV
    csv_path = output_dir / f'_batch_{label}.csv'
    rows = []
    if csv_path.exists():
        with open(csv_path, newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
    return rows


def average_rows(rows: list[dict], mode_filter: str | None = None) -> dict:
    """Compute column averages over a list of CSV dicts."""
    if mode_filter:
        rows = [r for r in rows if r.get('mode') == mode_filter]
    if not rows:
        return {}
    numeric_cols = ['flights', 'assigned', 'unassigned', 'objective',
                    'gap_pct', 'cpu_s', 'wall_s', 'num_vars', 'num_constraints']
    avgs = {}
    for col in numeric_cols:
        vals = []
        for r in rows:
            try:
                vals.append(float(r[col]))
            except (KeyError, TypeError, ValueError):
                pass
        if vals:
            avgs[col] = round(sum(vals) / len(vals), 4)
    avgs['n'] = len(rows)
    avgs['status_counts'] = {}
    for r in rows:
        s = r.get('status', 'unknown')
        avgs['status_counts'][s] = avgs['status_counts'].get(s, 0) + 1
    return avgs


def compare_to_paper(our: dict, paper: dict) -> dict:
    """Build a side-by-side comparison row."""
    out = {}
    for key in ['flights', 'num_vars', 'num_constraints', 'gap_pct', 'cpu_s']:
        our_val = our.get(key, None)
        paper_val = paper.get(key, None)
        out[f'our_{key}'] = our_val
        out[f'paper_{key}'] = paper_val
        if our_val is not None and paper_val is not None and paper_val != 0:
            out[f'ratio_{key}'] = round(our_val / paper_val, 4)
    return out


# ---------------------------------------------------------------------------
# Table reproducers
# ---------------------------------------------------------------------------

def reproduce_basic_table(table_id: str, config: dict, args) -> None:
    """Reproduce Tables 5 or 6 (no maintenance)."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ref = config.get('reference_table', {})
    all_repro_rows = []
    all_compare_rows = []

    quick_p = {10, 20}
    quick_h = {7, 15}

    for cell in config['grid']:
        p, h, density = cell['p'], cell['h'], cell['density']
        if args.quick and (p not in quick_p or h not in quick_h):
            continue

        n_inst = args.instances or cell.get('instances', 10)
        time_lim = args.time_limit or config.get('time_limit', 14400)
        label = f't{table_id}_p{p}_h{h}_d{str(density).replace(".", "")}'

        print(f'\nGrid cell: density={density}, p={p}, h={h}, n={n_inst}')
        extra = []
        if not config.get('use_maintenance', True):
            extra.append('--no-maintenance')
        if not config.get('use_overlap', True):
            extra.append('--no-overlap')

        rows = run_grid_cell(density, p, h, n_inst, config,
                             args.solver, time_lim, extra,
                             RESULTS_DIR, label)

        avg = average_rows(rows, mode_filter='milp')
        avg.update({'p': p, 'h': h, 'density': density})
        all_repro_rows.append(avg)

        paper_key = f'p{p}_h{h}'
        if paper_key in ref:
            comp = compare_to_paper(avg, ref[paper_key])
            comp.update({'p': p, 'h': h, 'density': density})
            all_compare_rows.append(comp)

    # Write reproduced table
    repro_path = RESULTS_DIR / f'table{table_id}_reproduced.csv'
    if all_repro_rows:
        keys = list(all_repro_rows[0].keys())
        with open(repro_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
            w.writeheader()
            w.writerows(all_repro_rows)
        print(f'\nReproduced table written to {repro_path}')

    # Write vs-paper comparison
    if all_compare_rows:
        comp_path = RESULTS_DIR / f'table{table_id}_vs_paper.csv'
        keys = list(all_compare_rows[0].keys())
        with open(comp_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
            w.writeheader()
            w.writerows(all_compare_rows)
        print(f'Comparison table written to {comp_path}')


def reproduce_maintenance_table(table_id: str, config: dict, args) -> None:
    """Reproduce Tables 10 or 11 (with maintenance)."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ref = config.get('reference_table', {})

    quick_p = {10, 20}
    quick_h = {15, 21}

    for variant in config.get('variants', [{}]):
        v_label = variant.get('label', 'default')
        extra = []
        if variant.get('use_paper_c13', False):
            extra.append('--use-paper-c13')
        nu = variant.get('nu_landings')
        if nu:
            extra += ['--nu-landings', str(nu)]
        dmax = variant.get('dmax')
        if dmax:
            extra += ['--dmax', str(dmax)]
        tmax_h = variant.get('Tmax_hours')
        if tmax_h:
            extra += ['--tmax-hours', str(tmax_h)]

        all_rows = []
        for cell in config['grid']:
            p, h, density = cell['p'], cell['h'], cell['density']
            if args.quick and (p not in quick_p or h not in quick_h):
                continue

            n_inst = args.instances or cell.get('instances', 10)
            time_lim = args.time_limit or config.get('time_limit', 10800)
            label = f't{table_id}_{v_label}_p{p}_h{h}'

            print(f'\nVariant={v_label} p={p} h={h} density={density}')
            rows = run_grid_cell(density, p, h, n_inst, config,
                                 args.solver, time_lim, extra,
                                 RESULTS_DIR, label)

            avg = average_rows(rows, mode_filter='milp')
            avg.update({'p': p, 'h': h, 'density': density, 'variant': v_label})

            # compare to paper reference
            paper_key = f'p{p}_h{h}'
            ref_v = ref.get(v_label, ref) if isinstance(ref, dict) else {}
            paper_row = ref_v.get(paper_key, {})
            if paper_row:
                avg.update({f'paper_{k}': v for k, v in compare_to_paper(avg, paper_row).items()})

            all_rows.append(avg)

        if all_rows:
            out_path = RESULTS_DIR / f'table{table_id}_{v_label}_reproduced.csv'
            keys = list(all_rows[0].keys())
            with open(out_path, 'w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
                w.writeheader()
                w.writerows(all_rows)
            print(f'\nReproduced table written to {out_path}')


def run_c13_experiment(config: dict, args) -> None:
    """Run the constraint-13 correction experiment."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    all_rows = []

    for variant in config['variants']:
        v_label = variant['label']
        extra = []
        if variant.get('use_paper_c13', False):
            extra.append('--use-paper-c13')
        if variant.get('use_existing_hrs', False):
            extra.append('--use-existing-hrs')

        # Run on targeted ABCD instances
        for inst_path in config.get('targeted_instances', []):
            full_path = ROOT / inst_path
            if not full_path.exists():
                print(f'  SKIP (not found): {full_path}')
                continue
            stem = full_path.stem
            label = f'c13_{v_label}_{stem}'
            cmd = [
                PYTHON, str(RUN_BATCH_SCRIPT),
                '--mode', 'milp',
                '--solver', args.solver,
                '--time-limit', str(args.time_limit or 3600),
                '--input-dir', str(full_path.parent),
                '--pattern', full_path.name,
                '--output-dir', str(RESULTS_DIR / 'c13'),
                '--label', label,
            ] + extra
            subprocess.run(cmd, capture_output=True, text=True)
            csv_path = RESULTS_DIR / 'c13' / f'_batch_{label}.csv'
            if csv_path.exists():
                with open(csv_path, newline='', encoding='utf-8') as f:
                    for row in csv.DictReader(f):
                        row['variant'] = v_label
                        row['instance'] = stem
                        all_rows.append(row)

        # Run on parametric grid
        quick_p = {10, 20}
        quick_h = {7, 15}
        for cell in config['grid']:
            p, h, density = cell['p'], cell['h'], cell['density']
            if args.quick and (p not in quick_p or h not in quick_h):
                continue
            n_inst = args.instances or cell.get('instances', 10)
            time_lim = args.time_limit or config.get('time_limit', 3600)
            label = f'c13_{v_label}_p{p}_h{h}'
            rows = run_grid_cell(density, p, h, n_inst, config,
                                 args.solver, time_lim, extra,
                                 RESULTS_DIR / 'c13', label)
            for row in rows:
                row['variant'] = v_label
                all_rows.append(row)

    if all_rows:
        out_path = RESULTS_DIR / 'c13_correction.csv'
        keys = list(all_rows[0].keys())
        with open(out_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
            w.writeheader()
            w.writerows(all_rows)
        print(f'\nC13 correction results written to {out_path}')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Reproduce Khaled et al. (2018) tables and new experiments.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--table', default=None,
                        help='Table number to reproduce: 5, 6, 10, or 11')
    parser.add_argument('--experiment', default=None,
                        help='Experiment name: c13_correction')
    parser.add_argument('--solver', default='cplex',
                        help='MILP solver (default: cplex)')
    parser.add_argument('--time-limit', type=int, default=None,
                        help='Override time limit (seconds)')
    parser.add_argument('--instances', type=int, default=None,
                        help='Override number of instances per grid cell')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: p in {10,20}, h in {7,15} only')
    args = parser.parse_args()

    if args.table is None and args.experiment is None:
        parser.error('Specify --table N or --experiment NAME.')

    target = args.table or args.experiment
    config = load_config(target)

    table_id = config.get('table')
    exp_name = config.get('experiment')

    if exp_name == 'c13_correction':
        print('=== Constraint-13 Correction Experiment ===')
        run_c13_experiment(config, args)
    elif table_id in (5, 6):
        print(f'=== Reproducing Table {table_id} (basic model) ===')
        reproduce_basic_table(str(table_id), config, args)
    elif table_id in (10, 11):
        print(f'=== Reproducing Table {table_id} (maintenance model) ===')
        reproduce_maintenance_table(str(table_id), config, args)
    else:
        print(f'Unknown table/experiment: {target}', file=sys.stderr)
        sys.exit(1)

    print('\nDone.')


if __name__ == '__main__':
    main()
