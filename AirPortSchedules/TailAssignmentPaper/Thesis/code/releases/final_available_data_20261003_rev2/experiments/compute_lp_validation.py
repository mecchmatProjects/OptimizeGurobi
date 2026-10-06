#!/usr/bin/env python3
"""
Compute LP relaxation bounds for Phase-2 random-grid instances.

This creates a validation table showing:
- Heuristic cost (greedy from Phase-2)
- LP lower bound
- Heuristic gap from LP bound (%)

Since MILP hits time limits on Phase-2 instances, the LP bound provides a
rigorous lower bound on the optimal solution, allowing us to quantify how
close heuristics are to the true optimum.
"""

import sys
from pathlib import Path
import json
import csv
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyomo.environ import (
    Var, Constraint, Binary, NonNegativeReals, SolverFactory, 
    value as pyo_value, TerminationCondition
)
from model import MILP_Sheduler


def solve_lp_bound(instance_path, solver_name='highs', time_limit=30):
    """Solve LP relaxation to get lower bound for an instance.
    
    Returns dict with keys: instance, p, flights, lp_bound, status, runtime_s
    """
    instance_path = Path(instance_path)
    instance_name = instance_path.stem
    
    try:
        # Load instance
        with open(instance_path) as f:
            data = json.load(f)
        
        p = len(data.get('Aircrafts', []))
        flights = len(data.get('Flights', []))
        
        # Build MILP model
        log.info(f"Building model for {instance_name}")
        scheduler = MILP_Sheduler(data)
        scheduler.build_model(use_maintenance=True)
        
        # Relax: change all Binary variables to Continuous [0, 1]
        model = scheduler.model
        for var in model.component_data_objects(ctype=Var):
            if var.domain == Binary:
                var.domain = NonNegativeReals
                var.bounds = (0, 1)
        
        # Solve LP relaxation
        log.info(f"Solving LP relaxation ({solver_name}, {time_limit}s limit)")
        solver = SolverFactory(solver_name)
        
        if time_limit:
            if 'highs' in solver_name.lower():
                solver.options['TimeLimit'] = int(time_limit)
            elif 'cplex' in solver_name.lower():
                solver.options['timelimit'] = int(time_limit)
        
        results = solver.solve(model, tee=False)
        
        status = str(results.solver.termination_condition)
        lp_obj = pyo_value(model.obj) if results.solver.termination_condition == TerminationCondition.optimal else None
        runtime = getattr(results.solver, 'time', None)
        
        return {
            'instance': instance_name,
            'p': p,
            'flights': flights,
            'lp_bound': lp_obj,
            'status': status,
            'runtime_s': runtime
        }
    
    except Exception as e:
        log.error(f"Failed: {e}")
        return {
            'instance': instance_name,
            'p': p if 'p' in locals() else None,
            'flights': flights if 'flights' in locals() else None,
            'lp_bound': None,
            'status': 'error',
            'runtime_s': None
        }


def compute_phase2_validation():
    """Compute LP bounds and heuristic gaps for Phase-2 instances."""
    
    phase2_dir = Path("results/tables")
    phase2_csv = phase2_dir / "phase2_summary.csv"
    
    if not phase2_csv.exists():
        log.error(f"Phase-2 summary not found: {phase2_csv}")
        return
    
    # Read Phase-2 results
    phase2 = {}
    with open(phase2_csv) as f:
        reader = csv.DictReader(f)
        for row in reader:
            instance = row['instance']
            if instance not in phase2:
                phase2[instance] = {}
            method = row['method']
            phase2[instance][method] = {
                'cost': float(row['cost']) if row.get('cost') else None,
                'status': row.get('status')
            }
    
    log.info(f"Loaded {len(phase2)} Phase-2 instances")
    
    # Select a subset for LP bound computation (representative instances)
    # Choose: one instance from each tier (easy, medium, hard)
    instance_dir = Path("data/instances")
    
    representative = [
        "DataCplex_density=0.5_p=10_h=7_test_0",    # easy
        "DataCplex_density=0.75_p=10_h=7_test_0",   # medium
        "DataCplex_density=0.95_p=10_h=7_test_0",   # hard
    ]
    
    lp_results = []
    output_dir = Path("results/tables")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for instance_name in representative:
        instance_path = instance_dir / f"{instance_name}.json"
        if instance_path.exists():
            log.info(f"\n=== Computing LP bound for {instance_name} ===")
            result = solve_lp_bound(instance_path, solver_name='highs', time_limit=30)
            
            # Add Phase-2 heuristic results
            if instance_name in phase2:
                greedy_cost = phase2[instance_name].get('greedy', {}).get('cost')
                ls_cost = phase2[instance_name].get('local_search', {}).get('cost')
                
                result['greedy_cost'] = greedy_cost
                result['ls_cost'] = ls_cost
                
                if result['lp_bound'] and greedy_cost:
                    result['greedy_gap_pct'] = 100 * (greedy_cost - result['lp_bound']) / result['lp_bound']
                else:
                    result['greedy_gap_pct'] = None
                    
                if result['lp_bound'] and ls_cost:
                    result['ls_gap_pct'] = 100 * (ls_cost - result['lp_bound']) / result['lp_bound']
                else:
                    result['ls_gap_pct'] = None
            
            lp_results.append(result)
            log.info(f"LP bound: {result['lp_bound']}, "
                    f"Greedy gap: {result.get('greedy_gap_pct', 'N/A'):.1f}%")
    
    # Write results
    output_csv = output_dir / "lp_bounds_validation.csv"
    fieldnames = ['instance', 'p', 'flights', 'lp_bound', 'status', 'runtime_s',
                  'greedy_cost', 'greedy_gap_pct', 'ls_cost', 'ls_gap_pct']
    
    with open(output_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in lp_results:
            writer.writerow({k: row.get(k) for k in fieldnames})
    
    log.info(f"\nWrote results to {output_csv}")
    return lp_results


if __name__ == '__main__':
    compute_phase2_validation()
