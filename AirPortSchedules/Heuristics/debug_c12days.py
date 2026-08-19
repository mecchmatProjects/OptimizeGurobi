"""
Analyze c12days constraints to find which one conflicts with c9/c11.
Key: c12days forces z[i,j,d,c] == z[i,j,days_i,c] for d in (days_i, days_i+ival).
c9: x[i,j] >= z[i,j,d,c] for all d.
c11: y[j,d,c] == sum(z[i,j,d,c]).
c14: sum(y[j,d,c]) <= 1 per day.
"""
import json

data = json.load(open('inputsABCD/ABCD_multi_check_test.json'))
flights = {f[0]: {
    'dep': f[3], 'arr': f[4], 'origin': f[1], 'dest': f[2],
    'day_dep': int(f[3]//1440)+1, 'day_arr': int(f[4]//1440)+1,
    'dur': f[4]-f[3]
} for f in data['Flights']}

CHECK_LIST = ['C', 'D']
check_dur_days = {'A': 0, 'B': 2, 'C': 1, 'D': 2}  # int(dur_min // 1440)

DAY_SHIFT = 1440
# FM flights = B->C flights (arriving at C)
fm_flights = [fid for fid, f in flights.items() if f['dest'] == 'C']
print(f"FM flights (dest=C, i.e. B->C): {fm_flights}")

# Intended assignments (cost=1000)
intended = {data['Flights'][i][0]: next(j for j,c in enumerate(data['Cost_Matrix'][i]) if c==1000.0)
            for i in range(len(data['Flights']))}

horizon = max(f['day_dep'] for f in flights.values())
days = list(range(1, horizon+1))
print(f"Days: 1..{horizon}")

print("\n=== c12days analysis: which constraints are forced ===")
for c in CHECK_LIST:
    ival = check_dur_days[c]
    if ival <= 0:
        continue
    print(f"\n-- {c}-check (ival={ival} days) --")
    for fid in fm_flights:
        days_i = flights[fid]['day_arr']
        int_ac = intended[fid]
        print(f"  FM flight F{fid} (AC{int_ac}, B->C, day_arr={days_i}):")
        # Range that forces z[fid,j,d,c] == z[fid,j,days_i,c]
        forced_range = list(range(days_i+1, min(days_i+ival, horizon+1)))
        zero_range_after = list(range(days_i+ival, horizon+1))
        if forced_range:
            print(f"    z[{fid},j,d,{c}] == z[{fid},j,{days_i},{c}] forces: d in {forced_range}")
            # Each of these days must have y[j,d,c]=1 if z[fid,j,days_i,c]=1
            # and c9 requires x[fid,j]=1 for that
            for d_forced in forced_range:
                # What other FM flights have z on this day d_forced?
                other_fm_on_d = [f2 for f2 in fm_flights
                                 if f2 != fid and flights[f2]['day_arr'] <= d_forced
                                 and not (d_forced >= flights[f2]['day_arr'] + ival)]
                # c12days for those flights at d_forced:
                # z[f2,j,d_forced,c] == z[f2,j,days_i_f2,c] if d_forced in (days_i_f2, days_i_f2+ival)
                # else z[f2,j,d_forced,c] == 0 if d_forced >= days_i_f2+ival
                applicable = []
                for f2 in fm_flights:
                    if f2 == fid: continue
                    di2 = flights[f2]['day_arr']
                    if d_forced == di2:  # same day as arrival
                        applicable.append(f"F{f2}(same-day,ac{intended[f2]})")
                    elif di2 < d_forced < di2 + ival:   # in forced range
                        applicable.append(f"F{f2}(forced-same-as-day{di2},ac{intended[f2]})")
                    elif d_forced >= di2 + ival:  # must be 0
                        pass  # not applicable
                print(f"    Day {d_forced}: z triggers from other FM flights: {applicable or 'none'}")

print("\n=== Checking c14 conflicts: two checks on same day for same AC ===")
# For each aircraft, check if c12days forces two separate check starts on the same day
for j in range(5):
    print(f"\n  AC{j}:")
    for d in days:
        # Which c-checks AND d-checks can fire on day d for AC j?
        c_check_sources = []
        d_check_sources = []
        for fid in fm_flights:
            if intended[fid] != j: continue  # only assigned flights
            di = flights[fid]['day_arr']
            # C-check: z[fid,j,d,C] can be 1 only at d=di
            if d == di:
                c_check_sources.append(f"F{fid}(C-check,day{di})")
            # D-check at d=di or d=di+1 (via c12days forced range)
            if d == di or d == di+1:
                d_check_sources.append(f"F{fid}(D-check,day{d})")
        if c_check_sources and d_check_sources:
            print(f"    Day {d}: C-check possible from {c_check_sources}, D-check possible from {d_check_sources}")
            print(f"    -> c14 allows only 1 check! CONFLICT if both needed!")

print("\n=== Show AC2 C-checks and AC3 D-checks on same day ===")
print("  AC2 FM flights (C-check):")
for fid in fm_flights:
    if intended[fid] == 2:
        print(f"    F{fid}: day_arr={flights[fid]['day_arr']}")
print("  AC3 FM flights (D-check):")
for fid in fm_flights:  
    if intended[fid] == 3:
        print(f"    F{fid}: day_arr={flights[fid]['day_arr']}")
