#!/usr/bin/env python3
"""
Step 4 Validation: Lower Bounds via LP Relaxation

This script computes LP relaxation lower bounds on a curated subset of instances
(mix of exact-feasible and Phase-1 random-grid) to support quality comparison
against heuristics.

The LP relaxation provides a rigorous lower bound on the optimal integer solution.
This allows us to compute:
- Heuristic gap from LP lower bound (meaningful even when MILP hits time limit)
- Comparison: Classical MILP (easier) vs Integrated MILP (harder with maintenance)
- Validation: Can heuristics come within X% of provable lower bounds?
"""

import json
import sys
from pathlib import Path
import csv
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def solve_lp_lower_bound(instance_path, solver_name='highs', time_limit=30, use_maintenance=True):
    """
    Compute LP relaxation lower bound for a TAP instance.
    
    Parameters
    ----------
    instance_path : Path
        JSON instance file
    solver_name : str
        Pyomo solver (highs, cbc, cplex, …)
    time_limit : int
        Wall-clock time limit in seconds
    use_maintenance : bool
        Include maintenance constraints (vs. basic routing only)
        
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
        with open(instance_path) as f:
            data = json.load(f)
        
        # Build model
        log.info(f"Building model: {name}")
        scheduler = MILP_Sheduler(instance_path)
        scheduler.build_model(use_maintenance=use_maintenance)
        model = scheduler.model
        
        # Relax all Binary variables to Continuous [0, 1]
        for var in model.component_data_objects(ctype=Var):
            if var.domain == Binary:
                var.domain = NonNegativeReals
                var.bounds = (0, 1)
        
        # Solve LP
        log.info(f"Solving LP relaxation ({solver_name}, {time_limit}s)")
        solver = SolverFactory(solver_name)
        
        if time_limit:
            if 'highs' in solver_name.lower():
                solver.options['TimeLimit'] = int(time_limit)
            elif 'cplex' in solver_name.lower():
                solver.options['timelimit'] = int(time_limit)
        
        results = solver.solve(model, tee=False)
        
        n_var = len(list(model.component_data_objects(ctype=Var)))
        n_con = len(list(model.component_data_objects(ctype=Constraint)))
        status = str(results.solver.termination_condition)
        lp_bound = pyo_value(model.obj) if results.solver.termination_condition == TerminationCondition.optimal else None
        runtime = getattr(results.solver, 'time', None)
        if runtime is None:
            runtime = 0.0
        
        log.info(f"  LP bound: {lp_bound}, status: {status}, time: {runtime:.1f}s")
        
        return {
            'instance': name,
            'n_var': n_var,
            'n_con': n_con,
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
            'status': 'error',
            'lp_bound': None,
            'runtime_s': None
        }


def main():
    """
    Compute LP bounds for representative instances.
    
    Strategy:
    - Exact-feasible: ABCD curated instances with full maintenance model
    - Phase-1 random-grid: 3 instances (varying density) for comparison
    """
    
    instances_to_solve = [
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
    
    output_dir = Path("results/tables")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Solve LP bounds: Classical (no maintenance) and Integrated (with maintenance)
    results = []
    for inst_path, family in instances_to_solve:
        inst_path = Path(inst_path)
        
        if not inst_path.exists():
            log.warning(f"Instance not found: {inst_path}")
            continue
        
        log.info(f"\n=== {inst_path.name} ({family}) ===")
        
        # Classical (routing only)
        result_classical = solve_lp_lower_bound(inst_path, use_maintenance=False)
        result_classical['family'] = family
        result_classical['formulation'] = 'classical'
        results.append(result_classical)
        
        # Integrated (with maintenance)
        result_integrated = solve_lp_lower_bound(inst_path, use_maintenance=True)
        result_integrated['family'] = family
        result_integrated['formulation'] = 'integrated'
        results.append(result_integrated)
    
    # Write results
    output_csv = output_dir / "step4_lp_lower_bounds.csv"
    fieldnames = ['instance', 'family', 'formulation', 'n_var', 'n_con',
                  'status', 'lp_bound', 'runtime_s']
    
    with open(output_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({k: row.get(k) for k in fieldnames})
    
    log.info(f"\n✓ Wrote LP bounds to {output_csv}")
    
    # Summary
    successful = sum(1 for r in results if r['status'] == 'optimal')
    log.info(f"\nSummary: {successful}/{len(results)} LP instances solved to optimality")
    
    for r in results:
        if r['status'] == 'optimal':
            log.info(f"  {r['instance']:30s} {r['formulation']:12s} bound={r['lp_bound']:10.0f} vars={r['n_var']:6d} {r['runtime_s']:6.1f}s")


if __name__ == '__main__':
    main()
