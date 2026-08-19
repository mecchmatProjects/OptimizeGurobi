"""Proper constraint checker: set expected solution, evaluate via Pyomo value()."""
import sys, logging
logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '.')

from heu180h import MILP_Sheduler
from pyomo.environ import *
from pyomo.core import ConstraintList

sched = MILP_Sheduler('inputsABCD/ABCD_capacity_bottleneck_test.json')
m = sched.build_model(use_check_hierarchy=False, use_existing_hrs=True)

# ------ Set all variables to 0 first ------
for v in m.component_data_objects(Var, active=True):
    v.set_value(0)

# Expected solution
expected_x = {(1,0):1, (2,1):1, (3,2):1, (4,0):1, (5,1):1, (6,2):1, (7,0):1, (8,1):1}
expected_z = {(1,0,1,'A'):1, (2,1,2,'A'):1, (3,2,3,'A'):1}
expected_y = {(0,1,'A'):1, (1,2,'A'):1, (2,3,'A'):1}
expected_mega = expected_y.copy()

for (i,j), v in expected_x.items():
    try: m.x[i,j].set_value(v)
    except KeyError: print(f'WARNING: x[{i},{j}] not in model')

for (i,j,d,c), v in expected_z.items():
    try: m.z[i,j,d,c].set_value(v)
    except KeyError: print(f'WARNING: z[{i},{j},{d},{c}] not in model')

for (j,d,c), v in expected_y.items():
    try: m.y[j,d,c].set_value(v)
    except KeyError: print(f'WARNING: y[{j},{d},{c}] not in model')

for (j,d,c), v in expected_mega.items():
    try: m.mega[j,d,c].set_value(v)
    except KeyError: print(f'WARNING: mega[{j},{d},{c}] not in model')

# ------ Check each constraint ------
print('=== Constraint check with expected solution ===')
ALL_CNTS = ['c8','c9','c10','c11','c13','c13b','c14','c14b','c15','c23','c_hierarchy','c_overlap']
for cname in ALL_CNTS:
    if not hasattr(m, cname):
        continue
    cobj = getattr(m, cname)
    violated = []
    for idx, con in cobj.items():
        try:
            body_val = value(con.body)
        except Exception as e:
            print(f'  {cname}[{idx}] eval error: {e}')
            continue
        lb = con.lb
        ub = con.ub
        if ub is not None and body_val > float(ub) + 1e-6:
            violated.append((idx, str(con.body)[:120], body_val, f'<= {float(ub):.1f}'))
        elif lb is not None and body_val < float(lb) - 1e-6:
            violated.append((idx, str(con.body)[:120], body_val, f'>= {float(lb):.1f}'))

    if violated:
        print(f'\n{cname}: {len(violated)} VIOLATIONS')
        for idx, body, val, sense in violated[:15]:
            print(f'  [{idx}]: val={val:.4f} (expected {sense})')
            print(f'         {body}')
    else:
        print(f'{cname}: OK')
