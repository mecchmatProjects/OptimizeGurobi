"""
IIS finder for the ABCD_multi_check_test.json MILP.
Uses CPLEX's conflict refiner via LP relaxation.
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from heu180h import AircraftScheduler

sched = AircraftScheduler(
    data_path='inputsABCD/ABCD_multi_check_test.json',
    no_check_hierarchy=True,
    no_ferry=False,
    no_maintenance=False,
    no_overlap=False,
    no_sanity=False,
)
m = sched.build_model()

# Relax all binaries to [0,1] and solve as LP
from pyomo.environ import *

# Make it an LP
for var in m.component_data_objects(ctype=Var):
    var.domain = NonNegativeReals
    var.setub(1.0)
    var.setlb(0.0)

solver = SolverFactory('cplex')
solver.options['lpmethod'] = 4   # barrier
result = solver.solve(m, tee=True)
tc = str(result.solver.termination_condition)
print(f"\nLP relaxation status: {tc}")

if tc == 'infeasible':
    print("LP is infeasible → presolve can identify IIS")
    # Write to LP file for analysis
    m.write('debug_iis_model.lp', io_options={'symbolic_solver_labels': True})
    print("Written to debug_iis_model.lp")
else:
    from pyomo.environ import value as pyo_val
    print(f"LP obj = {pyo_val(m.obj):.2f}")
