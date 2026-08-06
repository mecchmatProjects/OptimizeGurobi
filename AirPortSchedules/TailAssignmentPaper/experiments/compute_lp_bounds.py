#!/usr/bin/env python3
"""
Compute LP relaxation lower bounds for MILP instances.

This script solves the LP relaxation (all variables continuous) for instances
where the MILP hits time limits. The LP bound provides a rigorous lower bound
on the optimal integer solution, allowing us to quantify heuristic gaps even
when MILP optimality is not certified.

Usage:
  python experiments/compute_lp_bounds.py --input-dir data/instances/ \\
    --instances-glob "DataCplex_density=*_p=10_h=7*" --solver highs \\
    --time-limit 30 --output results/tables/lp_bounds.csv
"""

import argparse
import json
import sys
from pathlib import Path
import csv
import logging
from pyomo.environ import (
    ConcreteModel, Constraint, Var, Binary, NonNegativeReals, Objective,
    SolverFactory, value as pyo_value, ConstraintList, Block
)

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
log = logging.getLogger(__name__)


def relax_model(model):
    """Create a continuous relaxation of a Pyomo model by changing all Binary
    variables to Continuous [0, 1].
    
    Parameters
    ----------
    model : ConcreteModel
        Original MILP model with Binary variables
        
    Returns
    -------
    ConcreteModel
        New model with all Binary variables relaxed to Continuous
    """
    relaxed = model.clone()
    
    # Find all Binary variables and change them to Continuous
    for var in relaxed.component_data_objects(ctype=Var):
        if var.domain == Binary:
            # Relax to continuous [0, 1]
            var.domain = NonNegativeReals
            var.bounds = (0, 1)
    
    return relaxed


def solve_lp_relaxation(instance_path, solver_name='highs', time_limit=30, tee=False):
    """Solve the LP relaxation of a TAP instance and return the bound.
    
    Parameters
    ----------
    instance_path : str | Path
        Path to JSON instance file
    solver_name : str
        Pyomo solver name (e.g., 'highs', 'cbc', 'cplex')
    time_limit : int
        Wall-clock time limit in seconds
    tee : bool
        Stream solver log to stdout
        
    Returns
    -------
    dict
        Keys: instance_name, n_vars, n_cons, status, obj (LP bound),
              runtime_s, gap_vs_heuristic (if heuristic obj provided)
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from model import MILP_Sheduler
    
    instance_path = Path(instance_path)
    instance_name = instance_path.stem
    
    try:
        # Load and build the model
        with open(instance_path) as f:
            data = json.load(f)
        
        scheduler = MILP_Sheduler(data)
        scheduler.build_model(use_maintenance=True)
        
        # Relax to LP
        relaxed_model = relax_model(scheduler.model)
        
        # Solve LP relaxation
        solver = SolverFactory(solver_name)
        if time_limit:
            _sn = solver_name.lower()
            if 'highs' in _sn or 'cbc' in _sn:
                solver.options['TimeLimit'] = int(time_limit)
            elif 'cplex' in _sn:
                solver.options['timelimit'] = int(time_limit)
        
        log.info(f"Solving LP relaxation: {instance_name} ({solver_name})")
        results = solver.solve(relaxed_model, tee=tee)
        
        n_var = len(list(relaxed_model.component_data_objects(ctype=Var)))
        n_con = len(list(relaxed_model.component_data_objects(ctype=Constraint)))
        status = str(results.solver.termination_condition)
        lp_obj = pyo_value(relaxed_model.obj) if results.solver.termination_condition.name == 'optimal' else None
        runtime = getattr(results.solver, 'time', None)
        
        return {
            'instance': instance_name,
            'n_vars': n_var,
            'n_cons': n_con,
            'status': status,
            'lp_bound': lp_obj,
            'runtime_s': runtime
        }
    
    except Exception as e:
        log.error(f"Failed to solve {instance_name}: {e}")
        return {
            'instance': instance_name,
            'status': 'error',
            'lp_bound': None,
            'runtime_s': None,
            'error': str(e)
        }


def compute_lp_bounds_batch(input_dir, instances_glob, solver_name, time_limit, output_csv):
    """Compute LP bounds for a batch of instances.
    
    Parameters
    ----------
    input_dir : str | Path
        Directory containing instance JSON files
    instances_glob : str
        Glob pattern for instance files (relative to input_dir)
    solver_name : str
        Pyomo solver name
    time_limit : int
        Time limit per instance in seconds
    output_csv : str | Path
        Output CSV file path
    """
    input_dir = Path(input_dir)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    
    # Find instances
    instances = sorted(input_dir.glob(instances_glob))
    log.info(f"Found {len(instances)} instances matching '{instances_glob}'")
    
    results = []
    for i, inst_path in enumerate(instances, 1):
        log.info(f"[{i}/{len(instances)}] Processing {inst_path.name}")
        result = solve_lp_relaxation(inst_path, solver_name=solver_name, 
                                    time_limit=time_limit)
        results.append(result)
    
    # Write results
    fieldnames = ['instance', 'n_vars', 'n_cons', 'status', 'lp_bound', 'runtime_s']
    with open(output_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({k: row.get(k) for k in fieldnames})
    
    log.info(f"Wrote results to {output_csv}")
    
    # Summary
    successful = sum(1 for r in results if r['status'] == 'optimal')
    log.info(f"Successfully solved {successful}/{len(results)} instances to LP optimality")


def main():
    parser = argparse.ArgumentParser(
        description="Compute LP relaxation lower bounds for MILP instances"
    )
    parser.add_argument('--input-dir', default='data/instances/',
                       help='Directory containing instance JSON files')
    parser.add_argument('--instances-glob', default='DataCplex_density=*_p=10_h=7*',
                       help='Glob pattern for instance files')
    parser.add_argument('--solver', default='highs',
                       help='Pyomo solver name (highs, cbc, cplex, …)')
    parser.add_argument('--time-limit', type=int, default=30,
                       help='Time limit per instance in seconds')
    parser.add_argument('--output', default='results/tables/lp_bounds.csv',
                       help='Output CSV file path')
    parser.add_argument('--verbose', action='store_true',
                       help='Stream solver logs to stdout')
    
    args = parser.parse_args()
    
    compute_lp_bounds_batch(
        input_dir=args.input_dir,
        instances_glob=args.instances_glob,
        solver_name=args.solver,
        time_limit=args.time_limit,
        output_csv=args.output
    )


if __name__ == '__main__':
    main()
