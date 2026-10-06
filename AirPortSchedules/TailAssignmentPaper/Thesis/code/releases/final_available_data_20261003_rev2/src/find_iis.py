"""
Standalone IIS (Irreducible Infeasible Subsystem) finder for ABCD_all_checks_test.json.
Uses CPLEX conflict refiner via cplex Python API directly (not Pyomo).
Falls back to manual constraint enumeration if cplex API not available.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Build the model via the existing class, then write LP and analyze
from heu180h import MILP_Sheduler as AircraftScheduler

DATA = 'inpytABCD/ABCD_all_checks_test.json'

print("Building model...")
sch = AircraftScheduler(DATA)
sch.build_model(use_check_hierarchy=False)
m = sch.model

print(f"Model: {sum(1 for _ in m.component_data_objects(ctype=__import__('pyomo.core',fromlist=['Var']).Var))} vars, "
      f"{sum(1 for _ in m.component_data_objects(ctype=__import__('pyomo.core',fromlist=['Constraint']).Constraint))} constraints")

# Write LP file for inspection
from pyomo.opt import ProblemFormat
lp_file = 'OUT_TEST/debug_infeas.lp'
m.write(lp_file, format='lp')
print(f"LP written to {lp_file}")

# Use CPLEX conflict refiner
print("\nRunning CPLEX conflict refiner (IIS)...")
try:
    from pyomo.opt import SolverFactory
    solver = SolverFactory('cplex')
    solver.options['conflict'] = 1      # enable conflict refiner
    solver.options['conflictdisplay'] = 2  # verbose conflict output
    r = solver.solve(m, tee=True, symbolic_solver_labels=True)
    print(f"\nStatus: {r.solver.termination_condition}")
except Exception as e:
    print(f"IIS attempt failed: {e}")
    # Manual: try commenting out one constraint group at a time
    print("\nTrying to identify which constraint group causes infeasibility...")
    
    from pyomo.opt import SolverFactory, TerminationCondition
    
    constraint_groups = ['c1', 'c23', 'c8', 'c9', 'c10', 'c11', 'c_hierarchy', 
                         'c12', 'c12b', 'c12days', 'c13', 'c13b', 'c14', 'c14b', 
                         'c15', 'c_overlap']
    
    def try_without(group_name):
        import pyomo.environ as pe
        cg = getattr(m, group_name, None)
        if cg is None:
            return None
        # Deactivate the constraint group
        cg.deactivate()
        solver = SolverFactory('cplex')
        solver.options['timelimit'] = 10
        r = solver.solve(m, tee=False)
        tc = r.solver.termination_condition
        cg.activate()
        return tc
    
    print(f"{'Group':<15} {'Without it':<20}")
    print("-" * 35)
    for cg in constraint_groups:
        tc = try_without(cg)
        if tc is None:
            print(f"{cg:<15} (not found)")
        else:
            marker = " <-- FEASIBLE! This group causes infeasibility" if 'optimal' in str(tc).lower() or 'feasible' in str(tc).lower() else ""
            print(f"{cg:<15} {str(tc):<20}{marker}")
