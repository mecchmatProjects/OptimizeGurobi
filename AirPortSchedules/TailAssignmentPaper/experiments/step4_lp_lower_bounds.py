#!/usr/bin/env python3
"""
Step 4 Validation: Lower Bounds via LP Relaxation

This script computes LP relaxation lower bounds on TAP instances to support
quality comparison against heuristics.

The LP relaxation provides a rigorous lower bound on the optimal integer solution.
This allows us to compute:
- Heuristic gap from LP lower bound (meaningful even when MILP hits time limit)
- Comparison: Classical MILP (easier) vs Integrated MILP (harder with maintenance)
- Validation: Can heuristics come within X% of provable lower bounds?

CLI
---
--input-dir DIR       Solve every *.json instance in DIR (default: curated
                       hardcoded list kept for backward compatibility).
--pattern GLOB         Glob pattern under --input-dir (default "*.json").
--output PATH          CSV file or directory to write results to.
--solver NAME          Pyomo solver name (highs, cbc, cplex, cplexamp, ...).
--executable PATH      Optional solver executable path.
--time-limit SECONDS   Wall-clock budget applied to every LP solve.
--formulation {classical,integrated,both}
--enabled-checks LIST  Comma-separated subset of A,B,C,D (shrinks |C|).
--sparse-z             Restrict z to feasible (flight,aircraft) arcs only.
--reachability          Drop deferred trigger days a station-departure rules out.
--tight-c13-m          Use interval-specific C13 big-M bounds.
--strong-conflicts     Disaggregate C8 into per-flight conflict rows.
--max-hour-check-deferral-days N
                       Cap A/B check deferral to N days past trigger arrival.
                       This is the dominant lever for large z-variable counts
                       on long-horizon instances. Default 3; none means no cap.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from src.experiment_utils import (
    ExperimentCSV,
    experiment_metadata,
    instance_paths,
)
from src.solver_utils import (
    apply_time_limit,
    extract_bounds,
    finite,
    parse_deferral_days,
    relax_integrality,
    solve_and_load,
    termination_of,
)

DEFAULT_INSTANCES = [
    # Exact-feasible ABCD instances (10-54 flights, full maintenance A/B/C/D)
    ("data/instances/ABCD_no_maint_test.json", "exact"),
    ("data/instances/ABCD_capacity_bottleneck_test.json", "exact"),
    ("data/instances/ABCD_check_hierarchy_test.json", "exact"),
    ("data/instances/ABCD_all_checks_test.json", "exact"),

    # Phase-1 random-grid (for LP lower-bound validation on larger instances)
    ("data/instances/DataCplex_density=0.5_p=10_h=7_test_0.json", "random-grid"),
    ("data/instances/DataCplex_density=1_p=10_h=7_test_0.json", "random-grid"),
    ("data/instances/DataCplex_density=0.95_p=10_h=7_test_0.json", "random-grid"),
]


def solve_lp_lower_bound(instance_path, solver_name='cplex', time_limit=30,
                          use_maintenance=True, executable=None,
                          enabled_checks=None, sparse_z=False,
                          reachability=False, tight_c13_m=False,
                          strong_conflicts=False, max_deferral_days=3,
                          allow_ferry=True, tee=False):
    """
    Compute LP relaxation lower bound for a TAP instance.

    Parameters
    ----------
    instance_path : Path
        JSON instance file
    solver_name : str
        Pyomo solver (highs, cbc, cplex, ...)
    time_limit : int
        Wall-clock time limit in seconds
    use_maintenance : bool
        Include maintenance constraints (vs. basic routing only)
    enabled_checks : list[str] | None
        Restrict the active check types (e.g. ['A']); shrinks the maintenance
        trigger domain by a factor of |enabled_checks| / 4.
    sparse_z, reachability, tight_c13_m, strong_conflicts : bool
        Model-building options. The station-wait reachability filter is an
        experimental restriction, not formulation-equivalent preprocessing.
    max_deferral_days : int | None
        Caps how many days an A/B (flight-hour) check may be deferred past
        its trigger flight's arrival day. Explicit None means candidate days
        span the entire remaining horizon, which is the dominant source of
        z-variable blow-up on long-horizon, many-aircraft instances.

    Returns
    -------
    dict with keys: instance, n_var, n_con, status, lp_bound, runtime_s
    """
    from pyomo.environ import Constraint, SolverFactory, Var

    from src.model import MILP_Sheduler

    instance_path = Path(instance_path)
    name = instance_path.stem
    started = time.perf_counter()
    row = {'instance': name, 'n_var': None, 'n_con': None, 'z_vars': None,
           'status': 'error', 'lp_bound': None, 'runtime_s': None,
           'max_deferral_days': max_deferral_days,
           'restrictive_deferral': use_maintenance and max_deferral_days is not None, 'error': ''}

    try:
        # Build model
        log.info(f"Building model: {name}")
        scheduler = MILP_Sheduler(
            instance_path,
            enabled_checks=enabled_checks,
            max_hour_check_deferral_days=max_deferral_days,
        )
        scheduler.build_model(
            use_maintenance=use_maintenance,
            use_sparse_maint_aircraft_domain=sparse_z,
            use_maint_reachability=reachability,
            use_tight_c13_m=tight_c13_m,
            use_strong_maint_conflicts=strong_conflicts,
            allow_ferry=allow_ferry,
        )
        model = scheduler.model
        if model is None:
            raise RuntimeError('Model construction returned no model.')
        relax_integrality(model)
        row.update(n_var=sum(1 for _ in model.component_data_objects(Var)),
                   n_con=sum(1 for _ in model.component_data_objects(Constraint)),
                   z_vars=scheduler.z_var_count, flights=len(scheduler.flight_ids),
                   aircraft=len(scheduler.aircraft_ids), days=len(scheduler.days),
                   build_s=time.perf_counter() - started)

        # Solve LP
        log.info(f"Solving LP relaxation ({solver_name}, {time_limit}s)")
        solver_kwargs = {"executable": str(executable)} if executable else {}
        solver = SolverFactory(solver_name, **solver_kwargs)
        apply_time_limit(solver, solver_name, time_limit)

        solve_started = time.perf_counter()
        results, _loaded, _objective = solve_and_load(solver, model, tee=tee)
        status = termination_of(results)
        dual, primal, gap, nodes = extract_bounds(results)
        row.update(status=status, lp_bound=dual if status.lower() == 'optimal' else None,
                   dual_bound=dual, primal_bound=primal, mip_gap=gap, nodes=nodes,
                   runtime_s=time.perf_counter() - solve_started)
        log.info('  z_vars=%s LP bound=%s status=%s', row['z_vars'], row['lp_bound'], status)

    except Exception as e:
        log.exception('Failed %s', name)
        row['error'] = f'{type(e).__name__}: {e}'
    row['wall_s'] = time.perf_counter() - started
    return row


def routing_feasibility_status(instance_path, solver_name='cplex', time_limit=60,
                               executable=None, allow_ferry=True, return_details=False, **_kwargs):
    row = solve_lp_lower_bound(instance_path, solver_name=solver_name,
                               time_limit=time_limit, executable=executable,
                               use_maintenance=False, allow_ferry=allow_ferry)
    return row if return_details else row['status']


def validate_lp_results(rows, reference=None, atol=1e-6, rtol=1e-8):
    summary = {'violations': [], 'n_lower_bound_valid': 0, 'unavailable': 0,
               'uncompared': 0}
    reference = reference or {}
    for row in rows:
        if row.get('status', '').lower() != 'optimal':
            summary['unavailable'] += 1
            continue
        bound = finite(row.get('lp_bound'))
        if bound is None:
            summary['violations'].append(f"{row.get('instance')}: non-finite optimal LP bound")
            continue
        key = (row.get('instance'), row.get('formulation'))
        expected = reference.get(key, reference.get(row.get('instance')))
        if isinstance(expected, dict):
            config = expected.get('config', {})
            comparable = {name: 'none' if val is None else str(val) for name, val in config.items()}
            if any(str(row.get(name)) != val for name, val in comparable.items()):
                summary['uncompared'] += 1
                continue
            expected = expected.get('objective')
        elif row.get('restrictive_deferral') in (True, 'True', 'true'):
            summary['uncompared'] += 1
            continue
        expected = finite(expected)
        if expected is None:
            summary['uncompared'] += 1
        elif bound > expected + atol + rtol * abs(expected):
            summary['violations'].append(f"{row.get('instance')}: LP {bound} > reference {expected}")
        else:
            summary['n_lower_bound_valid'] += 1
    return summary


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input-dir', type=Path, default=None,
                        help="Solve every instance under this directory "
                             "instead of the curated default list.")
    parser.add_argument('--pattern', default='*.json',
                        help="Glob pattern applied under --input-dir.")
    parser.add_argument('--output', type=Path,
                        default=Path("results/tables/step4_lp_lower_bounds.csv"),
                        help="Output CSV path, or a directory to write "
                             "step4_lp_lower_bounds.csv into.")
    parser.add_argument('--solver', default='cplex')
    parser.add_argument('--executable', type=Path, default=None)
    parser.add_argument('--time-limit', type=int, default=30)
    parser.add_argument('--formulation', choices=('classical', 'integrated', 'both'),
                        default='both')
    parser.add_argument('--enabled-checks', default='',
                        help="Comma-separated subset of A,B,C,D. Restricting "
                             "this is the fastest way to shrink a large "
                             "maintenance-trigger domain.")
    parser.add_argument('--sparse-z', action='store_true',
                        help="Aircraft-compatible sparse maintenance domain.")
    parser.add_argument('--reachability', action='store_true',
                        help="Filter deferred trigger days by station reachability.")
    parser.add_argument('--tight-c13-m', action='store_true',
                        help="Interval-specific C13 big-M bounds.")
    parser.add_argument('--strong-conflicts', action='store_true',
                        help="Disaggregate C8 into per-flight conflict rows.")
    parser.add_argument('--max-hour-check-deferral-days', type=parse_deferral_days, default=3,
                        help="Cap how far an A/B check may be deferred past its "
                             "trigger flight's arrival day. Without this, a "
                             "trigger's candidate days span the entire remaining "
                             "horizon, which is the dominant cause of z-variable "
                             "blow-up on long-horizon, many-aircraft instances.")
    parser.add_argument('--routing-preflight', action='store_true')
    parser.add_argument('--include-routing-infeasible', action='store_true',
                        help='Bypass preflight and record that provenance.')
    parser.add_argument('--preflight-time-limit', type=int, default=60)
    parser.add_argument('--tee', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--overwrite', action='store_true')
    return parser.parse_args(argv)


def main(argv=None):
    """Compute LP bounds for the requested instances."""
    args = parse_args(argv)

    enabled_checks = [c.strip().upper() for c in args.enabled_checks.split(',') if c.strip()] or None

    if args.input_dir:
        paths = instance_paths(args.input_dir, args.pattern)
        instances_to_solve = [(str(p), 'random-grid') for p in paths]
        if not instances_to_solve:
            log.warning(f"No instances matched {args.input_dir}/{args.pattern}")
    else:
        instances_to_solve = DEFAULT_INSTANCES

    output_path = args.output
    if output_path.suffix.lower() != '.csv':
        output_path = output_path / "step4_lp_lower_bounds.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    formulations = (['classical', 'integrated'] if args.formulation == 'both'
                    else [args.formulation])

    paths = [Path(path) for path, _family in instances_to_solve]
    metadata = experiment_metadata(Path(__file__).resolve().parents[1], paths, vars(args))
    fieldnames = ['instance', 'family', 'formulation', 'n_var', 'n_con', 'z_vars',
                  'status', 'lp_bound', 'runtime_s', 'build_s', 'wall_s',
                  'routing_status', 'preflight_s', 'total_wall_s', 'error',
                  'max_deferral_days', 'restrictive_deferral', 'reused_preflight',
                  'dual_bound', 'primal_bound', 'mip_gap', 'nodes']
    with ExperimentCSV(output_path, fieldnames, metadata, args.resume, args.overwrite) as output, \
            ExperimentCSV(output_path.with_suffix('.audit.csv'),
                          ['instance', 'routing_status', 'preflight_s', 'action'],
                          metadata, args.resume, args.overwrite) as audit:
        completed = {(row['instance'], row['formulation']) for row in output.previous
                     if row['status'] not in ('error', 'build-error')}
        skipped = {row['instance'] for row in audit.previous if row['action'] == 'skipped'}
        for inst_path, family in tqdm(instances_to_solve, desc='LP instances'):
            inst_path = Path(inst_path)
            if not inst_path.exists():
                log.warning('Missing instance: %s', inst_path)
                continue
            if inst_path.stem in skipped:
                continue
            pending = [form for form in formulations if (inst_path.stem, form) not in completed]
            if not pending:
                continue
            routing_status = 'included_without_preflight'
            cached_preflight = None
            preflight_started = time.perf_counter()
            if args.routing_preflight and not args.include_routing_infeasible:
                try:
                    preflight = routing_feasibility_status(
                        inst_path, solver_name=args.solver, executable=args.executable,
                        time_limit=args.preflight_time_limit, return_details=True)
                    if isinstance(preflight, dict):
                        cached_preflight = preflight
                        routing_status = preflight['status']
                    else:
                        routing_status = preflight
                except Exception:
                    log.exception('Preflight failed; retaining %s', inst_path.stem)
                    routing_status = 'error'
            preflight_s = time.perf_counter() - preflight_started
            skip = routing_status.lower() == 'infeasible'
            audit.write({'instance': inst_path.stem, 'routing_status': routing_status,
                         'preflight_s': preflight_s, 'action': 'skipped' if skip else 'retained'})
            if skip:
                continue
            for index, formulation in enumerate(pending):
                reuse = formulation == 'classical' and cached_preflight is not None and routing_status.lower() == 'optimal'
                if reuse and isinstance(cached_preflight, dict):
                    result = cached_preflight.copy()
                else:
                    result = solve_lp_lower_bound(
                        inst_path, solver_name=args.solver, time_limit=args.time_limit,
                        use_maintenance=(formulation == 'integrated'), executable=args.executable,
                        enabled_checks=enabled_checks, sparse_z=args.sparse_z,
                        reachability=args.reachability, tight_c13_m=args.tight_c13_m,
                        strong_conflicts=args.strong_conflicts,
                        max_deferral_days=args.max_hour_check_deferral_days, tee=args.tee)
                result.update(family=family, formulation=formulation, routing_status=routing_status,
                              reused_preflight=reuse, preflight_s=preflight_s if index == 0 else 0,
                              total_wall_s=(0 if reuse else result.get('wall_s', 0)) +
                                            (preflight_s if index == 0 else 0))
                output.write(result)
    log.info('Wrote %s (with audit, metadata and log)', output_path)
    return 0


if __name__ == '__main__':
    main()
