"""LP relaxation timing test for h=15 -- compare LP methods."""
import time
from heu180h import MILP_Sheduler
from pyomo.environ import NonNegativeReals, value, Var
from pyomo.opt import SolverFactory

data_file = 'Inputs/DataCplex_density=1_p=10_h=15_test_0.json'

# Test barrier (fastest for large LPs) with and without crossover, plus primal
for method, name, crossover in [(4, 'barrier_no_cross', -1),
                                  (4, 'barrier_cross',    0),
                                  (1, 'primal',           None)]:
    opt = MILP_Sheduler(data_file)
    opt.build_model()
    m = opt.model

    for v in m.component_data_objects(ctype=Var):
        v.domain = NonNegativeReals
        v.setub(1.0)

    s = SolverFactory('cplex')
    s.options['lpmethod'] = method
    if crossover is not None:
        s.options['barrier crossover'] = crossover
    s.options['timelimit'] = 300

    print(f"\nMethod={method} ({name}), crossover={crossover}...")
    t0 = time.time()
    r = s.solve(m, tee=False)
    wall = time.time() - t0

    try:
        obj_val = f"{value(m.obj):.4f}"
    except Exception:
        obj_val = "N/A"
    print(f"  Status: {r.solver.termination_condition}")
    print(f"  Obj:    {obj_val}")
    print(f"  CPlex:  {r.solver.time:.2f}s")
    print(f"  Wall:   {wall:.2f}s")
