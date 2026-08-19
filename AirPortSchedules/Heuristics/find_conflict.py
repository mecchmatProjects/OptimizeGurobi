"""
Find which constraint group causes infeasibility by deactivating one at a time.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logging
logging.disable(logging.CRITICAL)

from heu180h import MILP_Sheduler
from pyomo.opt import SolverFactory, TerminationCondition
from pyomo.core import Var, Constraint

DATA = 'inpytABCD/ABCD_all_checks_test.json'

def is_feasible(m):
    solver = SolverFactory('cplex')
    solver.options['timelimit'] = 15
    r = solver.solve(m, tee=False)
    tc = r.solver.termination_condition
    return 'optimal' in str(tc).lower() or 'feasible' in str(tc).lower()

print("Building model...")
sch = MILP_Sheduler(DATA)
sch.build_model(use_check_hierarchy=False)
m = sch.model
n_var = sum(1 for _ in m.component_data_objects(ctype=Var))
n_con = sum(1 for _ in m.component_data_objects(ctype=Constraint))
print(f"Vars={n_var}, Constraints={n_con}")

constraint_groups = ['c1', 'c23', 'c8', 'c9', 'c10', 'c11', 'c_hierarchy',
                     'c12', 'c12b', 'c12days', 'c13', 'c13b', 'c14', 'c14b',
                     'c15', 'c_overlap']

print(f"\n{'Group':<15} {'Result without it':<25}")
print("-" * 40)
for cg_name in constraint_groups:
    cg = getattr(m, cg_name, None)
    if cg is None:
        print(f"{cg_name:<15} (not found)")
        continue
    cg.deactivate()
    feas = is_feasible(m)
    cg.activate()
    marker = "  <-- REMOVING THIS FIXES IT" if feas else ""
    print(f"{cg_name:<15} {'FEASIBLE' if feas else 'still infeasible'}{marker}")
