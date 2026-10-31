"""Heuristic termination time and optimality gap table over instance files.

For every JSON instance, each heuristic is run and timed, then its schedule is
scored with the MILP objective: flight cost + early-check penalty (cost per
minute a check is performed before it is due), plus ferry cost when ferries
are allowed. The gap is measured against the MILP optimum, or against the MILP
lower bound when the solver stops early (an upper bound on the true gap).

Example:
    python experiments/heuristic_gap_table.py --input-dir data/instances \
        --methods dijkstra aco --solver highs --milp-time-limit 300
"""
import argparse
import csv
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model import (DEFAULT_EARLY_CHECK_PENALTY, MILP_Sheduler, Scheduler,
                       heuristic_objective)
from src.solver_utils import parse_deferral_days

LOGGER = logging.getLogger(__name__)
HEURISTICS = ('greedy', 'insertion', 'greedy+insertion', 'repair',
              'local_search', 'dijkstra', 'aco')
DAY_MINUTES = 1440


def instance_features(data_path):
    data = json.loads(Path(data_path).read_text(encoding='utf-8'))
    flights = data['Flights']
    airports = {flight[1] for flight in flights} | {flight[2] for flight in flights}
    horizon = data.get('Parameters', {}).get('Target_Horizon_Days')
    if horizon is None:
        horizon = max(int(float(flight[4]) // DAY_MINUTES) + 1 for flight in flights)
    return {
        'P': len(data['Aircrafts']),
        'airports': len(airports),
        'maintenance_stations': sum(1 for cap in data['Station_Capacity'].values() if cap > 0),
        'H': int(horizon),
        'F': len(flights),
        'min_turn_min': float(data.get('Parameters', {}).get('Min_Turn_Minutes', 30)),
    }


def run_heuristic(data_path, method, allow_ferry, aco_options, early_check_penalty):
    started = time.perf_counter()
    scheduler = Scheduler(str(data_path), allow_ferry=allow_ferry, heuristic=method,
                          early_check_penalty=early_check_penalty, **aco_options)
    routes, unassigned = scheduler.optimize()
    cpu = time.perf_counter() - started

    objective, early_minutes = heuristic_objective(scheduler, routes)
    valid = objective is not None
    ferry_events = 0
    maintenance_events = 0
    if valid:
        for aircraft, route in routes.items():
            for event in scheduler.get_timeline(aircraft, route)['events']:
                ferry_events += event['kind'] == 'FERRY'
                maintenance_events += event['kind'] == 'MAINT'

    flights = len(scheduler.flights)
    assigned = flights - len(unassigned)
    if not valid:
        status = 'invalid'
    elif unassigned:
        status = 'partial'
    else:
        status = 'complete'
    return {
        'method': method, 'status': status, 'cpu_s': cpu,
        'objective': objective if status == 'complete' else None,
        'assigned': assigned, 'coverage_pct': 100.0 * assigned / flights,
        'ferry_events': ferry_events, 'maintenance_events': maintenance_events,
        'early_check_min': early_minutes,
    }, routes


def run_reference(data_path, solver_name, time_limit, deferral_days, tight_c13_m,
                  early_check_penalty):
    started = time.perf_counter()
    optimizer = MILP_Sheduler(str(data_path), max_hour_check_deferral_days=deferral_days,
                              early_check_penalty=early_check_penalty)
    optimizer.build_model(use_tight_c13_m=tight_c13_m)
    # The full assignment report is too long for a batch table run.
    optimizer.print_report = lambda out_path=None, summary=None: None
    summary = optimizer.solve(solver_name=solver_name, time_limit=time_limit,
                              warm_start=False)
    summary['wall_s'] = time.perf_counter() - started
    return summary, optimizer


def milp_feasibility(optimizer, result, routes):
    """Check a complete heuristic schedule against every active MILP row."""
    if optimizer is None or result['status'] != 'complete':
        return 'not checked'
    if result['ferry_events']:
        return 'no: uses ferry legs'
    try:
        optimizer.set_mip_start_from_routes({'routes': routes, 'unassigned': []})
    except ValueError as exc:
        if 'does not support' in str(exc):
            return 'not checked: multi-day check mapping'
        return f'no: {exc}'
    return 'yes'


def reference_value(summary):
    if summary is None:
        return None, 'none'
    if str(summary.get('status')).lower() == 'optimal' and summary.get('obj') is not None:
        return float(summary['obj']), 'optimal'
    bound = summary.get('dual_bound')
    if bound is not None and bound > 0:
        return float(bound), 'lower_bound'
    return None, 'none'


def gap_percent(objective, reference):
    if objective is None or reference is None or reference <= 0:
        return None
    return 100.0 * (objective - reference) / reference


def comparison_note(row, reference_kind):
    if row['status'] != 'complete':
        return f"{row['status']}: {row['assigned']} flights assigned"
    if reference_kind == 'none':
        return 'no MILP reference'
    notes = []
    if row['milp_feasible'].startswith('no'):
        notes.append('outside the MILP feasible set: ' + row['milp_feasible'][4:])
    if reference_kind == 'lower_bound':
        notes.append('gap measured against lower bound (upper bound on true gap)')
    return '; '.join(notes)


def format_gap(row):
    if row['status'] != 'complete':
        return f"partial ({row['assigned']}/{row['F']})"
    if row['gap_pct'] is None:
        return 'n/a'
    marker = '*' if row['reference_status'] == 'lower_bound' else ''
    if row['milp_feasible'].startswith('no'):
        marker += '+'
    return f"{row['gap_pct']:.2f}%{marker}"


def wide_table(heuristic_rows, methods):
    records = {}
    for row in heuristic_rows:
        record = records.setdefault(row['stem'], {
            'stem': row['stem'], 'P': row['P'], 'airports': row['airports'],
            'maintenance_stations': row['maintenance_stations'], 'H': row['H'],
            'F': row['F'], 'min_turn_min': row['min_turn_min'],
            'reference_status': row['reference_status'],
            'reference_objective': row['reference_objective'],
        })
        record[f"{row['method']}_time_s"] = round(row['cpu_s'], 2)
        record[f"{row['method']}_gap"] = format_gap(row)
    table = pd.DataFrame(records.values())
    table.insert(0, 'sr_no', range(1, len(table) + 1))
    ordered = ['sr_no', 'stem', 'P', 'airports', 'maintenance_stations', 'H', 'F',
               'min_turn_min', 'reference_status', 'reference_objective']
    for method in methods:
        ordered += [f'{method}_time_s', f'{method}_gap']
    return table[[column for column in ordered if column in table.columns]]


def latex_escape(text):
    return str(text).replace('\\', r'\textbackslash{}').replace('%', r'\%').replace('_', r'\_')


def write_latex(table, methods, path):
    headers = ['Sr.\\ No.', 'No.\\ of aircraft', 'No.\\ of airports',
               'Planning horizon', 'No.\\ of flights', 'Min.\\ turn (min)']
    for method in methods:
        name = latex_escape(method.capitalize())
        headers += [f'{name} time (s)', f'{name} gap']
    lines = [
        r'\begin{tabular}{' + 'r' * len(headers) + '}',
        r'\toprule',
        ' & '.join(headers) + r' \\',
        r'\midrule',
    ]
    for _, row in table.iterrows():
        cells = [row['sr_no'], row['P'], row['airports'], f"{row['H']} days", row['F'],
                 f"{row['min_turn_min']:g}"]
        for method in methods:
            cells += [f"{row[f'{method}_time_s']:.2f}",
                      latex_escape(row[f'{method}_gap']).replace('*', r'$^{*}$')
                      .replace('+', r'$^{\dagger}$')]
        lines.append(' & '.join(str(cell) for cell in cells) + r' \\')
    lines += [r'\bottomrule', r'\end{tabular}', '',
              r'% * gap against the MILP lower bound (time limit reached); '
              r'dagger = schedule violates MILP constraints (see the long CSV note); '
              r'partial = heuristic left flights unassigned.']
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input-dir', type=Path, default=ROOT / 'data/instances')
    parser.add_argument('--pattern', default='*.json',
                        help='Glob pattern; use "**/*.json" to include subfolders.')
    parser.add_argument('--methods', nargs='+', default=['dijkstra', 'aco'],
                        choices=HEURISTICS)
    parser.add_argument('--solver', dest='solver_name', default='cplex')
    parser.add_argument('--milp-time-limit', type=int, default=300)
    parser.add_argument('--no-milp', action='store_true',
                        help='Only time the heuristics; gaps are reported as n/a.')
    parser.add_argument('--allow-ferry', action='store_true',
                        help='Allow heuristic ferry legs (not representable in the MILP).')
    parser.add_argument('--max-hour-check-deferral-days', type=parse_deferral_days, default=3)
    parser.add_argument('--tight-c13-m', action='store_true')
    parser.add_argument('--early-check-penalty', type=float,
                        default=DEFAULT_EARLY_CHECK_PENALTY,
                        help='Cost per minute a check is performed before it is due.')
    parser.add_argument('--aco-iterations', type=int, default=20)
    parser.add_argument('--aco-ants', type=int, default=8)
    parser.add_argument('--aco-seed', type=int, default=0)
    parser.add_argument('--output-prefix', type=Path,
                        default=ROOT / 'results/tables/heuristic_gap_table')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')

    files = sorted(args.input_dir.glob(args.pattern))
    if not files:
        parser.error(f'No files match {args.pattern} in {args.input_dir}')
    aco_options = {'aco_iterations': args.aco_iterations, 'aco_ants': args.aco_ants,
                   'aco_seed': args.aco_seed}

    long_rows = []
    heuristic_rows = []
    for data_path in tqdm(files, desc='instances'):
        stem = data_path.stem
        features = instance_features(data_path)
        summary = None
        optimizer = None
        if not args.no_milp:
            try:
                summary, optimizer = run_reference(
                    data_path, args.solver_name, args.milp_time_limit,
                    args.max_hour_check_deferral_days, args.tight_c13_m,
                    args.early_check_penalty)
            except Exception as exc:  # keep the batch going; record the failure
                LOGGER.warning('MILP failed on %s: %s', stem, exc)
                summary = {'status': f'error: {exc}'}
        reference, reference_kind = reference_value(summary)
        base = {'stem': stem, **features,
                'vars': (summary or {}).get('n_vars'),
                'constraints': (summary or {}).get('n_cons'),
                'reference_status': reference_kind, 'reference_objective': reference}
        if summary is not None:
            mip_gap = summary.get('gap')
            long_rows.append({**base, 'method': 'milp', 'status': summary.get('status'),
                              'nodes_max': summary.get('nodes'),
                              'gap_pct': 100.0 * mip_gap if mip_gap is not None else None,
                              'cpu_s': summary.get('wall_s'), 'objective': summary.get('obj'),
                              'early_check_min': summary.get('early_check_minutes'),
                              'assigned': None, 'coverage_pct': None, 'ferry_events': 0,
                              'milp_feasible': 'yes' if reference_kind == 'optimal' else '',
                              'note': 'MILP reference'})

        for method in args.methods:
            result, routes = run_heuristic(data_path, method, args.allow_ferry, aco_options,
                                           args.early_check_penalty)
            row = {**base, **result, 'nodes_max': None,
                   'gap_pct': gap_percent(result['objective'], reference),
                   'milp_feasible': milp_feasibility(optimizer, result, routes)}
            row['note'] = comparison_note(row, reference_kind)
            long_rows.append(row)
            heuristic_rows.append(row)
            LOGGER.info('%s %s: %s, %.2fs, gap=%s', stem, method, row['status'],
                        row['cpu_s'], row['gap_pct'])

    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    long_path = args.output_prefix.with_name(args.output_prefix.name + '_long.csv')
    fields = ['stem', 'method', 'P', 'H', 'F', 'airports', 'maintenance_stations',
              'min_turn_min', 'vars', 'constraints', 'nodes_max', 'gap_pct', 'cpu_s',
              'objective', 'early_check_min', 'status', 'assigned', 'coverage_pct',
              'ferry_events',
              'maintenance_events', 'milp_feasible', 'reference_status',
              'reference_objective', 'note']
    with long_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(long_rows)

    table = wide_table(heuristic_rows, args.methods)
    wide_path = args.output_prefix.with_suffix('.csv')
    tex_path = args.output_prefix.with_suffix('.tex')
    table.to_csv(wide_path, index=False)
    write_latex(table, args.methods, tex_path)

    print(table.to_string(index=False))
    print('* gap against the MILP lower bound (time limit reached)')
    print('+ schedule violates MILP constraints (reason in the long CSV note column)')
    print(f'Saved {wide_path}\nSaved {long_path}\nSaved {tex_path}')


if __name__ == '__main__':
    main()
