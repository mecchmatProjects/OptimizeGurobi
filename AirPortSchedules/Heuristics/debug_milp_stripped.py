"""
Standalone MILP feasibility check for ABCD_multi_check_test.json
Strips down to just the essential assignment + c13b constraints to find infeasibility.
Uses pyomo + cplex.
"""
import json
from pyomo.environ import *

data = json.load(open('inputsABCD/ABCD_multi_check_test.json'))

# Parse flights
flights = {}
for f in data['Flights']:
    fid = f[0]
    flights[fid] = {
        'dep': f[3], 'arr': f[4], 'origin': f[1], 'dest': f[2],
        'day_dep': int(f[3]//1440)+1, 'dur': f[4]-f[3]
    }

fids = sorted(flights.keys())
acs = list(range(5))
M = 1e7

# Check parameters (in minutes)
thresh = {'A': data['Maintenance_Thresholds']['A'],
          'B': data['Maintenance_Thresholds']['B']}

# Initial values already in minutes (loaded from JSON directly)
init_A = {j: data['Initial_Checks']['A'].get(str(j), 0) for j in acs}
init_B = {j: data['Initial_Checks']['B'].get(str(j), 0) for j in acs}
init = {'A': init_A, 'B': init_B}

cost = data['Cost_Matrix']  # 21x5

# Days
horizon = max(flights[fid]['day_dep'] for fid in fids)
days = list(range(1, horizon+1))

def _fbetween(d1, d2):
    return [fid for fid in fids if d1 < flights[fid]['day_dep'] <= d2]

print(f"Flights: {len(fids)}, ACs: {len(acs)}, Days: {len(days)} ({horizon})")
print(f"Thresholds: A={thresh['A']}min, B={thresh['B']}min")
print(f"Init A: {init_A}")
print(f"Init B: {init_B}")

def build_and_solve(include_c13=True, include_c13b=True, include_c8=True,
                    include_c15=True, include_c14b=True,
                    force_assignments=False):
    m = ConcreteModel()
    
    # Variables
    m.x = Var(fids, acs, domain=Binary)    # x[f,j]=1 if AC j flies flight f
    m.mega = Var(acs, days, ['A','B'], domain=Binary)  # check on day d for c in {A,B}
    m.y = Var(acs, days, ['A','B'], domain=Binary)     # check starts on day d
    m.z = Var(fids, acs, days, ['A','B'], domain=Binary)  # z[f,j,d,c]=1 if f triggers check c for j on day d
    
    # Each flight assigned to exactly one AC
    m.c_assign = ConstraintList()
    for fid in fids:
        m.c_assign.add(sum(m.x[fid, j] for j in acs) == 1)
    
    # c23: routing (no two flights same AC with origin!=prev.dest or overlap)
    m.c_routing = ConstraintList()
    sorted_fids = sorted(fids, key=lambda f: flights[f]['dep'])
    for idx, f1 in enumerate(sorted_fids):
        for f2 in sorted_fids[idx+1:]:
            # If both assigned to same AC and they overlap
            if flights[f1]['arr'] > flights[f2]['dep'] - 30:    # overlap or insufficient turn
                for j in acs:
                    m.c_routing.add(m.x[f1,j] + m.x[f2,j] <= 1)
            # If f1 and f2 are consecutive on same AC, must be compatible
    
    # c23b: position tracking (simplified - same AC, f2 after f1, dest(f1)!=origin(f2))
    m.c_pos = ConstraintList()
    for f1 in fids:
        for f2 in fids:
            if f1 == f2: continue
            # If f2 departs after f1 arrives with >=30 min turn, and they're on same AC
            # and dest(f1) != origin(f2) → can't be same AC
            if (flights[f2]['dep'] - flights[f1]['arr'] >= 30 and
                flights[f1]['dest'] != flights[f2]['origin']):
                # Check if there's any other flight between them on same AC
                # Simplified: just add if they could be consecutive
                pass  # Skip for now, focus on c13/c13b
    
    # Mega definition: mega[j,d,c] = 1 if AC j has check c active on day d
    # mega >= y (check starts on day d); also c14b: mega[d+1,c]=1 if mega[d,c]=1 AND K>1
    # For simplicity: y[j,d,c] forces mega[j,d,c]=1
    m.c_mega_y = ConstraintList()
    for j in acs:
        for d in days:
            for c in ['A','B']:
                m.c_mega_y.add(m.mega[j,d,c] >= m.y[j,d,c])
    
    # c14b: B-check spans 2 days (K=2)
    if include_c14b:
        m.c14b = ConstraintList()
        for j in acs:
            for di, d in enumerate(days):
                if di + 1 < len(days):
                    # If B-check starts on day d, day d+1 also mega
                    m.c14b.add(m.mega[j, days[di+1], 'B'] >= m.y[j, d, 'B'])
                    # Note: D-check also spans 2 days but not tracked here (only A/B in this model)
    
    # y[j,d,c] connections to z and x
    # z[f,j,d,c]=1 means flight f triggers check c for AC j on day d
    # FM flights = B->C flights
    fm_flights = [fid for fid in fids if flights[fid]['origin'] == 'B']
    print(f"FM flights (B->C): {fm_flights}")
    
    m.c_y_from_z = ConstraintList()
    for j in acs:
        for d in days:
            for c in ['A','B']:
                # y[j,d,c] = sum z[f,j,d,c] for FM flights f
                m.c_y_from_z.add(m.y[j,d,c] == sum(m.z[f,j,d,c] for f in fm_flights))
    
    # z can only be 1 if x[f,j]=1
    m.c_z_x = ConstraintList()
    for f in fm_flights:
        for j in acs:
            for d in days:
                for c in ['A','B']:
                    m.c_z_x.add(m.z[f,j,d,c] <= m.x[f,j])
    
    # z: check can only be triggered on the arrival day or later
    m.c_z_day = ConstraintList()
    for f in fm_flights:
        for j in acs:
            for d in days:
                if d < flights[f]['day_dep']:  # before arrival day
                    for c in ['A','B']:
                        m.c_z_day.add(m.z[f,j,d,c] == 0)
    
    # At most one check start per AC per day
    m.c14 = ConstraintList()
    for j in acs:
        for d in days:
            m.c14.add(sum(m.y[j,d,c] for c in ['A','B']) <= 1)
    
    # c13b: initial accumulated hours constraint
    if include_c13b:
        m.c13b = ConstraintList()
        for c in ['A','B']:
            hr_limit = thresh[c]
            for j in acs:
                prior_hrs = init[c][j]
                for ei in range(1, len(days)):
                    d_ = days[ei]
                    t_sum = sum(flights[fid]['dur'] * m.x[fid, j]
                                for fid in _fbetween(0, d_))
                    y_mid = sum(m.mega[j, days[r], c] for r in range(ei))
                    m.c13b.add(
                        t_sum <= (hr_limit - prior_hrs)
                                 + M * y_mid
                                 + M * m.mega[j, d_, c]
                    )
    
    # c13: inter-check flight hours constraint  
    if include_c13:
        m.c13 = ConstraintList()
        for c in ['A','B']:
            hr_limit = thresh[c]
            for j in acs:
                for si in range(len(days)-1):
                    for ei in range(si+2, len(days)):
                        d, d_ = days[si], days[ei]
                        t_sum = sum(flights[fid]['dur'] * m.x[fid, j]
                                    for fid in _fbetween(d, d_))
                        y_mid = sum(m.mega[j, days[r], c] for r in range(si+1, ei))
                        m.c13.add(t_sum <= hr_limit + M*y_mid + M*m.mega[j, d, c])
                        m.c13.add(t_sum <= hr_limit + M*y_mid + M*m.mega[j, d_, c])
    
    # c8(b): same-day block - if AC j flies a C->B escape flight on same day as FM arrival day,
    # then z[f,j,d_arr,c]=0 when that C->B dep is within the check window
    if include_c8:
        m.c8b = ConstraintList()
        for f in fm_flights:
            arr = flights[f]['arr']
            d_arr = flights[f]['day_dep']  # day of arrival
            for c in ['A','B']:
                dur_c = {'A': 360, 'B': 2880}[c]
                window_end = arr + dur_c
                # C->B flights on arrival day with dep in (arr, arr+dur]
                for f2 in fids:
                    if (flights[f2]['origin'] == 'C' and
                        flights[f2]['day_dep'] == d_arr and
                        arr < flights[f2]['dep'] <= window_end):
                        for j in acs:
                            # If both assigned to same AC, block same-day trigger
                            m.c8b.add(m.z[f,j,d_arr,c] + m.x[f2,j] <= 1)
        
        # c8(c): escape deferred block - any escape C->B on arrival day blocks deferred triggers
        m.c8c = ConstraintList()
        for f in fm_flights:
            arr = flights[f]['arr']
            d_arr = flights[f]['day_dep']
            for c in ['A','B']:
                escape_f2s = [f2 for f2 in fids
                              if flights[f2]['origin'] == 'C' and
                              flights[f2]['day_dep'] == d_arr and
                              flights[f2]['dep'] > arr]
                for f2 in escape_f2s:
                    for j in acs:
                        for d_def in days:
                            if d_def > d_arr:
                                m.c8c.add(m.z[f,j,d_def,c] + m.x[f2,j] <= 1)
    
    # c15: no flight during active check window
    if include_c15:
        m.c15 = ConstraintList()
        for f in fm_flights:
            arr = flights[f]['arr']
            d_arr = flights[f]['day_dep']
            for c in ['A','B']:
                dur_c = {'A': 360, 'B': 2880}[c]
                window_end = arr + dur_c
                # Block any flight departing from C within the check window
                blocked_flights = [f2 for f2 in fids
                                   if flights[f2]['origin'] == 'C' and
                                   arr <= flights[f2]['dep'] <= window_end]
                for f2 in blocked_flights:
                    for j in acs:
                        for d in days:
                            if d == d_arr:
                                m.c15.add(m.z[f,j,d,c] + m.x[f2,j] <= 1)
    
    # Force intended assignments if requested
    if force_assignments:
        m.c_forced = ConstraintList()
        intended = {fid: next(j for j,c in enumerate(row) if c == 1000.0)
                    for fid, row in zip(fids, cost)}
        for fid, j in intended.items():
            m.c_forced.add(m.x[fid,j] == 1)
    
    # Objective: minimize assignment cost
    m.obj = Objective(
        expr=sum(cost[i][j] * m.x[fids[i], j]
                 for i in range(len(fids)) for j in acs),
        sense=minimize
    )
    
    solver = SolverFactory('cplex')
    result = solver.solve(m, tee=False)
    status = str(result.solver.termination_condition)
    print(f"  Status: {status}")
    
    if status == 'optimal' or status == 'feasible':
        # Print assignment
        for fid in fids:
            for j in acs:
                if value(m.x[fid,j]) > 0.5:
                    print(f"    F{fid} -> AC{j}")
        # Print checks
        for j in acs:
            for d in days:
                for c in ['A','B']:
                    if value(m.mega[j,d,c]) > 0.5:
                        print(f"    mega[AC{j},day{d},{c}]=1")
    return status

print("\n=== Test 1: FORCED ASSIGNMENTS, WITH c13b only (no c13, no c8, no c15) ===")
s1 = build_and_solve(include_c13=False, include_c13b=True, include_c8=False,
                     include_c15=False, include_c14b=False, force_assignments=True)

print("\n=== Test 2: FORCED ASSIGNMENTS, WITH c13b + c8 (no c13, no c15) ===")
s2 = build_and_solve(include_c13=False, include_c13b=True, include_c8=True,
                     include_c15=False, include_c14b=False, force_assignments=True)

print("\n=== Test 3: FORCED ASSIGNMENTS, ALL constraints ===")
s3 = build_and_solve(include_c13=True, include_c13b=True, include_c8=True,
                     include_c15=True, include_c14b=True, force_assignments=True)

print("\n=== Test 4: FREE ASSIGNMENT, ALL constraints ===")
s4 = build_and_solve(include_c13=True, include_c13b=True, include_c8=True,
                     include_c15=True, include_c14b=True, force_assignments=False)
