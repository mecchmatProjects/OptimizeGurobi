"""Diagnose ABCD_multi_check_test infeasibility: LP relaxation + IIS-style analysis."""
import sys, logging
logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '.')

from heu180h import MILP_Sheduler
from pyomo.environ import *
from pyomo.core import ConstraintList, TransformationFactory

sched = MILP_Sheduler('inputsABCD/ABCD_multi_check_test.json')
m = sched.build_model(use_check_hierarchy=False, use_existing_hrs=True)

print('=== Constraints ===')
for attr in sorted(dir(m)):
    obj = getattr(m, attr, None)
    if isinstance(obj, ConstraintList):
        try:
            n = len(list(obj))
            print(f'  {attr}: {n}')
        except Exception:
            pass

solver = SolverFactory('cplex')

# LP relaxation
m_relax = m.clone()
TransformationFactory('core.relax_integer_vars').apply_to(m_relax)
res = solver.solve(m_relax, tee=False)
print(f'\nLP relaxation: {res.solver.termination_condition}, obj={value(m_relax.obj) if res.solver.termination_condition == "optimal" else "N/A"}')

# Try removing individual constraint groups to find the culprit
for cname in ['c8','c9','c10','c11','c12','c12b','c12days','c13','c13b','c14','c14b','c15','c23','c_hierarchy','c_overlap']:
    if not hasattr(m, cname):
        continue
    m2 = m.clone()
    TransformationFactory('core.relax_integer_vars').apply_to(m2)
    cobj = getattr(m2, cname)
    cobj.deactivate()
    r = solver.solve(m2, tee=False)
    tc = str(r.solver.termination_condition)
    print(f'  Remove {cname}: {tc}')
