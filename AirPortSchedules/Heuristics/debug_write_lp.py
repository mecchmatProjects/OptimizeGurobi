"""Write LP file with symbolic labels and check if MIP presolve finds conflict."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from heu180h import MILP_Sheduler
from pyomo.environ import *

sched = MILP_Sheduler('inputsABCD/ABCD_multi_check_test.json')
m = sched.build_model(use_check_hierarchy=False)

# Write the LP file
m.write('debug_full.lp', io_options={'symbolic_solver_labels': True})
print("LP written to debug_full.lp")
print(f"Variables: {len(list(m.component_data_objects(ctype=Var)))}")
print(f"Constraints: {len(list(m.component_data_objects(ctype=Constraint)))}")

# Now let's try to find the IIS using cplex
solver = SolverFactory('cplex')
solver.options['iis'] = 'yes'  # CPLEX: compute IIS  
solver.options['conflict'] = 1  # CPLEX conflict refiner
result = solver.solve(m, tee=True)
print(f"\nStatus: {result.solver.termination_condition}")
