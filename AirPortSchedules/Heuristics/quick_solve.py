#!/usr/bin/env python3
# Minimal test: full solve with 30s limit, just print status
import sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from heu180h import MILP_Sheduler

data = 'Inputs/DataCplex_density=1_p=10_h=7_test_0.json'

print("Building model...")
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
print(f"Built in {t1-t0:.1f}s")

print("Solving with 30s limit...")
t2 = time.time()
summary = opt.solve(solver_name='cplex', tee=False, time_limit=30)
t3 = time.time()
print(f"Solved in {t3-t2:.1f}s")
print(f"Status: {summary.get('status')}")
print(f"Obj: {summary.get('obj')}")
print(f"Gap: {summary.get('gap')}")
