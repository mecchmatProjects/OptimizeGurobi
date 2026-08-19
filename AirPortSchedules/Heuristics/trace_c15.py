"""
Detailed trace of C15 constraints generated for ABCD_all_checks_test.json.
This will show exactly which flight+aircraft pairs are blocked for each check type.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logging
logging.disable(logging.CRITICAL)

from heu180h import MILP_Sheduler

DATA = 'inpytABCD/ABCD_all_checks_test.json'

sch = MILP_Sheduler(DATA)

print("=== C15 analysis for ABCD_all_checks_test.json ===\n")
print(f"FM flights: {sch.maint_flight_ids}")
print(f"Aircraft: {sch.aircraft_ids}")
print()

# For each trigger flight and check type, what flights does C15 block?
for c in ['A', 'B', 'C', 'D']:
    dur = sch.check_dur[c]
    print(f"=== Check {c} (dur={dur} min = {dur/1440:.1f} days) ===")
    for i in sch.maint_flight_ids:
        fd = sch.flight_data[i]
        apt = fd['destination']
        t_arr = fd['arrivalTime']
        d_i = fd['day_arrival']
        blocked_flights = sch._f_dep_window(apt, t_arr, t_arr + dur)
        # Filter to only same-day (the condition check: d != d_i is skipped)
        blocked_same_day = [i2 for i2 in blocked_flights 
                           if sch.flight_data[i2]['day_departure'] == d_i]
        blocked_other_days = [i2 for i2 in blocked_flights 
                             if sch.flight_data[i2]['day_departure'] != d_i]
        if blocked_other_days:
            print(f"  Trigger f{i} (arr={t_arr:.0f}, day={d_i}): "
                  f"blocks same-day C-dep flights {blocked_same_day}, "
                  f"blocks OTHER-day via mega: {blocked_other_days[:8]}{'...' if len(blocked_other_days)>8 else ''}")
        else:
            print(f"  Trigger f{i} (arr={t_arr:.0f}, day={d_i}): blocks {blocked_same_day}")
    
    # Initial position constraint (b): ALL aircraft at C (all start at C)
    # Since seen_apts prevents duplicates, it runs once for airport C.
    # Blocks: for all j, flights departing C within [0, dur] minutes.
    init_blocked = sch._f_dep_window('C', 0, dur)
    print(f"  C15(b) initial: blocks all j from flying C-departures [{init_blocked[:10]}{'...' if len(init_blocked)>10 else ''}]")
    print(f"  => constraint: mega[j, day1, {c}] + x[i2, j] <= 1 for each i2 in those flights")
    print()

print("=== KEY ANALYSIS: Can 4 aircraft each fly their round trips on day 1? ===")
print()
print("Flight pairs (C→B then B→C, all day 1):")
pairs = [(1,2), (3,4), (5,6), (7,8)]
for f_out, f_in in pairs:
    fd_out = sch.flight_data[f_out]
    fd_in  = sch.flight_data[f_in]
    print(f"  f{f_out}(C→B dep={fd_out['departureTime']:.0f} arr={fd_out['arrivalTime']:.0f}) + "
          f"f{f_in}(B→C dep={fd_in['departureTime']:.0f} arr={fd_in['arrivalTime']:.0f})")

print()
print("C15(b) for D-check (dur=60480): blocks mega[j,day1,D]+x[i,j]<=1 for ALL C→B flights in [0,60480]")
all_c_dep = sch._f_dep_window('C', 0, 60480)
print(f"  C-departing flights in [0, 60480min]: {all_c_dep}")
print(f"  => AC3 needs mega[3,day1,D]=1 (C12b), so AC3 blocked from ALL these flights")
print(f"  => But AC3 is supposed to fly f7 (C→B) as its outbound! CONFLICT!")
print()

# Check if f7 is in the blocked set for D-check
f7_dep = sch.flight_data[7]['departureTime']
print(f"  f7 departure time: {f7_dep}")
print(f"  Is f7 blocked by C15(b) for D-check? {7 in all_c_dep}")
print()

print("=== THE REAL CONFLICT ===")
print("AC3 needs mega[3,day1,D]=1 (to trigger D-check on day1)")
print("C15(b): mega[3,day1,D] + x[f7,3] <= 1  (f7 is a C-departure within 42-day window)")
print("=> AC3 cannot fly f7 (the C→B outbound it needs to reach B and then fly f8 back)")
print("=> AC3 can NEVER get a trigger flight to C on day1 (can't leave C first)")
print()
print("C15 part (a): If some OTHER aircraft flies f7 and f8, creating a trigger for AC3...")
print("Wait: AC3 doesn't need to fly f7 first. AC3 STARTS at C.")
print("But to fly f8 (B→C), AC3 must first be at B — requires flying f7 (C→B) first.")
print("C15(b) blocks: mega[3,day1,D]=1 AND x[f7,3]=1 simultaneously.")
print("=> AC3 can't fly f7, so can't be at B to fly f8, so can't trigger D-check on day1. INFEASIBLE!")
