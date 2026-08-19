import json

data = json.load(open('inputsABCD/ABCD_multi_check_test.json'))
flights = {f[0]: {
    'dep': f[3], 'arr': f[4], 'origin': f[1], 'dest': f[2],
    'day_dep': int(f[3]//1440)+1, 'day_arr': int(f[4]//1440)+1,
    'dur': f[4]-f[3]
} for f in data['Flights']}

thresh_A = data['Maintenance_Thresholds']['A']
thresh_B = data['Maintenance_Thresholds']['B']
ac_names = ['AC0','AC1','AC2','AC3','AC4']

# Print cost matrix to see intended assignments
print("=== Cost Matrix ===")
for i, row in enumerate(data['Cost_Matrix']):
    fid = data['Flights'][i][0]
    best = min(range(len(row)), key=lambda j: row[j])
    print(f"  F{fid} -> {ac_names[best]} (cost={row[best]})")

# Get intended assignment per AC
print()
for ac_idx, ac_name in enumerate(ac_names):
    ac_fids = [data['Flights'][i][0] for i in range(len(data['Flights'])) 
               if data['Cost_Matrix'][i][ac_idx] == 1000.0]
    print(f"\n=== {ac_name} flights ===")
    ac_ftimes = sorted(ac_fids, key=lambda fid: flights[fid]['dep'])
    
    # Check route continuity
    pos = data['AIRCRAFT_INIT_POS'][str(ac_idx)]
    print(f"  Init pos: {pos}")
    for fid in ac_ftimes:
        f = flights[fid]
        ok = "OK" if pos == f['origin'] else f"BAD(at {pos}, need {f['origin']})"
        print(f"  F{fid}: {f['origin']}->{f['dest']} dep={f['dep']} arr={f['arr']} day={f['day_dep']} {ok}")
        pos = f['dest']

# Check c13b for AC0
print("\n=== c13b for AC0 (A, prior=1000) ===")
prior_A = data['Initial_Checks']['A']['0']
hr_limit_A = thresh_A  # in minutes
AC0_fids = [data['Flights'][i][0] for i in range(len(data['Flights'])) 
            if data['Cost_Matrix'][i][0] == 1000.0]
days = list(range(1, 22))
n = len(days)
for ei in range(1, n):
    d_ = days[ei]
    t_sum = sum(flights[fid]['dur'] for fid in AC0_fids if 0 < flights[fid]['day_dep'] <= d_)
    rem = hr_limit_A - prior_A
    excess = t_sum - rem
    note = " *** FORCES CHECK" if excess > 0 else ""
    print(f"  c13b(d_={d_}): t_sum={t_sum}, rem={rem}, excess={excess}{note}")

# Check c13 pairs for AC0 after reset (day 1 check)
# Both checks: day 1 and day 4 (expected)
# mega[0,1,A]=1 (1st check), mega[0,4,A]=1 (2nd check)
print("\n=== c13 for AC0 (all pairs, checking relaxation by mega[0,1,A] and mega[0,4,A]) ===")
check_days_AC0 = {1, 4}  # expected check days for AC0
violations = []
for si in range(n-1):
    for ei in range(si+2, n):
        d, d_ = days[si], days[ei]
        t_sum = sum(flights[fid]['dur'] for fid in AC0_fids if d < flights[fid]['day_dep'] <= d_)
        if t_sum > hr_limit_A:
            interior = [dd for dd in range(d+1, d_) if dd in check_days_AC0]
            c1_ok = d in check_days_AC0 or bool(interior)
            c2_ok = d_ in check_days_AC0 or bool(interior)
            ok = c1_ok and c2_ok
            status = "OK" if ok else "INFEASIBLE"
            if not ok:
                violations.append((d, d_, t_sum, c1_ok, c2_ok))
            print(f"  c13({d},{d_}): t_sum={t_sum}>1200. c1_relax(mega@{d})={c1_ok}, c2_relax(mega@{d_})={c2_ok} => {status}")

print(f"\nc13 INFEASIBLE pairs for AC0: {len(violations)}")

# Check c13b for AC1 (A, prior=800)
print("\n=== c13b for AC1 (A, prior=800) ===")
prior_A1 = data['Initial_Checks']['A']['1']
AC1_fids = [data['Flights'][i][0] for i in range(len(data['Flights'])) 
            if data['Cost_Matrix'][i][1] == 1000.0]
print(f"  AC1 flights: {AC1_fids}")
for ei in range(1, n):
    d_ = days[ei]
    t_sum = sum(flights[fid]['dur'] for fid in AC1_fids if 0 < flights[fid]['day_dep'] <= d_)
    rem = hr_limit_A - prior_A1
    excess = t_sum - rem
    note = " *** FORCES A-CHECK" if excess > 0 else ""
    print(f"  c13b(d_={d_}): t_sum={t_sum}, rem={rem}, excess={excess}{note}")
    if excess > 400:
        break

# Check c13b for AC1 B-check
print("\n=== c13b for AC1 (B, prior=3400) ===")
prior_B1 = data['Initial_Checks']['B']['1']
hr_limit_B = thresh_B
for ei in range(1, n):
    d_ = days[ei]
    t_sum = sum(flights[fid]['dur'] for fid in AC1_fids if 0 < flights[fid]['day_dep'] <= d_)
    rem = hr_limit_B - prior_B1
    excess = t_sum - rem
    note = " *** FORCES B-CHECK" if excess > 0 else ""
    print(f"  c13b(d_={d_}): t_sum={t_sum}, rem={rem}={hr_limit_B}-{prior_B1}, excess={excess}{note}")
    if d_ > 6:
        break

print("\n=== C8 check for AC0 F13 (B->C arr=4700, dur=360) ===")
F13_arr = 4700
F13_window_end = F13_arr + 360
print(f"  Check window: [{F13_arr}, {F13_window_end}]")
for fid, f in flights.items():
    if f['origin'] == 'C' and f['day_dep'] == 4 and F13_arr < f['dep'] <= F13_window_end:
        print(f"  BLOCKED by F{fid}: dep={f['dep']} (in window)")
print(f"  F15 dep={flights[15]['dep']}: {'IN window (blocked)' if F13_arr < flights[15]['dep'] <= F13_window_end else 'OUTSIDE window (ok)'}")
