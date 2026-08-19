"""Debug c23 routing infeasibility for ABCD_multi_check_test."""
from heu180h import MILP_Sheduler
import pyomo.environ as pyo

sched = MILP_Sheduler('inputsABCD/ABCD_multi_check_test.json')
sched.build_model()
m = sched.model
solver = pyo.SolverFactory('cplex')

# Relax all binary variables
for v in m.component_objects(pyo.Var, active=True):
    for idx in v:
        if v[idx].domain == pyo.Binary:
            v[idx].domain = pyo.NonNegativeReals
            v[idx].setub(1.0)

# --- Solve without c23 to get the "ideal" assignment ---
m.c23.deactivate()
solver.solve(m, tee=False)

print("=== LP solution without c23 (routing) ===")
print(f"{'Flight':>6}  {'Route':>8}  {'Dep':>7}  {'Arr':>7}  {'AC0':>6}  {'AC1':>6}  {'AC2':>6}  {'AC3':>6}  {'AC4':>6}")
for i in sorted(m.F):
    fd = sched.flight_data[i]
    vals = [pyo.value(m.x[i, j]) for j in range(5)]
    vals_fmt = [f"{v:.2f}" if v is not None else "  N/A" for v in vals]
    route = f"{fd['origin']}->{fd['destination']}"
    print(f"  F{i:>2}  {route:>8}  {fd['departureTime']:>7.0f}  {fd['arrivalTime']:>7.0f}  "
          f"{'  '.join(vals_fmt)}")

print()
print("=== Per-aircraft flight sequences (x > 0.5) ===")
for j in range(5):
    flights_j = [(i, sched.flight_data[i]) for i in sorted(m.F)
                 if (pyo.value(m.x[i, j]) or 0) > 0.5]
    print(f"\nAC{j} (init={sched.aircraft_init[j]}):")
    for i, fd in flights_j:
        print(f"  F{i:>2}: {fd['origin']}->{fd['destination']} dep={fd['departureTime']:>7.0f} arr={fd['arrivalTime']:>7.0f}")

print()
print("=== Checking c23 violations for the LP solution ===")
tau = sched.MIN_TURN
n_viol = 0
for j in m.P:
    init_apt = sched.aircraft_init[j]
    for k in m.A:
        for i in sched._f_dep_k(k):
            t = sched.flight_data[i]['departureTime']
            lhs_val = (sum(pyo.value(m.x[i1, j]) or 0 for i1 in sched._f_arr_before(k, t, tau))
                       - sum(pyo.value(m.x[i1, j]) or 0 for i1 in sched._f_dep_before(k, t)))
            x_ij = pyo.value(m.x[i, j]) or 0
            rhs_val = x_ij if k != init_apt else x_ij - 1
            if lhs_val < rhs_val - 1e-4:
                n_viol += 1
                fd = sched.flight_data[i]
                print(f"  VIOL c23: AC{j}, apt={k}, F{i}({fd['origin']}->{fd['destination']} dep={t:.0f}): "
                      f"lhs={lhs_val:.3f} < rhs={rhs_val:.3f}  (x={x_ij:.3f})")
                # Show what arrivals/departures are counted
                arr_before = list(sched._f_arr_before(k, t, tau))
                dep_before = list(sched._f_dep_before(k, t))
                for i2 in arr_before:
                    v = pyo.value(m.x[i2, j]) or 0
                    fd2 = sched.flight_data[i2]
                    if v > 0.01:
                        print(f"    arr_before F{i2}({fd2['origin']}->{fd2['destination']} arr={fd2['arrivalTime']:.0f}): x={v:.3f}")
                for i2 in dep_before:
                    v = pyo.value(m.x[i2, j]) or 0
                    fd2 = sched.flight_data[i2]
                    if v > 0.01:
                        print(f"    dep_before F{i2}({fd2['origin']}->{fd2['destination']} dep={fd2['departureTime']:.0f}): x={v:.3f}")

if n_viol == 0:
    print("  No violations found (solution satisfies c23).")
