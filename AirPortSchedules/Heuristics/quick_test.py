#!/usr/bin/env python3
# Quick test: just build the model (no solve) and report constraint counts
import sys, time

sys.path.insert(0, '.')
from heu180h import MILP_Sheduler

data = 'Inputs/DataCplex_density=1_p=10_h=7_test_0.json'

print("Building model with all maintenance flags ON...")
t0 = time.time()
opt = MILP_Sheduler(data)
opt.build_model(
    use_day_spacing=True,
    use_existing_hrs=True,
    use_check_hierarchy=True,
    use_sanity=False,
    use_overlap=False,
    allow_ferry=False,
    use_maintenance=True,
)
t1 = time.time()
m = opt.model
print(f"Model built in {t1-t0:.1f}s")
# Count blocks
for name, block in m.component_map(active=True).items():
    from pyomo.core import ConstraintList, Constraint
    if isinstance(block, (ConstraintList, Constraint)):
        try:
            n = len(list(block))
        except Exception:
            n = '?'
        print(f"  {name}: {n} constraints")

print("Done.")
