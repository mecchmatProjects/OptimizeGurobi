"""Diagnostic: test which combination of C23+maintenance constraints causes infeasibility."""
import json, time
from pyomo.environ import *

DATA = 'Inputs/DataCplex_density=1_p=10_h=7_test_0.json'
with open(DATA) as f:
    d = json.load(f)

DAY_SHIFT = 24*60
MIN_TURN = 30
M_BIG = 9999999
CHECK_LIST = ['A','B','C','D']

flights = d['Flights']
aircraft = d['Aircrafts']
init_pos = {int(k): v for k,v in d['AIRCRAFT_INIT_POS'].items()}
thresh = d['Maintenance_Thresholds']
durs_raw = d['Maintenance_Durations']

flight_ids = [fl[0] for fl in flights]
fd = {}
for fl in flights:
    fid, orig, dest, dep, arr = fl[0], fl[1], fl[2], float(fl[3]), float(fl[4])
    fd[fid] = {
        'origin': orig, 'destination': dest,
        'departureTime': dep, 'arrivalTime': arr,
        'day_dep': int(dep // DAY_SHIFT) + 1,
        'day_arr': int(arr // DAY_SHIFT) + 1,
        'dur': arr - dep,
    }

airports = sorted(set(v['origin'] for v in fd.values()) | set(v['destination'] for v in fd.values()))
# Use heu180h's day computation: max_day = max(arr)+1, at least 8
max_day = max(v['day_arr'] for v in fd.values()) + 1
max_day = max(8, max_day)
days = list(range(1, max_day + 1))
maint_apts_set = {a for a, c in d['Station_Capacity'].items() if c > 0}
maint_apts = sorted(maint_apts_set)
n = len(days)

print(f"Days: {days}  n={n}")

check_hrs = {'A': thresh['A']/60.0, 'B': thresh['B']/60.0, 'C': thresh['C']*24.0, 'D': thresh['D']*24.0}
check_days_map = {'A': None, 'B': None, 'C': int(thresh['C']), 'D': int(thresh['D'])}
check_dur_days = {k: int(float(durs_raw[k])//DAY_SHIFT) for k in CHECK_LIST}
CHECK_HIERARCHY = {'A': ['A','B','C','D'], 'B': ['B','C','D'], 'C': ['C','D'], 'D': ['D']}


def make_base():
    m = ConcreteModel()
    m.F  = Set(initialize=flight_ids)
    m.P  = Set(initialize=sorted(aircraft))
    m.A  = Set(initialize=airports)
    m.D  = Set(initialize=days)
    m.C  = Set(initialize=CHECK_LIST)
    m.MA = Set(initialize=maint_apts)
    m.x    = Var(m.F, m.P, domain=Binary)
    m.z    = Var(m.F, m.P, m.D, m.C, domain=Binary)
    m.y    = Var(m.P, m.D, m.C, domain=Binary)
    m.mega = Var(m.P, m.D, m.C, domain=Binary)
    m.obj  = Objective(expr=sum(m.x[i,j] for i in m.F for j in m.P), sense=maximize)
    m.c1   = ConstraintList()
    for i in m.F:
        m.c1.add(sum(m.x[i,j] for j in m.P) == 1)
    return m


def add_c23(m):
    def f_dep_k(k): return [i for i,v in fd.items() if v['origin']==k]
    def f_arr_before(k,t): return [i for i,v in fd.items() if v['destination']==k and v['arrivalTime']<=t-MIN_TURN]
    def f_dep_before(k,t): return [i for i,v in fd.items() if v['origin']==k and v['departureTime']<t]
    m.c23 = ConstraintList()
    for j in m.P:
        ia = init_pos[j]
        for k in airports:
            for i in f_dep_k(k):
                t   = fd[i]['departureTime']
                ab  = f_arr_before(k, t)
                db  = f_dep_before(k, t)
                lhs = (sum(m.x[i1,j] for i1 in ab) if ab else 0) \
                    - (sum(m.x[i1,j] for i1 in db) if db else 0)
                rhs = m.x[i,j] if k != ia else m.x[i,j] - 1
                m.c23.add(lhs >= rhs)


def add_c9(m):
    m.c9 = ConstraintList()
    for c in CHECK_LIST:
        for i in m.F:
            for j in m.P:
                for day in days:
                    m.c9.add(m.x[i,j] >= m.z[i,j,day,c])


def add_c11(m):
    """y[j,d,c] = sum_i z[i,j,d,c]  for i landing at MA."""
    m.c11 = ConstraintList()
    for c in CHECK_LIST:
        for day in days:
            for j in m.P:
                m.c11.add(
                    sum(m.z[i,j,day,c] for i in flight_ids
                        if fd[i]['destination'] in maint_apts_set)
                    == m.y[j, day, c]
                )


def add_hier(m):
    m.c_h = ConstraintList()
    for j in m.P:
        for day in days:
            for c in CHECK_LIST:
                m.c_h.add(m.mega[j,day,c] == sum(m.y[j,day,c2] for c2 in CHECK_HIERARCHY[c]))


def add_mega_eq_y(m):
    """Simplified: mega = y (no hierarchy)."""
    m.c_h = ConstraintList()
    for j in m.P:
        for day in days:
            for c in CHECK_LIST:
                m.c_h.add(m.mega[j,day,c] == m.y[j,day,c])


def add_c13(m):
    def f_between(d1,d2): return [i for i,v in fd.items() if d1 < v['day_dep'] <= d2]
    m.c13 = ConstraintList()
    for c in CHECK_LIST:
        hl  = check_hrs[c]
        cd  = check_days_map[c] if check_days_map[c] is not None else n
        for j in m.P:
            for si in range(n-1):
                for ei in range(si+2, min(si+cd, n)):
                    d1, d2 = days[si], days[ei]
                    t_sum  = sum(fd[i]['dur']*m.x[i,j] for i in f_between(d1,d2))
                    y_mid  = sum(m.mega[j,days[r],c] for r in range(si+1, ei))
                    m.c13.add(t_sum <= hl*60 + M_BIG*y_mid + M_BIG*m.mega[j,d1,c])
                    m.c13.add(t_sum <= hl*60 + M_BIG*y_mid + M_BIG*m.mega[j,d2,c])


def add_c13b(m):
    init_ck = d.get('Initial_Checks', {})
    init_hrs = {}
    for ck in CHECK_LIST:
        if ck in ('C','D'):
            dk = ck + '_Days'
            if dk in init_ck:
                init_hrs[ck] = {aid: float(init_ck[dk].get(str(aid), 0))*24.0 for aid in aircraft}
            else:
                init_hrs[ck] = {aid: float(init_ck.get(ck,{}).get(str(aid),0))/60.0 for aid in aircraft}
        else:
            init_hrs[ck] = {aid: float(init_ck.get(ck,{}).get(str(aid),0))/60.0 for aid in aircraft}

    def f_before(d2): return [i for i,v in fd.items() if 0 < v['day_dep'] <= d2]
    m.c13b = ConstraintList()
    for c in CHECK_LIST:
        hl = check_hrs[c]
        cd = check_days_map[c] if check_days_map[c] is not None else n
        for j in m.P:
            prior = init_hrs[c].get(j, 0.0)
            for ei in range(1, min(n-1, cd)):
                d2    = days[ei]
                t_sum = sum(fd[i]['dur']*m.x[i,j] for i in f_before(d2))
                y_mid = sum(m.mega[j,days[r],c] for r in range(ei-1))
                m.c13b.add(t_sum <= (hl-prior)*60 + M_BIG*y_mid + M_BIG*m.mega[j,d2,c])


def add_sanity(m):
    m.c_sanity = ConstraintList()
    for c in CHECK_LIST:
        for i in flight_ids:
            arr_day = fd[i]['day_arr']
            for j in sorted(aircraft):
                for day in days:
                    if day < arr_day:
                        m.c_sanity.add(m.z[i,j,day,c] == 0)
                    if day > arr_day + check_dur_days[c]:
                        m.c_sanity.add(m.z[i,j,day,c] == 0)


def solve_test(label, add_fns, tl=60):
    print(f"\n--- {label} ---")
    m = make_base()
    for fn in add_fns:
        fn(m)
    solver = SolverFactory('cplex')
    t0 = time.time()
    result = solver.solve(m, timelimit=tl)
    tc = result.solver.termination_condition
    print(f"  Status: {tc}  ({time.time()-t0:.1f}s)")
    return tc


def add_c8(m):
    """C8: maintenance blocks subsequent same-day flights from same airport."""
    later_flights = {}
    for i2, v2 in fd.items():
        key = (v2['origin'], v2['day_dep'], v2['departureTime'])
        later_flights.setdefault(key, []).append(i2)
    m.c8 = ConstraintList()
    for c in CHECK_LIST:
        for i in flight_ids:
            v = fd[i]
            arr_i  = v['arrivalTime']
            d_i    = v['day_arr']
            dest_i = v['destination']
            blocking = [i2 for i2, v2 in fd.items()
                        if v2['origin'] == dest_i and v2['day_dep'] == d_i
                        and v2['departureTime'] > arr_i]
            if d_i in days:
                for j in sorted(aircraft):
                    for i2 in blocking:
                        m.c8.add(m.z[i,j,d_i,c] + m.x[i2,j] <= 1)


def add_c10(m):
    cap = {a: d['Station_Capacity'][a] for a in maint_apts}
    F_m = {a: [i for i,v in fd.items() if v['destination']==a] for a in maint_apts}
    m.c10 = ConstraintList()
    for day in days:
        for a in maint_apts:
            fa = F_m.get(a,[])
            if fa:
                m.c10.add(sum(m.z[i,j,day,c] for c in CHECK_LIST for i in fa for j in sorted(aircraft)) <= cap[a])


def add_c14(m):
    m.c14 = ConstraintList()
    for j in m.P:
        for day in days:
            m.c14.add(sum(m.y[j,day,c] for c in CHECK_LIST) <= 1)


def add_c14b(m):
    m.c14b = ConstraintList()
    for j in m.P:
        for c in CHECK_LIST:
            K = check_dur_days[c]
            if K <= 1:
                continue
            for di, day in enumerate(days):
                end = min(di+K, n)
                if di == 0:
                    m.c14b.add(sum(m.mega[j,days[d1],c] for d1 in range(1,end))
                               + M_BIG*(1-m.mega[j,days[0],c]) >= end-1)
                    continue
                if di >= end:
                    continue
                m.c14b.add(sum(m.mega[j,days[d1],c] for d1 in range(di+1,end))
                           + M_BIG*m.mega[j,days[di-1],c]
                           + M_BIG*(1-m.mega[j,days[di],c]) >= end-di-1)


def add_c12(m):
    m.c12 = ConstraintList()
    for c in CHECK_LIST:
        ival = check_days_map[c]
        if ival is None or ival >= n:
            continue
        for j in m.P:
            for start in range(n - ival + 1):
                m.c12.add(sum(m.mega[j,days[r],c] for r in range(start, start+ival)) >= 1)


def add_c15_full(m):
    """Full C15 including initial positions and C15b multi-day blocking."""
    m.c15 = ConstraintList()
    for c in CHECK_LIST:
        dur = float(durs_raw[c])
        # a) Arriving-flight triggered checks
        for i in flight_ids:
            v   = fd[i]
            apt = v['destination']
            day = v['day_arr']
            t_a = v['arrivalTime']
            if apt not in maint_apts_set:
                continue
            for j in sorted(aircraft):
                blocked = [i2 for i2,v2 in fd.items()
                           if v2['origin']==apt and t_a < v2['departureTime'] <= t_a+dur]
                for i2 in blocked:
                    m.c15.add(m.z[i,j,day,c] + m.x[i2,j] <= 1)
        # b) Initial position at time zero
        d0 = days[0]
        seen_apts = set()
        for j_init, apt in init_pos.items():
            if apt not in maint_apts_set or apt in seen_apts:
                continue
            seen_apts.add(apt)
            blocked_init = [i2 for i2,v2 in fd.items()
                            if v2['origin']==apt and 0 < v2['departureTime'] <= dur]
            for j2 in sorted(aircraft):
                for i2 in blocked_init:
                    m.c15.add(m.mega[j2,d0,c] + m.x[i2,j2] <= 1)

    # C15b: multi-day checks block departing flights on subsequent days
    m.c15b = ConstraintList()
    for c in CHECK_LIST:
        if check_dur_days[c] <= 1:
            continue
        for i in flight_ids:
            v   = fd[i]
            apt = v['origin']
            day = v['day_dep']
            if apt not in maint_apts_set:
                continue
            for j in sorted(aircraft):
                if day > days[0]:
                    m.c15b.add(m.y[j,day,c] + m.x[i,j] <= 1)


def add_overlap(m):
    tau = MIN_TURN
    fids = list(flight_ids)
    m.c_overlap = ConstraintList()
    for idx, i in enumerate(fids):
        for i1 in fids[idx+1:]:
            if fd[i]['departureTime'] >= fd[i1]['arrivalTime'] + tau:
                continue
            if fd[i1]['departureTime'] >= fd[i]['arrivalTime'] + tau:
                continue
            for j in sorted(aircraft):
                m.c_overlap.add(m.x[i,j] + m.x[i1,j] <= 1)


BASE = [add_c23, add_c9, add_c11, add_hier, add_c13, add_c13b]
ALL_MAINT_FULL = BASE + [add_c8, add_c10, add_c14, add_c14b, add_c12, add_c15_full]

# Count constraints
m = make_base()
for fn in ALL_MAINT_FULL + [add_sanity]:
    fn(m)
total_cons = sum(1 for c in m.component_objects(Constraint, active=True) for _ in c)
total_vars = sum(1 for v in m.component_objects(Var, active=True) for _ in v)
print(f"Diag model (full C15): {total_vars} vars, {total_cons} constraints")
print("heu180h --no-overlap reports: 77860 vars, 205040 constraints\n")

# Isolate: is it C15a (triggered by flights), C15b (multi-day), or C15-init (day0 blocks)?
def add_c15a_only(m):
    """Only the flight-triggered part of C15 (no init, no C15b)."""
    m.c15 = ConstraintList()
    for c in CHECK_LIST:
        dur = float(durs_raw[c])
        for i in flight_ids:
            v   = fd[i]
            apt = v['destination']
            day = v['day_arr']
            t_a = v['arrivalTime']
            if apt not in maint_apts_set:
                continue
            for j in sorted(aircraft):
                blocked = [i2 for i2,v2 in fd.items()
                           if v2['origin']==apt and t_a < v2['departureTime'] <= t_a+dur]
                for i2 in blocked:
                    m.c15.add(m.z[i,j,day,c] + m.x[i2,j] <= 1)


def add_c15_init_only(m):
    """Only the initial-position part of C15."""
    m.c15_init = ConstraintList()
    for c in CHECK_LIST:
        dur = float(durs_raw[c])
        d0 = days[0]
        seen_apts = set()
        for j_init, apt in init_pos.items():
            if apt not in maint_apts_set or apt in seen_apts:
                continue
            seen_apts.add(apt)
            blocked_init = [i2 for i2,v2 in fd.items()
                            if v2['origin']==apt and 0 < v2['departureTime'] <= dur]
            for j2 in sorted(aircraft):
                for i2 in blocked_init:
                    m.c15_init.add(m.mega[j2,d0,c] + m.x[i2,j2] <= 1)


def add_c15b_only(m):
    """Only C15b multi-day blocking."""
    m.c15b = ConstraintList()
    for c in CHECK_LIST:
        if check_dur_days[c] <= 1:
            continue
        for i in flight_ids:
            v   = fd[i]
            apt = v['origin']
            day = v['day_dep']
            if apt not in maint_apts_set:
                continue
            for j in sorted(aircraft):
                if day > days[0]:
                    m.c15b.add(m.y[j,day,c] + m.x[i,j] <= 1)


solve_test("BASE + sanity (no C15)",              BASE + [add_sanity], tl=60)
solve_test("BASE + C15a only + sanity",           BASE + [add_c15a_only, add_sanity], tl=60)
solve_test("BASE + C15_init only + sanity",       BASE + [add_c15_init_only, add_sanity], tl=60)
solve_test("BASE + C15b only + sanity",           BASE + [add_c15b_only, add_sanity], tl=60)
solve_test("BASE + C15a + C15_init + sanity",     BASE + [add_c15a_only, add_c15_init_only, add_sanity], tl=60)
solve_test("BASE + C15a + C15b + sanity",         BASE + [add_c15a_only, add_c15b_only, add_sanity], tl=60)
solve_test("BASE + ALL C15 + sanity",             BASE + [add_c15_full, add_sanity], tl=10)
