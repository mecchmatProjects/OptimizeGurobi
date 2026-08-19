"""Find minimal infeasible constraint combination."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from heu180h import MILP_Sheduler
from pyomo.environ import *

def test_combo(deactivate, label):
    sched = MILP_Sheduler('inputsABCD/ABCD_multi_check_test.json')
    m = sched.build_model(use_check_hierarchy=False)
    for attr in deactivate:
        comp = getattr(m, attr, None)
        if comp is not None:
            comp.deactivate()
    solver = SolverFactory('cplex')
    result = solver.solve(m, tee=False)
    tc = str(result.solver.termination_condition)
    ok = tc in ('optimal', 'feasible')
    sym = '✓' if ok else '✗'
    print(f"  {sym} [{label}]: {tc}")
    return ok

print("=== c12days interaction analysis ===\n")
# c12days alone removes feasibility
print("Testing with c12days removed:")
test_combo(["c12days"], "no c12days")

# What does c12days interact with?
print("\nc12days + other removed:")
combos = [
    (["c12days","c23"], "no c12days+c23"),
    (["c12days","c15"], "no c12days+c15"),
    (["c12days","c10"], "no c12days+c10"),
    (["c12days","c11"], "no c12days+c11"),
    (["c12days","c8"],  "no c12days+c8"),
    (["c12days","c12"], "no c12days+c12"),
    (["c12days","c12b"],"no c12days+c12b"),
    (["c12days","c14"], "no c12days+c14"),
    (["c12days","c14b"],"no c12days+c14b"),
    (["c12days","c13"], "no c12days+c13"),
]
for d, l in combos:
    test_combo(d, l)

# Now test: which single constraint blocks c12days?
print("\n\nWith c12days ACTIVE, removing one other:")
combos2 = [
    (["c23"],    "no c23"),
    (["c15"],    "no c15"),
    (["c10"],    "no c10"),
    (["c11"],    "no c11"),  # already known feasible
    (["c8"],     "no c8"),   # already known infeasible
    (["c12"],    "no c12"),  # already known
    (["c12b"],   "no c12b"),
    (["c14"],    "no c14"),
    (["c14b"],   "no c14b"),
    (["c13"],    "no c13"),
    (["c13b"],   "no c13b"),
    (["c_overlap"],"no overlap"),
]
for d, l in combos2:
    test_combo(d, l)

# Can we find minimal 2-set that fixes it (without c12days)?
print("\n\nWith ALL constraints active: which 2-pair removes infeasibility?")
print("(only checking pairs involving c12days)") 
