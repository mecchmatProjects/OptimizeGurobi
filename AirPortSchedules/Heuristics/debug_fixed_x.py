"""
Fix x variables to the intended routing and solve for y/z/mega variables only.
This tests if the maintenance constraints are satisfiable given the correct routing.
"""
from heu180h import MILP_Sheduler
import pyomo.environ as pyo

sched = MILP_Sheduler('inputsABCD/ABCD_multi_check_test.json')
sched.build_model()
m = sched.model

# The intended integral routing (flight_id -> aircraft_id)
intended_x = {
    (1, 0): 1, (2, 0): 1,
    (3, 1): 1, (4, 4): 1,
    (5, 1): 1, (6, 1): 1, (7, 1): 1,
    (8, 0): 1, (9, 0): 1,
    (10, 4): 1, (11, 4): 1,
    (12, 0): 1, (13, 0): 1,
    (14, 0): 1, (15, 0): 1,
    (16, 4): 1, (17, 4): 1,
    (18, 0): 1, (19, 0): 1,
    (20, 0): 1,
    (21, 2): 1, (22, 3): 1,
    (23, 2): 1, (24, 3): 1,
    (25, 2): 1, (26, 2): 1,
    (27, 3): 1, (28, 3): 1,
}

# Fix all x variables 
for i in m.F:
    for j in m.P:
        val = intended_x.get((i, j), 0)
        m.x[i, j].fix(val)

solver = pyo.SolverFactory('cplex')
print("Solving with x fixed to intended routing...")

# Try LP relaxation first (relax y, z, mega)
for v in m.component_objects(pyo.Var, active=True):
    for idx in v:
        if v[idx].domain == pyo.Binary and not v[idx].is_fixed():
            v[idx].domain = pyo.NonNegativeReals
            v[idx].setub(1.0)

res = solver.solve(m, tee=False)
status = str(res.solver.termination_condition)
print(f"LP relaxation (x fixed): {status}")

if 'optimal' in status or 'feasible' in status:
    import pyomo.environ as pyo2
    obj = pyo.value(m.obj)
    print(f"  Obj = {obj:.2f}")
    
    # Show y (checks scheduled)
    print("\n  Scheduled checks (y[j,d,c] > 0.01):")
    for (j, d, c), var in m.y.items():
        val = pyo.value(var)
        if val is not None and val > 0.01:
            print(f"    y[AC{j},day{d},{c}] = {val:.3f}")
else:
    print("  Still infeasible with x fixed!")
    print("  Checking which constraints are problematic...")
    
    # Deactivate constraint groups one by one  
    constraint_groups = ['c8', 'c9', 'c10', 'c11', 'c12', 'c12b', 'c12days',
                         'c13', 'c13b', 'c14', 'c14b', 'c15', 'c23', 'c_hierarchy', 'c_overlap']
    
    for cname in constraint_groups:
        # Rebuild model with x fixed
        sched2 = MILP_Sheduler('inputsABCD/ABCD_multi_check_test.json')
        sched2.build_model()
        m2 = sched2.model
        
        for i in m2.F:
            for j in m2.P:
                val = intended_x.get((i, j), 0)
                m2.x[i, j].fix(val)
        
        for v in m2.component_objects(pyo.Var, active=True):
            for idx in v:
                if v[idx].domain == pyo.Binary and not v[idx].is_fixed():
                    v[idx].domain = pyo.NonNegativeReals
                    v[idx].setub(1.0)
        
        c = getattr(m2, cname, None)
        if c is not None:
            c.deactivate()
        
        res2 = solver.solve(m2, tee=False)
        s2 = str(res2.solver.termination_condition)
        print(f"    Remove {cname}: {s2}")
        if 'optimal' in s2 or 'feasible' in s2:
            print(f"      -> Removing {cname} makes it FEASIBLE!")
