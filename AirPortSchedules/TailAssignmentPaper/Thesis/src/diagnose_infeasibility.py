"""Quick diagnostic: find which maintenance constraint group causes infeasibility."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from heu180h import MILP_Sheduler
from pyomo.environ import Constraint

FP = "Inputs/DataCplex_density=1_p=10_h=7_test_0.json"
SOLVER = 'cplex'

def test(label, **kwargs):
    opt = MILP_Sheduler(FP)
    m = opt.build_model(allow_ferry=False, use_overlap=False, use_sanity=False, **kwargs)
    nc  = sum(1 for _ in m.component_data_objects(ctype=Constraint))
    info = opt.solve(solver_name=SOLVER, tee=False, time_limit=30)
    print(f"  {label:48s}  {info['status']:15s}  cons={nc:>9,}  cpu={info['cpu'] or 0:5.1f}s")

print(f"\nDataset: {FP}   solver={SOLVER}\n")
print(f"  {'Scenario':48s}  {'Status':15s}  {'Constraints':>10}  CPU")
print("  " + "-"*90)

# Full maintenance
test("all maintenance ON",                              use_maintenance=True)

# Drop individual optional groups
test("drop C12 day-spacing",                           use_maintenance=True, use_day_spacing=False)
test("drop C13b existing-hrs",                         use_maintenance=True, use_existing_hrs=False)
test("drop C12 + C13b",                                use_maintenance=True, use_day_spacing=False, use_existing_hrs=False)
test("drop check hierarchy",                           use_maintenance=True, use_check_hierarchy=False)
test("drop C12 + C13b + hierarchy",                    use_maintenance=True, use_day_spacing=False,
                                                        use_existing_hrs=False, use_check_hierarchy=False)

# Compare: no maintenance (pure assignment lower bound)
test("NO maintenance (lower bound)",                   use_maintenance=False)

print()
