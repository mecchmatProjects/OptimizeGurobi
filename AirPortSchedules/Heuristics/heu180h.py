import json
import math
import random
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import matplotlib.patches as mpatches
import pandas as pd

# Optional Pyomo imports (only needed for Optimizer)
try:
    from pyomo.environ import (ConcreteModel, Set, Var, Objective, ConstraintList,
                                Binary, minimize, value as pyo_value)
    from pyomo.opt import SolverFactory, TerminationCondition
    PYOMO_AVAILABLE = True
except ImportError:
    PYOMO_AVAILABLE = False

# ----------------------------
# CORE SCHEDULER ENGINE
# ----------------------------

class Scheduler:
    def __init__(self, data_path):
        with open(data_path, 'r') as f:
            self.data = json.load(f)
        
        self.flights = {f[0]: {'fid': f[0], 'orig': f[1], 'dest': f[2], 'dep': f[3], 'arr': f[4], 'dur': f[4]-f[3]} 
                        for f in self.data['Flights']}
        self.aircrafts = self.data['Aircrafts']
        self.init_pos = self.data['AIRCRAFT_INIT_POS']
        self.init_checks = self.data['Initial_Checks']
        self.thresholds = self.data['Maintenance_Thresholds']
        self.durations = self.data['Maintenance_Durations']
        self.station_cap = self.data['Station_Capacity']
        self.cost_matrix = self.data['Cost_Matrix']
        
        self.ferry_time = 60
        self.ferry_cost = 6000 # High cost helps the optimizer minimize these

    def get_timeline(self, aid, fids):
        curr_apt = self.init_pos[str(aid)]
        curr_time = 0.0
        a = float(self.init_checks['A'].get(str(aid), 0))
        b = float(self.init_checks['B'].get(str(aid), 0))
        c_init = float(self.init_checks.get('C_Days', {}).get(str(aid), 0))
        d_init = float(self.init_checks.get('D_Days', {}).get(str(aid), 0))
        
        events = []
        total_cost = 0

        for fid in fids:
            fl = self.flights[fid]
            
            # 1. Repositioning (Ferry) - Minimization logic happens via cost
            if curr_apt != fl['orig']:
                if curr_time + self.ferry_time > fl['dep']: return None
                events.append({'kind': 'FERRY', 'start': curr_time, 'end': curr_time + self.ferry_time, 
                               'orig': curr_apt, 'dest': fl['orig'], 'cost': self.ferry_cost})
                curr_time += self.ferry_time
                curr_apt = fl['orig']
                total_cost += self.ferry_cost
            
            # 2. Maintenance Logic
            days_now = curr_time / 1440.0
            needed = None
            if d_init + days_now > self.thresholds['D']: needed = 'D'
            elif c_init + days_now > self.thresholds['C']: needed = 'C'
            elif b + fl['dur'] > self.thresholds['B']: needed = 'B'
            elif a + fl['dur'] > self.thresholds['A']: needed = 'A'
            
            if needed:
                m_dur = self.durations[needed]
                if curr_time + m_dur > fl['dep']: return None
                if self.station_cap.get(fl['orig'], 0) == 0: return None
                
                events.append({'kind': 'MAINT', 'start': curr_time, 'end': curr_time + m_dur, 
                               'orig': fl['orig'], 'dest': fl['orig'], 'check': needed})
                curr_time += m_dur
                
                if needed == 'D': a=0; b=0; c_init = -(curr_time/1440.0); d_init = -(curr_time/1440.0)
                elif needed == 'C': a=0; b=0; c_init = -(curr_time/1440.0)
                elif needed == 'B': a=0; b=0
                elif needed == 'A': a=0

            # 3. Flight Execution
            if curr_time > fl['dep']: return None
            
            snap = {'rem_a': self.thresholds['A'] - a, 'rem_b': self.thresholds['B'] - b,
                    'rem_c': self.thresholds['C'] - (c_init + fl['dep']/1440.0),
                    'rem_d': self.thresholds['D'] - (d_init + fl['dep']/1440.0)}
            
            events.append({'kind': 'FLIGHT', 'fid': fid, 'start': fl['dep'], 'end': fl['arr'], 
                           'orig': fl['orig'], 'dest': fl['dest'], 'cost': self.cost_matrix[fid-1][aid], 
                           'dur': fl['dur'], **snap})
            
            curr_time, curr_apt = fl['arr'], fl['dest']
            a += fl['dur']; b += fl['dur']
            total_cost += self.cost_matrix[fid-1][aid]

        return {'events': events, 'cost': total_cost}

    def optimize(self):
        ac_fids = {aid: [] for aid in self.aircrafts}
        assigned = set()
        sorted_fids = sorted(self.flights.keys(), key=lambda x: self.flights[x]['dep'])
        
        for fid in sorted_fids:
            best_opt = None
            for aid in self.aircrafts:
                res = self.get_timeline(aid, ac_fids[aid] + [fid])
                if res and (best_opt is None or res['cost'] < best_opt[0]):
                    best_opt = (res['cost'], aid)
            if best_opt:
                ac_fids[best_opt[1]].append(fid)
                assigned.add(fid)

        for _ in range(5): 
            still_unassigned = [fid for fid in self.flights if fid not in assigned]
            for fid in still_unassigned:
                best_ins = None
                for aid in self.aircrafts:
                    for i in range(len(ac_fids[aid]) + 1):
                        trial = ac_fids[aid][:i] + [fid] + ac_fids[aid][i:]
                        res = self.get_timeline(aid, trial)
                        if res and (best_ins is None or res['cost'] < best_ins[2]):
                            best_ins = (aid, i, res['cost'])
                if best_ins:
                    aid, idx, _ = best_ins
                    ac_fids[aid].insert(idx, fid)
                    assigned.add(fid)

        return ac_fids, [fid for fid in self.flights if fid not in assigned]

