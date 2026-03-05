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


# ----------------------------
# EXECUTION
# ----------------------------

sc = Scheduler('data18h.json')
final_ac_fids, unassigned = sc.optimize()

# Calculate and Print Free Time
print("\n--- Aircraft Utilization Summary ---")
max_horizon = max([f['arr'] for f in sc.flights.values()])
for aid in sorted(sc.aircrafts):
    res = sc.get_timeline(aid, final_ac_fids[aid])
    if res:
        busy_time = sum((e['end'] - e['start']) for e in res['events'])
        # Free time is horizon minus the time actually spent doing things
        free_time = max_horizon - busy_time
        print(f"AC {aid}: Free Time = {free_time:.2f} mins")
    else:
        print(f"AC {aid}: Free Time = {max_horizon:.2f} mins (No flights assigned)")
print("------------------------------------\n")

# Generate Table
rows = []
for aid in sorted(sc.aircrafts):
    res = sc.get_timeline(aid, final_ac_fids[aid])
    if res:
        for e in res['events']:
            label = f"F{e['fid']}" if e['kind'] == 'FLIGHT' else e.get('check', 'FERRY')
            row = [aid, e['kind'], label, e['orig'], e['dest'], e['start'], 
                   e.get('dur', '-'), e.get('rem_a', '-'), e.get('rem_b', '-'), 
                   e.get('rem_c', '-'), e.get('rem_d', '-')]
            rows.append(row)

df = pd.DataFrame(rows, columns=['AID', 'Type', 'ID', 'From', 'To', 'Dep', 'Dur', 'Rem A', 'Rem B', 'Rem C(d)', 'Rem D(d)'])
print(df.to_string())
df.to_csv('final_schedule.csv', index=False)

# Plotting
colors = {"FLIGHT": "#3498db", "FERRY": "#9b59b6", "A": "#2ecc71", "B": "#f1c40f", "C": "#e67e22", "D": "#c0392b", "UN": "#e74c3c"}
fig, ax = plt.subplots(figsize=(15, 8))
for i, aid in enumerate(sorted(sc.aircrafts)):
    res = sc.get_timeline(aid, final_ac_fids[aid])
    if res:
        for e in res['events']:
            c = colors.get(e.get('check', e['kind']), colors['FLIGHT'])
            ax.broken_barh([(e['start'], e['end']-e['start'])], (i*10, 8), facecolors=c, edgecolor='white', linewidth=0.5)

un_y = len(sc.aircrafts) * 10
for fid in unassigned:
    fl = sc.flights[fid]
    ax.broken_barh([(fl['dep'], fl['dur'])], (un_y, 8), facecolors=colors["UN"], alpha=0.3, hatch='//')

legend_patches = [mpatches.Patch(color=color, label=label) for label, color in colors.items()]
ax.legend(handles=legend_patches, title="Event Types", loc='upper left', bbox_to_anchor=(1, 1))

ax.set_yticks([i*10+4 for i in range(len(sc.aircrafts)+1)])
ax.set_yticklabels([f"AC {a}" for a in sorted(sc.aircrafts)] + ["UNASSIGNED"])
plt.title(f"Optimized Fleet Schedule (Assigned: {len(sc.flights)-len(unassigned)})")
plt.tight_layout()
plt.show()