from heu180h import MILP_Sheduler
from pyomo.environ import *
from pyomo.opt import SolverFactory

opt = MILP_Sheduler("inputsABCD/ABCD_two_b_one_c_test.json")
m = opt.build_model(use_maintenance=True, use_check_hierarchy=False)
solver = SolverFactory('cplex')

# What constraints touch x[7,3] (F7 by AC3)?
print("Constraints on x[7,3]:")
for name in ['c8', 'c15', 'c23', 'c_overlap', 'c1']:
    ct = getattr(m, name, None)
    if ct is None: continue
    for idx, con in ct.items():
        body = str(con.body)
        if 'x[7,3]' in body or 'x[7, 3]' in body:
            print(f"  {name}[{idx}]: {body}")

# What constraints touch x[7,4]?
print("Constraints on x[7,4]:")
for name in ['c8', 'c15', 'c23', 'c_overlap', 'c1']:
    ct = getattr(m, name, None)
    if ct is None: continue
    for idx, con in ct.items():
        body = str(con.body)
        if 'x[7,4]' in body or 'x[7, 4]' in body:
            print(f"  {name}[{idx}]: {body}")