# ----------------------------
# MILP OPTIMIZER ENGINE
# ----------------------------

class Optimizer:
    """MILP-based aircraft assignment with maintenance scheduling using Pyomo.

    Reads the same JSON format as Scheduler.  Each constraint group is
    implemented as a separate private method so they can be toggled or
    extended independently.

    JSON keys used
    --------------
    Flights           : [[fid, orig, dest, dep_min, arr_min], ...]
    Aircrafts         : [aid, ...]  (integer IDs)
    AIRCRAFT_INIT_POS : {str(aid): airport}
    Initial_Checks    : {check_key: {str(aid): elapsed_minutes}}
                        check_key ∈ {'A','B','C','D'}
    Maintenance_Thresholds : {'A': min, 'B': min, 'C': days, 'D': days}
    Maintenance_Durations  : {'A': min, 'B': min, 'C': min, 'D': min}
    Station_Capacity  : {airport: capacity}
    Cost_Matrix       : [[cost per (fid-1, aid_index)]]
    """

    CHECK_LIST = ['A', 'B', 'C', 'D']
    DAY_SHIFT  = 24 * 60   # minutes in one planning day
    MIN_TURN   = 30        # minimum ground turnaround (minutes)
    M_BIG      = 9_999_999

    # Hierarchy: performing check X also satisfies all lighter checks
    CHECK_HIERARCHY = {
        'A': ['A', 'B', 'C', 'D'],
        'B': ['B', 'C', 'D'],
        'C': ['C', 'D'],
        'D': ['D'],
    }

    def __init__(self, data_path, maintenance_airports=None):
        """Load data from *data_path* and prepare all MILP index sets.

        Parameters
        ----------
        data_path : str
            Path to the JSON data file.
        maintenance_airports : list[str] | None
            Airports where maintenance is allowed.  If None, derived from
            Station_Capacity (those with capacity > 0).
        """
        if not PYOMO_AVAILABLE:
            raise RuntimeError("Pyomo is not installed. Run: pip install pyomo")

        with open(data_path) as f:
            raw = json.load(f)

        # ── Flights ──────────────────────────────────────────────────────────
        self.flight_ids  = []
        self.flight_data = {}
        for fl in raw['Flights']:
            fid, orig, dest = fl[0], fl[1], fl[2]
            dep, arr = float(fl[3]), float(fl[4])
            self.flight_ids.append(fid)
            self.flight_data[fid] = {
                'origin':        orig,
                'destination':   dest,
                'departureTime': dep,
                'arrivalTime':   arr,
                'duration':      arr - dep,
                'day_departure': int(dep // self.DAY_SHIFT) + 1,
                'day_arrival':   int(arr // self.DAY_SHIFT) + 1,
            }

        # ── Aircrafts & initial positions ────────────────────────────────────
        self.aircraft_ids  = raw['Aircrafts']
        self.aircraft_init = {int(k): v for k, v in raw['AIRCRAFT_INIT_POS'].items()}

        # ── Airports ─────────────────────────────────────────────────────────
        all_airports = sorted(set(
            fd['origin']      for fd in self.flight_data.values()
        ) | set(
            fd['destination'] for fd in self.flight_data.values()
        ))
        self.airports = all_airports

        cap = raw['Station_Capacity']
        if maintenance_airports is not None:
            self.maint_airports = maintenance_airports
        else:
            self.maint_airports = sorted(a for a in all_airports if cap.get(a, 0) > 0)

        self.station_cap = {(a, d): cap.get(a, 0)
                            for a in all_airports for d in range(1, 10000)}

        # ── Thresholds & durations ───────────────────────────────────────────
        thresh = raw['Maintenance_Thresholds']  # A/B in minutes, C/D in days
        durs   = raw['Maintenance_Durations']   # all in minutes

        # Hours thresholds used in cumulative flight-hour constraints
        # A/B stored as minutes → convert; C/D stored as days → ×24
        self.check_hrs = {
            'A': thresh['A'] / 60.0,
            'B': thresh['B'] / 60.0,
            'C': thresh['C'] * 24.0,
            'D': thresh['D'] * 24.0,
        }
        # Day-interval thresholds for spacing constraints
        self.check_days = {
            'A': max(1, int(thresh['A'] / 60.0 / 24.0)),
            'B': max(1, int(thresh['B'] / 60.0 / 24.0)),
            'C': int(thresh['C']),
            'D': int(thresh['D']),
        }
        self.check_dur     = {k: float(durs[k]) for k in self.CHECK_LIST}  # minutes
        self.check_dur_days = {k: int(durs[k] // self.DAY_SHIFT) for k in self.CHECK_LIST}

        # ── Initial check state (elapsed flight minutes → hours) ─────────────
        init_ck = raw.get('Initial_Checks', {})
        self.init_check_hrs = {}
        for ck in self.CHECK_LIST:
            self.init_check_hrs[ck] = {
                aid: float(init_ck.get(ck, {}).get(str(aid), 0)) / 60.0
                for aid in self.aircraft_ids
            }

        # ── Cost matrix ───────────────────────────────────────────────────────
        # cost_matrix[fid-1][aid_index]  (outer index = flight, inner = aircraft)
        self.cost_matrix = raw['Cost_Matrix']
        self._aid_index  = {aid: idx for idx, aid in enumerate(self.aircraft_ids)}

        # ── Planning horizon (days) ───────────────────────────────────────────
        max_day = max(fd['day_arrival'] for fd in self.flight_data.values()) + 1
        max_day = max(8, max_day)
        self.days = list(range(1, max_day + 1))

        # Model and results (populated by build_model / solve)
        self.model   = None
        self.results = None

    # ------------------------------------------------------------------
    # Model construction
    # ------------------------------------------------------------------

    def build_model(self,
                    use_day_spacing=True,
                    use_existing_hrs=True,
                    use_check_hierarchy=True,
                    use_sanity=True,
                    use_overlap=True):
        """Construct the ConcreteModel.  Call before solve()."""
        m = ConcreteModel()
        self.model = m
        self._add_sets_and_variables(m)
        self._add_objective(m)
        self._add_c1_coverage(m)
        self._add_c23_turn(m)
        if use_overlap:
            self._add_overlap(m)
        self._add_c8_maint_blocks_flights(m)
        self._add_c9_maint_assignment(m)
        self._add_c10_capacity(m)
        self._add_c11_maint_link(m)
        self._add_hierarchy(m, use_check_hierarchy)
        self._add_c14_one_check_per_day(m)
        self._add_c14b_check_duration(m)
        if use_day_spacing:
            self._add_c12_day_spacing(m)
        if use_existing_hrs:
            self._add_c13b_existing_hrs(m)
        self._add_c13_hr_accumulation(m)
        self._add_c15_no_flight_during_maint(m)
        if use_sanity:
            self._add_sanity(m)
        return m

    def _add_sets_and_variables(self, m):
        """Define Pyomo Sets and Var declarations on model m."""
        m.F   = Set(initialize=self.flight_ids)
        m.P   = Set(initialize=sorted(self.aircraft_ids))
        m.A   = Set(initialize=self.airports)
        m.MA  = Set(initialize=self.maint_airports)
        m.D   = Set(initialize=sorted(self.days))
        m.C   = Set(initialize=self.CHECK_LIST)

        # x[i,j] = 1  iff flight i assigned to aircraft j
        m.x = Var(m.F, m.P, domain=Binary, initialize=0)
        # z[i,j,d,c] = 1  iff aircraft j does check c on day d triggered by flight i
        m.z = Var(m.F, m.P, m.D, m.C, domain=Binary, initialize=0)
        # y[j,d,c] = 1  iff aircraft j undergoes check c on day d
        m.y = Var(m.P, m.D, m.C, domain=Binary, initialize=0)
        # mega_check[j,d,c] = 1 if aircraft j has a check of type ≥c on day d (hierarchy)
        m.mega = Var(m.P, m.D, m.C, domain=Binary, initialize=0)

    def _add_objective(self, m):
        """Minimize flight assignment cost + premature maintenance penalty."""
        maint_cost = 100   # flat penalty per maintenance event (can be extended)
        m.obj = Objective(
            expr=(
                sum(self._flight_cost(i, j) * m.x[i, j]
                    for i in m.F for j in m.P)
                + sum(maint_cost * m.z[i, j, d, c]
                      for i in m.F for j in m.P for d in m.D for c in m.C)
            ),
            sense=minimize,
        )

    # ------------------------------------------------------------------
    # Helper index sets (computed lazily from flight_data)
    # ------------------------------------------------------------------
    def _f_arr_k(self, k):
        """Flights landing at airport k."""
        return [i for i, fd in self.flight_data.items() if fd['destination'] == k]

    def _f_dep_k(self, k):
        """Flights departing from airport k."""
        return [i for i, fd in self.flight_data.items() if fd['origin'] == k]

    def _f_arr_before(self, k, t, delta):
        """Flights landing at k with arrivalTime ≤ t − delta."""
        return [i for i in self._f_arr_k(k)
                if self.flight_data[i]['arrivalTime'] <= t - delta]

    def _f_dep_before(self, k, t):
        """Flights departing from k with departureTime < t."""
        return [i for i in self._f_dep_k(k)
                if self.flight_data[i]['departureTime'] < t]

    def _f_dep_window(self, k, t0, t1):
        """Flights departing from k with t0 < departureTime ≤ t1."""
        return [i for i in self._f_dep_k(k)
                if t0 < self.flight_data[i]['departureTime'] <= t1]

    def _f_between_days(self, d1, d2):
        """Flights whose day_departure is in (d1, d2]."""
        return [i for i, fd in self.flight_data.items()
                if d1 < fd['day_departure'] <= d2]

    def _f_on_day(self, d):
        """Flights departing on day d."""
        return [i for i, fd in self.flight_data.items() if fd['day_departure'] == d]

    def _flight_cost(self, fid, aid):
        return self.cost_matrix[fid - 1][self._aid_index[aid]]

    # ------------------------------------------------------------------
    # Constraint C1 – every flight covered by exactly one aircraft
    # ------------------------------------------------------------------

    def _add_c1_coverage(self, m):
        m.c1 = ConstraintList()
        for i in m.F:
            m.c1.add(sum(m.x[i, j] for j in m.P) == 1)

    # ------------------------------------------------------------------
    # Constraints C2–C3 – equipment-flow / turnaround feasibility
    # For every airport k, aircraft j, departing flight i from k:
    #   (flights arrived at k before dep[i] - turn) − (flights departed k
    #   before dep[i]) ≥ x[i,j]  (−1 if j is initially based at k)
    # ------------------------------------------------------------------

    def _add_c23_turn(self, m):
        m.c23 = ConstraintList()
        tau = self.MIN_TURN
        for j in m.P:
            init_apt = self.aircraft_init[j]
            for k in m.A:
                for i in self._f_dep_k(k):
                    t = self.flight_data[i]['departureTime']
                    lhs = (sum(m.x[i1, j] for i1 in self._f_arr_before(k, t, tau))
                           - sum(m.x[i1, j] for i1 in self._f_dep_before(k, t)))
                    rhs = m.x[i, j] if k != init_apt else m.x[i, j] - 1
                    m.c23.add(lhs >= rhs)

    # ------------------------------------------------------------------
    # Overlap constraint – two flights that overlap in time cannot share
    # the same aircraft (fills the gap left by C2–C3 for short windows)
    # ------------------------------------------------------------------

    def _add_overlap(self, m):
        m.c_overlap = ConstraintList()
        tau = self.MIN_TURN
        fids = list(m.F)
        for idx, i in enumerate(fids):
            fd_i = self.flight_data[i]
            for i1 in fids[idx + 1:]:
                fd_i1 = self.flight_data[i1]
                # They don't overlap if one departs after the other arrives + turn
                if fd_i['departureTime'] >= fd_i1['arrivalTime'] + tau:
                    continue
                if fd_i1['departureTime'] >= fd_i['arrivalTime'] + tau:
                    continue
                for j in m.P:
                    m.c_overlap.add(m.x[i, j] + m.x[i1, j] <= 1)

    # ------------------------------------------------------------------
    # Constraint C8 – maintenance check blocks subsequent same-day flights
    # z[i,j,d,c]=1 means aircraft j does check c on day d after flight i;
    # any flight i2 that departs the same day AFTER flight i is blocked.
    # ------------------------------------------------------------------

    def _add_c8_maint_blocks_flights(self, m):
        m.c8 = ConstraintList()
        for c in self.CHECK_LIST:
            for i in m.F:
                dep_i = self.flight_data[i]['arrivalTime']
                d_i   = self.flight_data[i]['day_arrival']
                for j in m.P:
                    for d in m.D:
                        # Same-day flights that depart after flight i arrives
                        for i2 in self.flight_ids:
                            fd2 = self.flight_data[i2]
                            if fd2['day_departure'] == d_i and fd2['departureTime'] > dep_i:
                                m.c8.add(m.z[i, j, d, c] + m.x[i2, j] <= 1)

    # ------------------------------------------------------------------
    # Constraint C9 – z[i,j,d,c] can only be 1 if x[i,j]=1
    # (maintenance triggered by a flight requires that flight is assigned)
    # ------------------------------------------------------------------

    def _add_c9_maint_assignment(self, m):
        m.c9 = ConstraintList()
        for c in self.CHECK_LIST:
            for i in m.F:
                for j in m.P:
                    for d in m.D:
                        m.c9.add(m.x[i, j] >= m.z[i, j, d, c])

    # ------------------------------------------------------------------
    # Constraint C10 – maintenance capacity per airport per day
    # ------------------------------------------------------------------

    def _add_c10_capacity(self, m):
        m.c10 = ConstraintList()
        cap = {a: self.station_cap[(a, 1)] for a in self.maint_airports}   # same every day
        F_m = {a: [i for i, fd in self.flight_data.items() if fd['destination'] == a]
               for a in self.maint_airports}
        for c in self.CHECK_LIST:
            for d in m.D:
                for a in m.MA:
                    flights_a = F_m.get(a, [])
                    if flights_a:
                        m.c10.add(
                            sum(m.z[i, j, d, c]
                                for i in flights_a for j in m.P) <= cap[a]
                        )

    # ------------------------------------------------------------------
    # Constraint C11 – link z to y:
    # y[j,d,c] = Σ_i  z[i,j,d,c]  (summed over flights landing at MA)
    # ------------------------------------------------------------------

    def _add_c11_maint_link(self, m):
        m.c11 = ConstraintList()
        ma_set = set(self.maint_airports)
        for c in self.CHECK_LIST:
            for d in m.D:
                for j in m.P:
                    m.c11.add(
                        sum(m.z[i, j, d, c]
                            for i in self.flight_ids
                            if self.flight_data[i]['destination'] in ma_set)
                        == m.y[j, d, c]
                    )

    # ------------------------------------------------------------------
    # Check hierarchy: mega[j,d,c] = 1 if a check at level ≥c occurs on d
    # ------------------------------------------------------------------

    def _add_hierarchy(self, m, use_hierarchy=True):
        m.c_hierarchy = ConstraintList()
        for j in m.P:
            for d in m.D:
                for c in self.CHECK_LIST:
                    if use_hierarchy:
                        covers = self.CHECK_HIERARCHY[c]
                        m.c_hierarchy.add(
                            m.mega[j, d, c] == sum(m.y[j, d, c2] for c2 in covers)
                        )
                    else:
                        m.c_hierarchy.add(m.mega[j, d, c] == m.y[j, d, c])

    # ------------------------------------------------------------------
    # Constraint C14 – at most one check type per aircraft per day
    # ------------------------------------------------------------------

    def _add_c14_one_check_per_day(self, m):
        m.c14 = ConstraintList()
        for j in m.P:
            for d in m.D:
                m.c14.add(sum(m.y[j, d, c] for c in self.CHECK_LIST) <= 1)

    # ------------------------------------------------------------------
    # Constraint C14b – multi-day checks occupy consecutive days
    # If aircraft j starts check c on day d and the check lasts K days then
    # mega[j,d+1..d+K-1,c] must all be 1.
    # ------------------------------------------------------------------

    def _add_c14b_check_duration(self, m):
        m.c14b = ConstraintList()
        days = sorted(self.days)
        for j in m.P:
            for c in self.CHECK_LIST:
                K = self.check_dur_days[c]
                if K <= 1:
                    continue
                for di, d in enumerate(days):
                    end = min(di + K, len(days))
                    if di == 0:
                        m.c14b.add(
                            sum(m.mega[j, days[d1], c] for d1 in range(1, end))
                            + self.M_BIG * (1 - m.mega[j, days[0], c]) >= end - 1
                        )
                        continue
                    if di >= end:
                        continue
                    m.c14b.add(
                        sum(m.mega[j, days[d1], c] for d1 in range(di + 1, end))
                        + self.M_BIG * m.mega[j, days[di - 1], c]
                        + self.M_BIG * (1 - m.mega[j, days[di], c]) >= end - di - 1
                    )

    # ------------------------------------------------------------------
    # Constraint C12 – day-spacing: every check-interval window must
    # contain at least one occurrence of mega[j,·,c]
    # ------------------------------------------------------------------

    def _add_c12_day_spacing(self, m):
        m.c12 = ConstraintList()
        days = sorted(self.days)
        n    = len(days)
        for c in self.CHECK_LIST:
            ival = self.check_days[c]
            for j in m.P:
                for start in range(n - ival + 1):
                    m.c12.add(
                        sum(m.mega[j, days[r], c] for r in range(start, start + ival)) >= 1
                    )

    # ------------------------------------------------------------------
    # Constraint C13 – cumulative flight-hour accumulation between checks
    # Between any two days d and d_ (within one check interval), total
    # flight minutes assigned to aircraft j must not exceed threshold
    # unless a check occurs in between (uses big-M relaxation).
    # ------------------------------------------------------------------

    def _add_c13_hr_accumulation(self, m):
        m.c13 = ConstraintList()
        days  = sorted(self.days)
        n     = len(days)
        for c in self.CHECK_LIST:
            hr_limit = self.check_hrs[c]   # hours
            for j in m.P:
                for si in range(n - 1):
                    for ei in range(si + 2, min(si + self.check_days[c], n)):
                        d,  d_ = days[si], days[ei]
                        t_sum  = sum(
                            self.flight_data[i]['duration'] * m.x[i, j]
                            for i in self._f_between_days(d, d_)
                        )
                        y_mid  = sum(m.mega[j, days[r], c]
                                     for r in range(si + 1, ei))
                        # Relax with big-M when either boundary day has a check
                        m.c13.add(
                            t_sum <= hr_limit * 60
                                     + self.M_BIG * y_mid
                                     + self.M_BIG * m.mega[j, d, c]
                        )
                        m.c13.add(
                            t_sum <= hr_limit * 60
                                     + self.M_BIG * y_mid
                                     + self.M_BIG * m.mega[j, d_, c]
                        )

    # ------------------------------------------------------------------
    # Constraint C13b – existing flight hours at start of horizon
    # The aircraft's accumulated hours since last check must be respected.
    # ------------------------------------------------------------------

    def _add_c13b_existing_hrs(self, m):
        m.c13b = ConstraintList()
        days = sorted(self.days)
        n    = len(days)
        for c in self.CHECK_LIST:
            hr_limit = self.check_hrs[c]
            for j in m.P:
                prior_hrs = self.init_check_hrs[c].get(j, 0.0)
                for ei in range(1, min(n - 1, self.check_days[c])):
                    d_   = days[ei]
                    t_sum = sum(
                        self.flight_data[i]['duration'] * m.x[i, j]
                        for i in self._f_between_days(0, d_)
                    )
                    y_mid = sum(m.mega[j, days[r], c] for r in range(ei - 1))
                    m.c13b.add(
                        t_sum <= (hr_limit - prior_hrs) * 60
                                 + self.M_BIG * y_mid
                                 + self.M_BIG * m.mega[j, d_, c]
                    )

    # ------------------------------------------------------------------
    # Constraint C15 – no flight during an active maintenance check
    # After flight i triggers check c for aircraft j on day d, flights
    # departing from the same airport within the check duration are blocked.
    # Also applies at the start of the horizon (initial position).
    # ------------------------------------------------------------------

    def _add_c15_no_flight_during_maint(self, m):
        m.c15 = ConstraintList()
        for c in self.CHECK_LIST:
            dur = self.check_dur[c]               # check duration in minutes
            # a) Triggered by an arriving flight
            for i in self.flight_ids:
                fd   = self.flight_data[i]
                apt  = fd['destination']
                d    = fd['day_arrival']
                t_arr = fd['arrivalTime']
                if apt not in self.maint_airports:
                    continue
                for j in m.P:
                    for i2 in self._f_dep_window(apt, t_arr, t_arr + dur):
                        m.c15.add(m.z[i, j, d, c] + m.x[i2, j] <= 1)
            # b) Initial position at time zero
            days = sorted(self.days)
            d0   = days[0]
            seen_apts = set()
            for j, apt in self.aircraft_init.items():
                if apt not in self.maint_airports or apt in seen_apts:
                    continue
                seen_apts.add(apt)
                for j2 in m.P:
                    for i2 in self._f_dep_window(apt, 0, dur):
                        m.c15.add(m.mega[j2, d0, c] + m.x[i2, j2] <= 1)
        # Multi-day checks additionally block departing flights on later days
        m.c15b = ConstraintList()
        for c in self.CHECK_LIST:
            if self.check_dur_days[c] <= 1:
                continue
            for i in self.flight_ids:
                fd  = self.flight_data[i]
                apt = fd['origin']
                d   = fd['day_departure']
                if apt not in self.maint_airports:
                    continue
                for j in m.P:
                    if d > sorted(self.days)[0]:
                        m.c15b.add(m.y[j, d, c] + m.x[i, j] <= 1)

    # ------------------------------------------------------------------
    # Sanity: z[i,j,d,c]=0 when day d is after arrival day + check duration
    # ------------------------------------------------------------------

    def _add_sanity(self, m):
        m.c_sanity = ConstraintList()
        for c in self.CHECK_LIST:
            for i in m.F:
                arr_day = self.flight_data[i]['day_arrival']
                for j in m.P:
                    for d in m.D:
                        if d < self.flight_data[i]['day_arrival']:
                            m.c_sanity.add(m.z[i, j, d, c] == 0)
                        if d > arr_day + self.check_dur_days[c]:
                            m.c_sanity.add(m.z[i, j, d, c] == 0)

    # ------------------------------------------------------------------
    # Solve
    # ------------------------------------------------------------------

    def solve(self, solver_name='cplex', tee=False, out_path=None):
        """Invoke the solver on the built model.

        Parameters
        ----------
        solver_name : str
            Pyomo solver name ('cplex', 'cbc', 'glpk', …).
        tee : bool
            Stream solver log to stdout.
        out_path : str | None
            If given, write the text report to this file.

        Returns
        -------
        dict with keys: status, n_vars, n_cons, gap, cpu, obj
        """
        if self.model is None:
            raise RuntimeError("Call build_model() first.")

        solver = SolverFactory(solver_name)
        self.results = solver.solve(self.model, tee=tee)

        m   = self.model
        res = self.results
        tc  = res.solver.termination_condition

        n_var  = len(list(m.component_data_objects(ctype=Var)))
        n_con  = len(list(m.component_data_objects(ctype=Constraint)))
        lo     = getattr(res.problem, 'lower_bound', None)
        hi     = getattr(res.problem, 'upper_bound', None)
        gap    = abs(hi - lo) / abs(lo) if lo and hi and lo != 0 else None
        cpu    = getattr(res.solver, 'time', None)
        obj_v  = pyo_value(m.obj) if tc == TerminationCondition.optimal else None

        summary = dict(status=str(tc), n_vars=n_var, n_cons=n_con,
                       gap=gap, cpu=cpu, obj=obj_v)
        self.print_report(out_path=out_path, summary=summary)
        return summary

    # ------------------------------------------------------------------
    # Text report
    # ------------------------------------------------------------------

    def print_report(self, out_path=None, summary=None):
        """Print assignment + maintenance schedule; optionally write to file."""
        m = self.model
        lines = []
        _p = lines.append

        _p("\n=== MILP Aircraft Assignment Report ===")
        if summary:
            g = f"{summary['gap']*100:.4f}%" if summary.get('gap') is not None else '-'
            t = f"{summary['cpu']:.2f}s"     if summary.get('cpu') is not None else '-'
            _p(f"  Status : {summary['status']}")
            _p(f"  Vars   : {summary['n_vars']}   Constraints: {summary['n_cons']}")
            _p(f"  Gap    : {g}   CPU: {t}")
            _p(f"  Obj    : {summary['obj']}")

        _p("\n--- Assignment ---")
        for i in m.F:
            for j in m.P:
                if pyo_value(m.x[i, j]) > 0.5:
                    _p(f"  Flight {i:4d}  → Aircraft {j}")

        _p("\n--- Maintenance ---")
        for j in m.P:
            for d in m.D:
                for c in self.CHECK_LIST:
                    if pyo_value(m.y[j, d, c]) > 0.5:
                        _p(f"  Aircraft {j}  day {d:3d}  check {c}")

        _p(f"\nTotal cost: {pyo_value(m.obj):.2f}")
        text = "\n".join(lines)
        print(text)
        if out_path:
            with open(out_path, 'w') as f:
                f.write(text)

    # ------------------------------------------------------------------
    # Extract schedule events for downstream use (Gantt / CSV)
    # ------------------------------------------------------------------

    def get_events(self):
        """Return list of event dicts {aircraft, type, label, start, end, day}.

        Compatible with the Gantt plotter used for the heuristic output.
        """
        m = self.model
        events = []
        for j in m.P:
            for i in m.F:
                if pyo_value(m.x[i, j]) > 0.5:
                    fd = self.flight_data[i]
                    events.append({
                        'aircraft': j,
                        'type':     'FLIGHT',
                        'label':    f'F{i}',
                        'start':    fd['departureTime'],
                        'end':      fd['arrivalTime'],
                        'day':      fd['day_departure'],
                        'check':    None,
                    })
            for d in m.D:
                for c in self.CHECK_LIST:
                    if pyo_value(m.y[j, d, c]) > 0.5:
                        # Find the trigger flight to get start time
                        t_start = (d - 1) * self.DAY_SHIFT
                        for i in m.F:
                            if pyo_value(m.z[i, j, d, c]) > 0.5:
                                t_start = self.flight_data[i]['arrivalTime']
                                break
                        events.append({
                            'aircraft': j,
                            'type':     'MAINT',
                            'label':    f'M{c}',
                            'start':    t_start,
                            'end':      t_start + self.check_dur[c],
                            'day':      d,
                            'check':    c,
                        })
        events.sort(key=lambda e: (e['aircraft'], e['start']))
        return events

    # ------------------------------------------------------------------
    # Gantt chart for MILP results
    # ------------------------------------------------------------------

    def plot_gantt(self, save_path=None, show=True):
        """Render a Gantt chart from the solved model.

        Parameters
        ----------
        save_path : str | None  Path to save PNG; if None chart is not saved.
        show      : bool        Call plt.show() when True.
        """
        events    = self.get_events()
        aid_list  = sorted(self.aircraft_ids)
        _plot_gantt(events, aid_list, unassigned_ids=[], save_path=save_path,
                    show=show, title='MILP Aircraft Schedule')


# ----------------------------
# SHARED GANTT UTILITY
# ----------------------------

# Colour palette shared by heuristic and MILP outputs
_GANTT_COLORS = {
    'FLIGHT': '#3498db',
    'FERRY':  '#9b59b6',
    'A':      '#2ecc71',
    'B':      '#f1c40f',
    'C':      '#e67e22',
    'D':      '#c0392b',
    'UN':     '#e74c3c',
}


def _plot_gantt(events, aid_list, unassigned_flights=None, unassigned_ids=None,
                flights_dict=None, save_path=None, show=True, title='Fleet Schedule'):
    """Generic Gantt plotter used by both Scheduler and Optimizer.

    Parameters
    ----------
    events           : list of dicts with keys aircraft, type, start, end, check
    aid_list         : ordered list of aircraft IDs (rows)
    unassigned_flights: dict {fid: flight_info} for heuristic unassigned row
    unassigned_ids   : list of unassigned fids (MILP has none usually)
    flights_dict     : full flights dict from Scheduler (for unassigned row)
    save_path        : file path to save PNG
    show             : call plt.show()
    title            : chart title
    """
    colors = _GANTT_COLORS
    fig, ax = plt.subplots(figsize=(18, max(6, len(aid_list) * 0.6 + 2)))

    for i, aid in enumerate(aid_list):
        for e in (ev for ev in events if ev['aircraft'] == aid):
            c_key = e.get('check') or e['type']
            color = colors.get(c_key, colors['FLIGHT'])
            dur   = e['end'] - e['start']
            ax.broken_barh([(e['start'], dur)], (i * 10, 8),
                           facecolors=color, edgecolor='white', linewidth=0.5)
            if dur > 30:
                ax.text(e['start'] + dur / 2, i * 10 + 4, e['label'],
                        ha='center', va='center', color='white', fontsize=7, clip_on=True)

    # Unassigned row (heuristic only)
    if unassigned_ids and flights_dict:
        un_y = len(aid_list) * 10
        for fid in unassigned_ids:
            fl = flights_dict[fid]
            ax.broken_barh([(fl['dep'], fl['dur'])], (un_y, 8),
                           facecolors=colors['UN'], alpha=0.3, hatch='//')

    n_rows = len(aid_list) + (1 if unassigned_ids else 0)
    ax.set_yticks([i * 10 + 4 for i in range(n_rows)])
    labels = [f'AC {a}' for a in aid_list]
    if unassigned_ids:
        labels.append('UNASSIGNED')
    ax.set_yticklabels(labels)
    ax.set_xlabel('Time (minutes)')

    legend_patches = [mpatches.Patch(color=c, label=k) for k, c in colors.items()]
    ax.legend(handles=legend_patches, title='Event Types',
              loc='upper left', bbox_to_anchor=(1, 1))
    plt.title(title)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Gantt saved to {save_path}")
    if show:
        plt.show()
    else:
        plt.close()


# ----------------------------
# UNIFIED MAIN
# ----------------------------

def run_heuristic(data_path='data18h.json', csv_path='final_schedule.csv',
                  gantt_path=None, show_gantt=True):
    """Run the greedy+insertion heuristic and display results."""
    sc = Scheduler(data_path)
    final_ac_fids, unassigned = sc.optimize()

    # Utilization summary
    max_horizon = max(f['arr'] for f in sc.flights.values())
    print("\n--- Aircraft Utilization Summary ---")
    for aid in sorted(sc.aircrafts):
        res = sc.get_timeline(aid, final_ac_fids[aid])
        if res:
            busy = sum(e['end'] - e['start'] for e in res['events'])
            print(f"  AC {aid:3d}: Free Time = {max_horizon - busy:.0f} min")
        else:
            print(f"  AC {aid:3d}: Free Time = {max_horizon:.0f} min  (no flights)")
    print("------------------------------------")

    # CSV export
    rows = []
    for aid in sorted(sc.aircrafts):
        res = sc.get_timeline(aid, final_ac_fids[aid])
        if res:
            for e in res['events']:
                label = f"F{e['fid']}" if e['kind'] == 'FLIGHT' else e.get('check', 'FERRY')
                rows.append([aid, e['kind'], label, e['orig'], e['dest'], e['start'],
                             e.get('dur', '-'), e.get('rem_a', '-'), e.get('rem_b', '-'),
                             e.get('rem_c', '-'), e.get('rem_d', '-')])
    df = pd.DataFrame(rows, columns=['AID','Type','ID','From','To','Dep','Dur',
                                     'Rem A','Rem B','Rem C(d)','Rem D(d)'])
    print(df.to_string())
    df.to_csv(csv_path, index=False)
    print(f"\nSchedule saved to {csv_path}")

    # Gantt
    events = []
    for aid in sorted(sc.aircrafts):
        res = sc.get_timeline(aid, final_ac_fids[aid])
        if res:
            for e in res['events']:
                events.append({
                    'aircraft': aid,
                    'type':     e['kind'],
                    'label':    f"F{e['fid']}" if e['kind'] == 'FLIGHT' else e.get('check', 'FERRY'),
                    'start':    e['start'],
                    'end':      e['end'],
                    'check':    e.get('check'),
                })

    _plot_gantt(events, sorted(sc.aircrafts),
                unassigned_ids=unassigned, flights_dict=sc.flights,
                save_path=gantt_path, show=show_gantt,
                title=f"Heuristic Schedule (assigned {len(sc.flights)-len(unassigned)}/{len(sc.flights)})")

    return sc, final_ac_fids, unassigned


def run_milp(data_path='data18h.json', solver='cplex', tee=False,
             out_txt=None, gantt_path=None, show_gantt=True,
             use_day_spacing=True, use_existing_hrs=True,
             use_check_hierarchy=True, use_sanity=True, use_overlap=True):
    """Build and solve the MILP model, then display results."""
    opt = Optimizer(data_path)
    opt.build_model(use_day_spacing=use_day_spacing,
                    use_existing_hrs=use_existing_hrs,
                    use_check_hierarchy=use_check_hierarchy,
                    use_sanity=use_sanity,
                    use_overlap=use_overlap)
    summary = opt.solve(solver_name=solver, tee=tee, out_path=out_txt)
    opt.plot_gantt(save_path=gantt_path, show=show_gantt)
    return opt, summary


def main():
    """Entry point – edit MODE and parameters below or call run_* directly."""
    import argparse
    parser = argparse.ArgumentParser(description='Aircraft Schedule Optimizer')
    parser.add_argument('--mode',   default='heuristic',
                        choices=['heuristic', 'milp'],
                        help='Optimization approach (default: heuristic)')
    parser.add_argument('--data',   default='data18h.json',
                        help='Path to JSON data file')
    parser.add_argument('--solver', default='cplex',
                        help='Pyomo solver name for MILP mode (default: cplex)')
    parser.add_argument('--tee',    action='store_true',
                        help='Stream solver log (MILP mode only)')
    parser.add_argument('--out',    default=None,
                        help='Output file path (txt for MILP, csv for heuristic)')
    parser.add_argument('--gantt',  default=None,
                        help='Save Gantt chart to this PNG path')
    parser.add_argument('--no-show', dest='show', action='store_false',
                        help='Do not display the Gantt chart interactively')
    parser.set_defaults(show=True)
    args = parser.parse_args()

    if args.mode == 'heuristic':
        run_heuristic(data_path=args.data,
                      csv_path=args.out or 'final_schedule.csv',
                      gantt_path=args.gantt,
                      show_gantt=args.show)
    else:
        run_milp(data_path=args.data,
                 solver=args.solver,
                 tee=args.tee,
                 out_txt=args.out,
                 gantt_path=args.gantt,
                 show_gantt=args.show)


if __name__ == '__main__':
    main()
