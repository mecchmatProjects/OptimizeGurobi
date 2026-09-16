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
                       on long-horizon, many-aircraft instances; unset, the
                       candidate days span the whole remaining horizon.
"""

import argparse
import json
import sys
from pathlib import Path
import csv
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

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


def apply_time_limit(solver, solver_name, time_limit):
    """Set the wall-clock limit using the option name each backend expects.

    Pyomo solver plugins do not share one option name for the time budget,
    so silently using the wrong key (e.g. 'TimeLimit' on CPLEX) is accepted
    without error and simply never binds.
    """
    if not time_limit:
        return
    name = solver_name.lower()
    config = getattr(solver, "config", None)
    if config is not None and hasattr(config, "time_limit"):
        config.time_limit = float(time_limit)
        return
    options = solver.options
    if "cplex" in name:
        options["timelimit"] = int(time_limit)
    elif "gurobi" in name:
        options["TimeLimit"] = int(time_limit)
    elif "glpk" in name:
        options["tmlim"] = int(time_limit)
    elif "highs" in name:
        options["time_limit"] = float(time_limit)
    else:
        options["TimeLimit"] = int(time_limit)


def solve_lp_lower_bound(instance_path, solver_name='highs', time_limit=30,
                          use_maintenance=True, executable=None,
                          enabled_checks=None, sparse_z=False,
                          reachability=False, tight_c13_m=False,
                          strong_conflicts=False, max_deferral_days=None):
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
        Strengthening/preprocessing flags from MILP_Sheduler.build_model that
        shrink the trigger-variable domain without changing the formulation's
        feasible set; use these for large instances (long horizon, many
        maintenance-eligible flights) where the full trigger domain is too
        large to build in reasonable time.
    max_deferral_days : int | None
        Caps how many days an A/B (flight-hour) check may be deferred past
        its trigger flight's arrival day. Unset, a trigger's candidate days
        span the entire remaining horizon, which is the dominant source of
        z-variable blow-up on long-horizon, many-aircraft instances.

    Returns
    -------
    dict with keys: instance, n_var, n_con, status, lp_bound, runtime_s
    """
    from pyomo.environ import (
        Var, Constraint, Binary, NonNegativeReals, SolverFactory,
        value as pyo_value, TerminationCondition
    )
    from model import MILP_Sheduler

    instance_path = Path(instance_path)
    name = instance_path.stem

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
        )
        model = scheduler.model

        # Relax all Binary variables to Continuous [0, 1]
        for var in model.component_data_objects(ctype=Var):
            if var.domain == Binary:
                var.domain = NonNegativeReals
                var.bounds = (0, 1)

        # Solve LP
        log.info(f"Solving LP relaxation ({solver_name}, {time_limit}s)")
        solver_kwargs = {"executable": str(executable)} if executable else {}
        solver = SolverFactory(solver_name, **solver_kwargs)
        apply_time_limit(solver, solver_name, time_limit)

        results = solver.solve(model, tee=False)

        n_var = len(list(model.component_data_objects(ctype=Var)))
        n_con = len(list(model.component_data_objects(ctype=Constraint)))
        status = str(results.solver.termination_condition)
        lp_bound = pyo_value(model.obj) if results.solver.termination_condition == TerminationCondition.optimal else None
        runtime = getattr(results.solver, 'time', None)
        if runtime is None:
            runtime = 0.0

        log.info(f"  z_vars={scheduler.z_var_count}  LP bound: {lp_bound}, status: {status}, time: {runtime:.1f}s")

        return {
            'instance': name,
            'n_var': n_var,
            'n_con': n_con,
            'z_vars': scheduler.z_var_count,
            'status': status,
            'lp_bound': lp_bound,
            'runtime_s': runtime
        }

    except Exception as e:
        import traceback
        log.error(f"Failed: {e}")
        log.error(traceback.format_exc())
        return {
            'instance': name,
            'n_var': None,
            'n_con': None,
            'z_vars': None,
            'status': 'error',
            'lp_bound': None,
            'runtime_s': None
        }


def parse_args():
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
    parser.add_argument('--solver', default='highs')
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
    parser.add_argument('--max-hour-check-deferral-days', type=int, default=None,
                        help="Cap how far an A/B check may be deferred past its "
                             "trigger flight's arrival day. Without this, a "
                             "trigger's candidate days span the entire remaining "
                             "horizon, which is the dominant cause of z-variable "
                             "blow-up on long-horizon, many-aircraft instances.")
    return parser.parse_args()


def main():
    """Compute LP bounds for the requested instances."""
    args = parse_args()

    enabled_checks = [c.strip().upper() for c in args.enabled_checks.split(',') if c.strip()] or None

    if args.input_dir:
        paths = sorted(args.input_dir.glob(args.pattern))
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

    results = []
    for inst_path, family in instances_to_solve:
        inst_path = Path(inst_path)

        if not inst_path.exists():
            log.warning(f"Instance not found: {inst_path}")
            continue

        log.info(f"\n=== {inst_path.name} ({family}) ===")

        for formulation in formulations:
            result = solve_lp_lower_bound(
                inst_path,
                solver_name=args.solver,
                time_limit=args.time_limit,
                use_maintenance=(formulation == 'integrated'),
                executable=args.executable,
                enabled_checks=enabled_checks,
                sparse_z=args.sparse_z,
                reachability=args.reachability,
                tight_c13_m=args.tight_c13_m,
                strong_conflicts=args.strong_conflicts,
                max_deferral_days=args.max_hour_check_deferral_days,
            )
            result['family'] = family
            result['formulation'] = formulation
            results.append(result)

    if not results:
        log.warning("No results to write.")
        return

    fieldnames = ['instance', 'family', 'formulation', 'n_var', 'n_con',
                  'z_vars', 'status', 'lp_bound', 'runtime_s']

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({k: row.get(k) for k in fieldnames})

    log.info(f"\n\u2713 Wrote LP bounds to {output_path}")

    successful = sum(1 for r in results if r['status'] == 'optimal')
    log.info(f"\nSummary: {successful}/{len(results)} LP instances solved to optimality")

    for r in results:
        if r['status'] == 'optimal':
            log.info(f"  {r['instance']:30s} {r['formulation']:12s} bound={r['lp_bound']:10.0f} vars={r['n_var']:6d} {r['runtime_s']:6.1f}s")


if __name__ == '__main__':
    main()
