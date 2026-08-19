"""
Detailed check: fix x to routing, then check maintenance constraints step by step.
"""
from heu180h import MILP_Sheduler
import pyomo.environ as pyo

sched = MILP_Sheduler('inputsABCD/ABCD_multi_check_test.json')
sched.build_model()
m = sched.model

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

for i in m.F:
    for j in m.P:
        m.x[i, j].fix(intended_x.get((i, j), 0))

for v in m.component_objects(pyo.Var, active=True):
    for idx in v:
        if v[idx].domain == pyo.Binary and not v[idx].is_fixed():
            v[idx].domain = pyo.NonNegativeReals
            v[idx].setub(1.0)

solver = pyo.SolverFactory('cplex')

# Check which FM (maintenance flights) exist for each aircraft
print("=== FM (maintenance flights) by aircraft ===")
for j in m.P:
    fm_j = [i for i in m.FM if intended_x.get((i, j), 0) == 1]
    print(f"  AC{j}: FM flights = {fm_j}")
    for i in fm_j:
        fd = sched.flight_data[i]
        print(f"    F{i}: {fd['origin']}->{fd['destination']} arr={fd['arrivalTime']:.0f}")

print()
print("=== Day of arrival for each FM flight ===")
for j in m.P:
    for i in m.FM:
        if intended_x.get((i, j), 0) == 1:
            fd = sched.flight_data[i]
            d_arr = int(fd['arrivalTime'] // 1440)
            print(f"  AC{j} F{i}: arr={fd['arrivalTime']:.0f} -> day={d_arr}")

print()
print("=== Initial check values ===")
ic = sched.init_checks
print(f"  A init:      AC0={ic['A'].get('0',0)}, AC1={ic['A'].get('1',0)}, AC2={ic['A'].get('2',0)}, AC3={ic['A'].get('3',0)}, AC4={ic['A'].get('4',0)}")
print(f"  B init:      AC0={ic['B'].get('0',0)}, AC1={ic['B'].get('1',0)}, ...")
print(f"  C_Days init: AC0={ic['C_Days'].get('0',0)}, AC1={ic['C_Days'].get('1',0)}, AC2={ic['C_Days'].get('2',0)}, AC3={ic['C_Days'].get('3',0)}")
print(f"  D_Days init: AC0={ic['D_Days'].get('0',0)}, ..., AC3={ic['D_Days'].get('3',0)}")

print()
print("=== Thresholds & durations ===")
print(f"  A: thresh={sched.thresh_ab['A']}, dur={sched.durations['A']}")
print(f"  B: thresh={sched.thresh_ab['B']}, dur={sched.durations['B']}")
print(f"  C: thresh={sched.thresh_cd['C']}, dur={sched.durations['C']}")
print(f"  D: thresh={sched.thresh_cd['D']}, dur={sched.durations['D']}")

print()
print("=== Horizon ===")
print(f"  Days: {sched.horizon}")

# Remove c23, deactivate, and try MIP (binary) 
m.c23.deactivate()
for v in m.component_objects(pyo.Var, active=True):
    for idx in v:
        if not v[idx].is_fixed():
            v[idx].domain = pyo.Binary

res = solver.solve(m, tee=False)
status = str(res.solver.termination_condition)
print(f"\n=== MIP solve (x fixed, c23 removed, y/z/mega binary): {status} ===")
try:
    obj = pyo.value(m.obj)
    if obj is not None:
        print(f"Obj = {obj:.2f}")
        for (j,d,c), var in m.y.items():
            val = pyo.value(var)
            if val is not None and val > 0.5:
                print(f"  y[AC{j},day{d},{c}]=1")
except:
    pass
