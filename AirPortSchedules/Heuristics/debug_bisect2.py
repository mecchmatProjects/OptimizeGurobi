"""Constraint bisection phase 2 - lower-level constraints"""
import json
from pyomo.environ import *
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from heu180h import MILP_Sheduler

def test(label, deactivate_list, extra_force=None):
    sched = MILP_Sheduler('inputsABCD/ABCD_multi_check_test.json')
    m = sched.build_model(use_check_hierarchy=False)
    for attr in deactivate_list:
        comp = getattr(m, attr, None)
        if comp is not None:
            comp.deactivate()
        else:
            print(f"  Warning: {attr} not found in model")
    if extra_force:
        for (var_name, *idx), val in extra_force.items():
            pass  # skip
    solver = SolverFactory('cplex')
    result = solver.solve(m, tee=False)
    tc = str(result.solver.termination_condition)
    print(f"  [{label}]: {tc}")
    return tc == 'optimal' or tc == 'feasible'

print("=== Phase 2: Testing c8, c9, c10, c11, c12, c12b, c12days, c23 ===\n")

# Test each individually
tests = [
    ("no c8",        ["c8"]),
    ("no c9",        ["c9"]),
    ("no c10",       ["c10"]),
    ("no c11",       ["c11"]),
    ("no c12",       ["c12"]),
    ("no c12b",      ["c12b"]),
    ("no c12days",   ["c12days"]),
    ("no c23",       ["c23"]),
    ("no c_overlap", ["c_overlap"]),
    ("no c8+c9",     ["c8", "c9"]),
    ("no c8+c23",    ["c8", "c23"]),
    ("no c11+c12",   ["c11", "c12", "c12b", "c12days"]),
    ("no maintenance (c8-c15)", ["c8","c9","c10","c11","c_hierarchy","c14","c14b","c12","c12b","c12days","c13","c13b","c15"]),
]

results = {}
for label, deactivated in tests:
    r = test(label, deactivated)
    results[label] = r

print("\n=== Summary ===")
for label, ok in results.items():
    print(f"  {label}: {'FEASIBLE' if ok else 'infeasible'}")
