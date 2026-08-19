"""Debug script: diagnose ABCD_capacity_bottleneck_test infeasibility."""
import sys, logging
logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '.')

from heu180h import MILP_Sheduler
from pyomo.environ import *
from pyomo.core import ConstraintList

sched = MILP_Sheduler('inputsABCD/ABCD_capacity_bottleneck_test.json')

m = sched.build_model(use_check_hierarchy=False, use_existing_hrs=True)

print('=== Constraints ===')
for attr in sorted(dir(m)):
    obj = getattr(m, attr, None)
    if isinstance(obj, ConstraintList):
        try:
            n = len(list(obj))
            print(f'  {attr}: {n}')
        except Exception as e:
            print(f'  {attr}: ERROR {e}')

# Solve LP relaxation to see if it's feasible
from pyomo.environ import SolverFactory
from pyomo.core import TransformationFactory

m_relax = m.clone()
TransformationFactory('core.relax_integer_vars').apply_to(m_relax)
solver = SolverFactory('cplex')
res = solver.solve(m_relax, tee=False)
print(f'\nLP relaxation: {res.solver.termination_condition}, obj={value(m_relax.obj):.2f}')

# Check all constraints with expected solution
import re
expected_x = {(1,0): 1, (2,1): 1, (3,2): 1, (4,0): 1, (5,1): 1, (6,2): 1, (7,0): 1, (8,1): 1}
expected_z = {(1,0,1,'A'): 1, (2,1,2,'A'): 1, (3,2,3,'A'): 1}

# Expected y values from C11 (z=y)
expected_y = {}
flight_data = sched.flight_data
for (i,j,d,c), v in expected_z.items():
    expected_y[(j,d,c)] = v

# Expected mega from c_hierarchy (we used no-hierarchy, so mega=y)
expected_mega = expected_y.copy()

def eval_expr(expr_str):
    """Very rough evaluator for simple z/x/y/mega sums."""
    total = 0.0
    for zm in re.findall(r'z\[(\d+),(\d+),(\d+),(\w+)\]', expr_str):
        total += expected_z.get((int(zm[0]),int(zm[1]),int(zm[2]),zm[3]), 0)
    for xm in re.findall(r'x\[(\d+),(\d+)\]', expr_str):
        total += expected_x.get((int(xm[0]),int(xm[1])), 0)
    for ym in re.findall(r'y\[(\d+),(\d+),(\w+)\]', expr_str):
        total += expected_y.get((int(ym[0]),int(ym[1]),ym[2]), 0)
    for mm in re.findall(r'mega\[(\d+),(\d+),(\w+)\]', expr_str):
        total += expected_mega.get((int(mm[0]),int(mm[1]),mm[2]), 0)
    return total

print('\n=== All violated constraints with expected solution ===')
for cname in ['c8','c9','c10','c11','c13','c13b','c14','c14b','c15','c23']:
    if hasattr(m, cname):
        cobj = getattr(m, cname)
        violated = []
        for idx, con in cobj.items():
            body_str = str(con.body)
            body_val = eval_expr(body_str)
            # Check if constraint is violated
            # Most are <= 1 or == something
            lb = con.lb
            ub = con.ub
            if ub is not None and body_val > float(ub) + 1e-6:
                violated.append((idx, body_str, body_val, f'<= {ub}'))
            elif lb is not None and body_val < float(lb) - 1e-6:
                violated.append((idx, body_str, body_val, f'>= {lb}'))
        if violated:
            print(f'\n{cname}: {len(violated)} violations')
            for idx, body, val, sense in violated[:10]:
                print(f'  [{idx}]: {body} = {val:.4f} (expected {sense})')
        else:
            print(f'{cname}: OK')
