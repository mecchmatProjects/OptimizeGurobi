"""Quick test: does adding forced assignments + disabling c14b fix infeasibility?"""
import json
from pyomo.environ import *

# Use the full heu180h model but with c14b disabled
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# We'll build and modify the model
from heu180h import MILP_Sheduler

sched = MILP_Sheduler('inputsABCD/ABCD_multi_check_test.json')
m = sched.build_model(use_check_hierarchy=False)

# Remove c14b to test if that's the problem
m.c14b.deactivate()
print("c14b DEACTIVATED")

solver = SolverFactory('cplex')
result = solver.solve(m, tee=False)
tc = str(result.solver.termination_condition)
print(f"Status without c14b: {tc}")

if tc == 'optimal':
    print("  -> c14b was causing infeasibility!")
    # Show check assignments
    for j in sorted(sched.aircraft_ids):
        for d in sched.days:
            for c in ['A','B','C','D']:
                yv = value(m.y[j,d,c])
                if yv and yv > 0.5:
                    print(f"  AC{j} day{d} {c}-check: y={yv:.0f}")
else:
    print("  -> c14b is NOT the culprit; problem is elsewhere")
    
    # Re-activate c14b, try without c13b
    m.c14b.activate()
    m.c13b.deactivate()
    print("\nc14b ACTIVE, c13b DEACTIVATED")
    result2 = solver.solve(m, tee=False)
    tc2 = str(result2.solver.termination_condition)
    print(f"Status without c13b: {tc2}")
    
    if tc2 == 'optimal':
        print("  -> c13b was causing infeasibility!")
    else:
        # Try without c13
        m.c13b.activate()
        m.c13.deactivate()
        print("\nc13b ACTIVE, c13 DEACTIVATED")
        result3 = solver.solve(m, tee=False)
        tc3 = str(result3.solver.termination_condition)
        print(f"Status without c13: {tc3}")
        
        if tc3 == 'optimal':
            print("  -> c13 was causing infeasibility!")
        else:
            # Try without c15
            m.c13.activate()
            m.c15.deactivate()
            print("\nc13 ACTIVE, c15 DEACTIVATED")  
            result4 = solver.solve(m, tee=False)
            tc4 = str(result4.solver.termination_condition)
            print(f"Status without c15: {tc4}")
            
            if tc4 == 'optimal':
                print("  -> c15 was causing infeasibility!")
            else:
                print("  -> Problem is in c8, c9, c10, c11, c12, c23, or c1")
