"""
Find which PAIR of constraint groups causes infeasibility.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logging
logging.disable(logging.CRITICAL)

from heu180h import MILP_Sheduler
from pyomo.opt import SolverFactory
from pyomo.core import Var, Constraint

DATA = 'inpytABCD/ABCD_all_checks_test.json'

def build_and_check(groups_to_keep):
    """Build fresh model with only specific constraint groups active."""
    sch = MILP_Sheduler(DATA)
    sch.build_model(use_check_hierarchy=False)
    m = sch.model
    all_groups = ['c1', 'c23', 'c8', 'c9', 'c10', 'c11', 'c_hierarchy',
                  'c12', 'c12b', 'c12days', 'c13', 'c13b', 'c14', 'c14b',
                  'c15', 'c_overlap']
    # Deactivate groups NOT in groups_to_keep
    for cg_name in all_groups:
        if cg_name not in groups_to_keep:
            cg = getattr(m, cg_name, None)
            if cg is not None:
                cg.deactivate()
    solver = SolverFactory('cplex')
    solver.options['timelimit'] = 10
    r = solver.solve(m, tee=False)
    tc = str(r.solver.termination_condition).lower()
    return 'optimal' in tc or 'feasible' in tc

# First, find which groups are involved: when all are active it's infeasible.
# We know removing any single group makes it feasible.
# So we need to find the minimal set. Start with pairs.

all_groups = ['c1', 'c23', 'c8', 'c9', 'c10', 'c11', 'c_hierarchy',
              'c12', 'c12b', 'c12days', 'c13', 'c13b', 'c14', 'c14b',
              'c15', 'c_overlap']

print("Testing pairs of constraints (is pair alone infeasible?)...")
print()
infeasible_pairs = []
for i, g1 in enumerate(all_groups):
    for g2 in all_groups[i+1:]:
        feas = build_and_check([g1, g2])
        if not feas:
            print(f"  INFEASIBLE pair: {g1} + {g2}")
            infeasible_pairs.append((g1, g2))

if not infeasible_pairs:
    print("No infeasible pairs found. Checking triples...")
    # The IIS requires 3+ groups
    for i, g1 in enumerate(all_groups):
        for j, g2 in enumerate(all_groups[i+1:], i+1):
            for g3 in all_groups[j+1:]:
                feas = build_and_check([g1, g2, g3])
                if not feas:
                    print(f"  INFEASIBLE triple: {g1} + {g2} + {g3}")
                    infeasible_pairs.append((g1, g2, g3))
                    break  # find first occurrence
            if infeasible_pairs:
                break
        if infeasible_pairs:
            break

print("\nDone.")
