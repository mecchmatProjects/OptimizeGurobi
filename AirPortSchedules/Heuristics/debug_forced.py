"""
Force intended assignments and print all active constraints that are violated.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from heu180h import MILP_Sheduler
from pyomo.environ import *

data = json.load(open('inputsABCD/ABCD_multi_check_test.json'))
intended = {data['Flights'][i][0]: next(j for j,c in enumerate(data['Cost_Matrix'][i]) if c==1000.0)
            for i in range(len(data['Flights']))}

sched = MILP_Sheduler('inputsABCD/ABCD_multi_check_test.json')
m = sched.build_model(use_check_hierarchy=False)

# Force x variables to intended
m.c_forced = ConstraintList()
for fid, j in intended.items():
    for j2 in range(5):
        if j2 == j:
            m.c_forced.add(m.x[fid, j2] == 1)
        else:
            m.c_forced.add(m.x[fid, j2] == 0)

print("Forced assignments:")
for fid, j in sorted(intended.items()):
    print(f"  F{fid} -> AC{j}")

solver = SolverFactory('cplex')
result = solver.solve(m, tee=False)
tc = str(result.solver.termination_condition)
print(f"\nStatus with forced assignments: {tc}")

if tc in ('optimal', 'feasible'):
    print("  -> Intended assignment IS feasible. MILP infeasibility is due to cost optimization driving model to bad area.")
    # Print active checks
    for j in range(5):
        for d in sorted(sched.days):
            for c in ['A','B','C','D']:
                yv = value(m.y[j,d,c])
                if yv and yv > 0.5:
                    print(f"  AC{j} day{d} {c}-check")
else:
    print("  -> Intended assignment is INFEASIBLE too. The schedule design is wrong.")
    
    # Try relaxing each constraint group one at a time WITH forced assignment
    for attr in ['c8','c9','c10','c11','c12','c12b','c12days','c13','c13b','c14','c14b','c15','c23','c_overlap','c_hierarchy']:
        sched2 = MILP_Sheduler('inputsABCD/ABCD_multi_check_test.json')
        m2 = sched2.build_model(use_check_hierarchy=False)
        comp = getattr(m2, attr, None)
        if comp:
            comp.deactivate()
        # Force assignment
        m2.c_forced = ConstraintList()
        for fid, j in intended.items():
            for j2 in range(5):
                m2.c_forced.add(m2.x[fid, j2] == (1 if j2 == j else 0))
        r = solver.solve(m2, tee=False)
        tc_ = str(r.solver.termination_condition)
        ok = tc_ in ('optimal','feasible')
        print(f"  {'✓' if ok else '✗'} Remove {attr}: {tc_}")
        if ok:
            break  # found culprit
