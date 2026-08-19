"""
Verify that the intended integral routing satisfies c23 for ABCD_multi_check_test.
Hand-trace the routing assignment and check each c23 constraint.
"""
from heu180h import MILP_Sheduler
import pyomo.environ as pyo

sched = MILP_Sheduler('inputsABCD/ABCD_multi_check_test.json')
sched.build_model()

# The intended integral routing:
# AC0 (init B): F1->F2->F8->F9->F12->F13->F14->F15->F18->F19->F20(optional)
# AC1 (init B): F3->F5->F6->F7
# AC2 (init B): F21->F23->F25->F26
# AC3 (init B): F22->F24->F27->F28
# AC4 (init C): F4->F10->F11->F16->F17->F20(optional)
# Flights: 1-28 (IDs after renumbering)
# F20 = B->C dep=28800 (was F21 originally)
# F21 = B->C dep=180  (AC2 trigger, was F22)
# F22 = B->C dep=240  (AC3 trigger, was F23)
# F23 = C->B dep=1860 (AC2 post-C-check, was F24)
# F24 = C->B dep=3360 (AC3 post-D-check, was F25)
# F25 = B->C dep=13500 (AC2 2nd C-check trigger, was F26)
# F26 = C->B dep=15200 (AC2 post-2nd-C-check, was F27)
# F27 = B->C dep=18720 (AC3 2nd D-check trigger, was F28)
# F28 = C->B dep=21860 (AC3 post-2nd-D-check, was F29)

intended_x = {
    # (flight_id, aircraft_id): 1 if assigned
    (1, 0): 1,   # AC0 flies F1 (B->C)
    (2, 0): 1,   # AC0 flies F2 (C->B)
    (3, 1): 1,   # AC1 flies F3 (B->C)
    (4, 4): 1,   # AC4 flies F4 (C->B)
    (5, 1): 1,   # AC1 flies F5 (C->B post-B-check)
    (6, 1): 1,   # AC1 flies F6 (B->C A-check trigger)
    (7, 1): 1,   # AC1 flies F7 (C->B post-A-check)
    (8, 0): 1,   # AC0 flies F8 (B->C accum)
    (9, 0): 1,   # AC0 flies F9 (C->B)
    (10, 4): 1,  # AC4 flies F10 (B->C)
    (11, 4): 1,  # AC4 flies F11 (C->B)
    (12, 0): 1,  # AC0 flies F12 (B->C)
    (13, 0): 1,  # AC0 flies F13 (C->B)
    (14, 0): 1,  # AC0 flies F14 (B->C)
    (15, 0): 1,  # AC0 flies F15 (C->B)
    (16, 4): 1,  # AC4 flies F16 (B->C)
    (17, 4): 1,  # AC4 flies F17 (C->B)
    (18, 0): 1,  # AC0 flies F18 (B->C 2nd A-check trigger)
    (19, 0): 1,  # AC0 flies F19 (C->B post-2nd-A-check)
    (20, 0): 1,  # AC0 flies F20 (B->C late op)
    (21, 2): 1,  # AC2 flies F21 (B->C 1st C-check trigger)
    (22, 3): 1,  # AC3 flies F22 (B->C 1st D-check trigger)
    (23, 2): 1,  # AC2 flies F23 (C->B post-1st-C-check)
    (24, 3): 1,  # AC3 flies F24 (C->B post-1st-D-check)
    (25, 2): 1,  # AC2 flies F25 (B->C 2nd C-check trigger)
    (26, 2): 1,  # AC2 flies F26 (C->B post-2nd-C-check)
    (27, 3): 1,  # AC3 flies F27 (B->C 2nd D-check trigger)
    (28, 3): 1,  # AC3 flies F28 (C->B post-2nd-D-check)
}

def get_x(i, j):
    return intended_x.get((i, j), 0)

m = sched.model
tau = sched.MIN_TURN

print("=== c23 check for intended integer assignment ===")
n_viol = 0
for j in m.P:
    init_apt = sched.aircraft_init[j]
    for k in m.A:
        for i in sched._f_dep_k(k):
            t = sched.flight_data[i]['departureTime']
            lhs_val = (sum(get_x(i1, j) for i1 in sched._f_arr_before(k, t, tau))
                       - sum(get_x(i1, j) for i1 in sched._f_dep_before(k, t)))
            x_ij = get_x(i, j)
            rhs_val = x_ij if k != init_apt else x_ij - 1
            if lhs_val < rhs_val - 1e-4:
                n_viol += 1
                fd = sched.flight_data[i]
                print(f"  VIOL: AC{j}, apt={k}, F{i}({fd['origin']}->{fd['destination']} dep={t:.0f}): "
                      f"lhs={lhs_val:.0f} < rhs={rhs_val:.0f}  (x={x_ij})")

if n_viol == 0:
    print("  All c23 constraints SATISFIED for intended routing!")
else:
    print(f"\n  Total violations: {n_viol}")

print("\n=== Per-aircraft sequence ===")
for j in range(5):
    flights_j = [(i, sched.flight_data[i]) for i in sorted(m.F)
                 if get_x(i, j) == 1]
    init = sched.aircraft_init[j]
    print(f"\nAC{j} (init={init}):")
    prev_arr = None
    prev_apt = init
    for i, fd in flights_j:
        dep = fd['departureTime']
        arr = fd['arrivalTime']
        orig = fd['origin']
        dest = fd['destination']
        turn = f"  turn={dep - prev_arr:.0f}min" if prev_arr is not None else ""
        pos_ok = "OK" if prev_apt == orig else f"MISMATCH(was at {prev_apt})"
        print(f"  F{i:>2}: {orig}->{dest} dep={dep:>7.0f} arr={arr:>7.0f}  [{pos_ok}{turn}]")
        prev_arr = arr
        prev_apt = dest
