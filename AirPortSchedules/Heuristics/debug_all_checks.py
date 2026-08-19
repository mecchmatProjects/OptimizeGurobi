"""
Debug script for ABCD_all_checks_test infeasibility.
Tests constraint deactivation to find the blocking constraints.
"""
import sys, json, importlib.util

DATA = 'inpytABCD/ABCD_all_checks_test.json'
sys.argv = ['heu180h.py', '--data', DATA,
            '--solver', 'cplex', '--no-check-hierarchy', '--no-show']

spec = importlib.util.spec_from_file_location('heu180h', 'heu180h.py')
heu_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(heu_mod)

from pyomo.environ import SolverFactory

def solve_model(deactivate=None, note=''):
    sched = heu_mod.MILP_Sheduler(DATA)
    m = sched.build_model(use_check_hierarchy=False)
    for name in (deactivate or []):
        cobj = getattr(m, name, None)
        if cobj is not None:
            cobj.deactivate()
    solver = SolverFactory('cplex')
    res = solver.solve(m, tee=False)
    status = str(res.solver.termination_condition)
    print(f'  [{note or "all active"}] -> {status}')
    return status, m

print('=== Baseline (all constraints) ===')
solve_model(note='baseline')

groups = ['c8', 'c9', 'c10', 'c11', 'c_hierarchy', 'c12', 'c12b', 'c12days',
          'c13', 'c13b', 'c14', 'c14b', 'c15', 'c23', 'c_overlap']

print('\n=== Individual deactivation ===')
for g in groups:
    solve_model(deactivate=[g], note=f'deactivate {g}')

print('\n=== Pairs: c12b + c13b ===')
solve_model(deactivate=['c12b', 'c13b'], note='deactivate c12b+c13b')

print('\n=== Pairs with c15 ===')
for g in ['c12b', 'c13b', 'c11', 'c9', 'c23']:
    solve_model(deactivate=['c15', g], note=f'deactivate c15+{g}')

print('\n=== Fix check: just c12b (C/D checks) ===')
solve_model(deactivate=['c12b'], note='deactivate c12b only')
solve_model(deactivate=['c13b'], note='deactivate c13b only')
