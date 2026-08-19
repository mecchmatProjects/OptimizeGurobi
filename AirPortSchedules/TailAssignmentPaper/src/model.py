import json
import math
import os
import random
import sys
import logging
from venv import logger

import pandas as pd

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    PLOTTING_AVAILABLE = True
except ImportError:
    plt = None
    mpatches = None
    PLOTTING_AVAILABLE = False
# Force UTF-8 output on Windows (avoids UnicodeEncodeError for box-drawing chars)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Optional Pyomo imports (only needed for Optimizer)
try:
    from pyomo.environ import (ConcreteModel, Set, Var, Objective, Constraint,
                                ConstraintList, Binary, minimize, value as pyo_value)
    from pyomo.contrib.solver.common.util import NoFeasibleSolutionError
    from pyomo.opt import SolverFactory, TerminationCondition
    PYOMO_AVAILABLE = True
except ImportError:
    PYOMO_AVAILABLE = False

# ----------------------------
# CORE SCHEDULER ENGINE
# ----------------------------

class Scheduler:
    """Greedy + insertion heuristic scheduler.

    Threshold units (stored in JSON exactly as follows):
      A, B  -> minutes of accumulated flight time
      C, D  -> calendar days since last check

    Durations (Maintenance_Durations) are always in minutes.

    Check hierarchy (heaviest resets all lighter counters):
      D check -> resets D, C, B, A
      C check -> resets C, B, A        (D counter keeps running)
      B check -> resets B, A           (C, D counters keep running)
      A check -> resets A only         (B, C, D counters keep running)
    """

    def __init__(self, data_path, allow_ferry=True, heuristic='greedy+insertion',
                 aco_iterations=20, aco_ants=8, aco_evaporation=0.2,
                 aco_beta=2.0, aco_seed=0):
        with open(data_path, 'r') as f:
            self.data = json.load(f)

        self.flights = {
            fl[0]: {'fid': fl[0], 'orig': fl[1], 'dest': fl[2],
                    'dep': float(fl[3]), 'arr': float(fl[4]),
                    'dur': float(fl[4]) - float(fl[3])}
            for fl in self.data['Flights']
        }
        self.aircrafts   = self.data['Aircrafts']
        self.init_pos    = self.data['AIRCRAFT_INIT_POS']
        self.init_checks = self.data['Initial_Checks']

        # A/B thresholds in MINUTES; C/D thresholds in DAYS
        self.thresh_ab = {
            'A': float(self.data['Maintenance_Thresholds']['A']),
            'B': float(self.data['Maintenance_Thresholds']['B']),
        }
        self.thresh_cd = {
            'C': float(self.data['Maintenance_Thresholds']['C']),
            'D': float(self.data['Maintenance_Thresholds']['D']),
        }
        # Durations always in minutes
        self.durations   = {k: float(v) for k, v in self.data['Maintenance_Durations'].items()}
        self.station_cap = self.data['Station_Capacity']
        self.cost_matrix = self.data['Cost_Matrix']
        self.allow_ferry = bool(allow_ferry)
        self.heuristic = self._normalize_heuristic(heuristic)

        self.ferry_time = 60
        self.ferry_cost = 6000
        self.aco_iterations = max(1, int(aco_iterations))
        self.aco_ants = max(1, int(aco_ants))
        self.aco_evaporation = min(1.0, max(0.0, float(aco_evaporation)))
        self.aco_beta = max(0.0, float(aco_beta))
        self.aco_seed = int(aco_seed)

    @staticmethod
    def _normalize_heuristic(heuristic):
        if heuristic is None:
            return 'greedy+insertion'
        key = str(heuristic).strip().lower().replace(' ', '')
        if key in {'greedy', 'greedyonly'}:
            return 'greedy'
        if key in {'insertion', 'bestinsertion'}:
            return 'insertion'
        if key in {'greedy+insertion', 'greedyinsertion', 'hybrid', 'combined'}:
            return 'greedy+insertion'
        if key in {'repair', 'greedyrepair', 'greedy+repair'}:
            return 'repair'
        if key in {'localsearch', 'local_search', 'localsearch', 'improve'}:
            return 'local_search'
        if key in {'dijkstra', 'modifieddijkstra', 'dijkstraheuristic'}:
            return 'dijkstra'
        if key in {'aco', 'antcolony', 'antcolonyoptimization'}:
            return 'aco'
        raise ValueError(
            f"Unsupported heuristic '{heuristic}'. Choose one of: greedy, insertion, greedy+insertion, repair, local_search, dijkstra, aco"
        )

    # ------------------------------------------------------------------
    def _init_counters(self, aid):
        """Return (a_min, b_min, c_days, d_days) for aircraft aid."""
        sid = str(aid)
        ic  = self.init_checks
        # A/B: accumulated flight minutes since last check
        a = float(ic.get('A', {}).get(sid, 0))
        b = float(ic.get('B', {}).get(sid, 0))
        # C/D: calendar days elapsed since last check
        c = float(ic.get('C_Days', ic.get('C', {})).get(sid, 0))
        d = float(ic.get('D_Days', ic.get('D', {})).get(sid, 0))
        return a, b, c, d

    @staticmethod
    def _reset_counters(needed, a, b, c_days, t_now_min):
        """Apply hierarchy reset after performing *needed* check.

        Parameters
        ----------
        t_now_min : float  Current schedule time in minutes (after check ends).

        Returns updated (a, b, c_days, d_days_offset).
        The d_days value is returned as an *offset* so that
        ``d_days_offset + (curr_time / 1440)`` gives elapsed days since last D check.
        """
        t_days = t_now_min / 1440.0
        if needed == 'D':
            # D is most comprehensive − resets all counters
            return 0.0, 0.0, -t_days, -t_days   # (a, b, c_offset, d_offset)
        elif needed == 'C':
            # C resets flight-hour counters A & B, and the C calendar counter
            return 0.0, 0.0, -t_days, None       # d_offset=None -> unchanged
        elif needed == 'B':
            # B resets flight-hour counters A & B only
            return 0.0, 0.0, None, None
        else:  # 'A'
            # A resets only its own flight-hour counter
            return 0.0, None, None, None

    def get_timeline(self, aid, fids):
        """Simulate one aircraft's schedule and return event list + cost.

        Returns None if the assignment is infeasible.
        """
        curr_apt  = self.init_pos[str(aid)]
        curr_time = 0.0          # minutes into the planning horizon
        a, b, c_off, d_off = self._init_counters(aid)
        # c_days_elapsed = c_off + (curr_time / 1440)  (same for d)

        events     = []
        total_cost = 0.0

        for fid in fids:
            fl = self.flights[fid]

            # ── 1. Ferry / repositioning ──────────────────────────────────
            if curr_apt != fl['orig']:
                if not self.allow_ferry:
                    return None
                if curr_time + self.ferry_time > fl['dep']:
                    return None
                events.append({
                    'kind': 'FERRY', 'start': curr_time,
                    'end':  curr_time + self.ferry_time,
                    'orig': curr_apt, 'dest': fl['orig'],
                    'cost': self.ferry_cost,
                })
                curr_time += self.ferry_time
                curr_apt   = fl['orig']
                total_cost += self.ferry_cost

            # ── 2. Maintenance check (before departing this flight) ───────
            days_now = curr_time / 1440.0
            # D then C (day-based); B then A (flight-hour-based)
            # Priority: heaviest check wins so hierarchy reset is maximal
            needed = None
            if   d_off + days_now >= self.thresh_cd['D']:          needed = 'D'
            elif c_off + days_now >= self.thresh_cd['C']:          needed = 'C'
            elif b + fl['dur']    >= self.thresh_ab['B']:          needed = 'B'
            elif a + fl['dur']    >= self.thresh_ab['A']:          needed = 'A'

            if needed:
                m_dur   = self.durations[needed]
                if curr_time + m_dur > fl['dep']:                    return None
                if self.station_cap.get(fl['orig'], 0) == 0:         return None

                events.append({
                    'kind': 'MAINT', 'check': needed,
                    'start': curr_time, 'end': curr_time + m_dur,
                    'orig': fl['orig'], 'dest': fl['orig'],
                })
                curr_time += m_dur

                # Apply hierarchy reset
                na, nb, nc, nd = self._reset_counters(needed, a, b, c_off, curr_time)
                if na is not None: a     = na
                if nb is not None: b     = nb
                if nc is not None: c_off = nc
                if nd is not None: d_off = nd

            # ── 3. Flight execution ───────────────────────────────────────
            if curr_time > fl['dep']:
                return None

            days_dep = fl['dep'] / 1440.0
            snap = {
                'rem_a':  self.thresh_ab['A'] - a,          # minutes remaining
                'rem_b':  self.thresh_ab['B'] - b,
                'rem_c':  self.thresh_cd['C'] - (c_off + days_dep),  # days remaining
                'rem_d':  self.thresh_cd['D'] - (d_off + days_dep),
            }
            events.append({
                'kind': 'FLIGHT', 'fid': fid,
                'start': fl['dep'], 'end': fl['arr'],
                'orig': fl['orig'], 'dest': fl['dest'],
                'cost': self.cost_matrix[fid - 1][aid],
                'dur':  fl['dur'],
                **snap,
            })

            curr_time  = fl['arr']
            curr_apt   = fl['dest']
            # Accumulate flight minutes for A & B counters
            a          += fl['dur']
            b          += fl['dur']
            total_cost += self.cost_matrix[fid - 1][aid]

        return {'events': events, 'cost': total_cost}

    def _best_feasible_insertion(self, ac_fids, fid):
        """Return the cheapest feasible insertion location for a flight."""
        best_ins = None
        for aid in self.aircrafts:
            for i in range(len(ac_fids[aid]) + 1):
                trial = ac_fids[aid][:i] + [fid] + ac_fids[aid][i:]
                res = self.get_timeline(aid, trial)
                if res and (best_ins is None or res['cost'] < best_ins[2]):
                    best_ins = (aid, i, res['cost'])
        return best_ins

    def _total_cost(self, ac_fids):
        """Return the sum of assignment costs across all aircraft schedules."""
        total_cost = 0.0
        for aid in self.aircrafts:
            res = self.get_timeline(aid, ac_fids[aid])
            if res is None:
                return None
            total_cost += res['cost']
        return total_cost

    def _best_feasible_relocation(self, ac_fids, fid):
        """Try moving a flight to a different aircraft/position if it lowers cost."""
        current_aid = None
        for aid in self.aircrafts:
            if fid in ac_fids[aid]:
                current_aid = aid
                break
        if current_aid is None:
            return None

        current_cost = self._total_cost(ac_fids)
        if current_cost is None:
            return None

        removed = {aid: list(ac_fids[aid]) for aid in self.aircrafts}
        removed[current_aid] = [f for f in removed[current_aid] if f != fid]

        best_move = None
        for target_aid in self.aircrafts:
            for idx in range(len(removed[target_aid]) + 1):
                trial = {aid: list(seq) for aid, seq in removed.items()}
                trial[target_aid].insert(idx, fid)
                candidate_cost = self._total_cost(trial)
                if candidate_cost is None:
                    continue
                if best_move is None or candidate_cost < best_move[2]:
                    best_move = (target_aid, idx, candidate_cost)

        if best_move and best_move[2] < current_cost - 1e-9:
            return best_move
        return None

    def _dijkstra_best_path(self, aid, seed_route, candidate_fids):
        """Return a maximum-coverage path for one aircraft.

        The space-time graph is represented implicitly: each candidate flight
        is a node and a transition is an arc when the extended route passes
        ``get_timeline``.  Labels are kept per terminal flight.  Coverage is
        the primary label criterion and simulated incremental route cost is
        the tie-breaker, matching the documented modified Dijkstra rule.
        """
        if not candidate_fids:
            return None

        seed_result = self.get_timeline(aid, seed_route)
        if seed_result is None:
            return None
        seed_cost = seed_result['cost']
        ordered = sorted(candidate_fids, key=lambda fid: self.flights[fid]['dep'])
        labels = {}

        for fid in ordered:
            trial = seed_route + [fid]
            result = self.get_timeline(aid, trial)
            if result is not None:
                labels[fid] = ([fid], result['cost'] - seed_cost)

            for previous_fid, (previous_path, previous_cost) in list(labels.items()):
                if self.flights[previous_fid]['arr'] > self.flights[fid]['dep']:
                    continue
                trial = seed_route + previous_path + [fid]
                result = self.get_timeline(aid, trial)
                if result is None:
                    continue
                candidate_label = (previous_path + [fid], result['cost'] - seed_cost)
                current_label = labels.get(fid)
                if (current_label is None
                        or len(candidate_label[0]) > len(current_label[0])
                        or (len(candidate_label[0]) == len(current_label[0])
                            and candidate_label[1] < current_label[1])):
                    labels[fid] = candidate_label

        best = None
        for path, incremental_cost in labels.values():
            if (best is None
                    or len(path) > len(best[0])
                    or (len(path) == len(best[0])
                        and incremental_cost < best[1])):
                best = (path, incremental_cost)
        return best

    def _optimize_dijkstra(self):
        """Construct a schedule using repeated modified-Dijkstra paths."""
        ac_fids = {aid: [] for aid in self.aircrafts}
        assigned = set()
        all_fids = set(self.flights)
        aircraft_order = sorted(
            self.aircrafts,
            key=lambda aid: sum(self.cost_matrix[fid - 1][aid] for fid in self.flights),
        )

        while assigned != all_fids:
            remaining = all_fids - assigned
            best_choice = None
            for aid in aircraft_order:
                path_label = self._dijkstra_best_path(aid, ac_fids[aid], remaining)
                if path_label is None:
                    continue
                path, incremental_cost = path_label
                choice = (len(path), -incremental_cost, aid, path)
                if best_choice is None or choice[:2] > best_choice[:2]:
                    best_choice = choice

            if best_choice is None:
                break
            _, _, aid, path = best_choice
            ac_fids[aid].extend(path)
            assigned.update(path)

        return ac_fids, [fid for fid in self.flights if fid not in assigned]

    @staticmethod
    def _weighted_choice(options, weights, rng):
        """Select one option from non-negative weights using ``rng``."""
        total = sum(weights)
        if total <= 0.0:
            return options[rng.randrange(len(options))]
        target = rng.random() * total
        cumulative = 0.0
        for option, weight in zip(options, weights):
            cumulative += weight
            if cumulative >= target:
                return option
        return options[-1]

    def _aco_construct_ant(self, sorted_fids, pheromone, rng):
        """Construct one probabilistic, timeline-feasible assignment."""
        routes = {aid: [] for aid in self.aircrafts}
        assigned = set()
        route_costs = {aid: 0.0 for aid in self.aircrafts}
        transitions = []

        for fid in sorted_fids:
            options = []
            weights = []
            for aid in self.aircrafts:
                route = routes[aid]
                result = self.get_timeline(aid, route + [fid])
                if result is None:
                    continue
                previous = route[-1] if route else None
                incremental_cost = result['cost'] - route_costs[aid]
                trail = pheromone.get((aid, previous, fid), 1.0)
                desirability = 1.0 / (1.0 + max(0.0, incremental_cost))
                options.append((aid, incremental_cost))
                weights.append(max(0.0, trail) * desirability ** self.aco_beta)

            if not options:
                continue
            aid, incremental_cost = self._weighted_choice(options, weights, rng)
            previous = routes[aid][-1] if routes[aid] else None
            routes[aid].append(fid)
            route_costs[aid] += incremental_cost
            assigned.add(fid)
            transitions.append((aid, previous, fid))

        return routes, assigned, sum(route_costs.values()), transitions

    def _optimize_aco(self):
        """Construct a schedule with pheromone-guided route exploration."""
        import random as _random

        sorted_fids = sorted(self.flights, key=lambda fid: self.flights[fid]['dep'])
        pheromone = {}
        rng = _random.Random(self.aco_seed)
        best = None

        for _ in range(self.aco_iterations):
            iteration_best = None
            ant_results = []
            for _ in range(self.aco_ants):
                result = self._aco_construct_ant(sorted_fids, pheromone, rng)
                ant_results.append(result)
                routes, assigned, total_cost, transitions = result
                score = (len(assigned), -total_cost)
                if iteration_best is None or score > iteration_best[0]:
                    iteration_best = (score, result)
                if best is None or score > best[0]:
                    best = (score, result)

            evaporation = self.aco_evaporation
            for key in list(pheromone):
                pheromone[key] = (1.0 - evaporation) * pheromone[key] + evaporation

            if iteration_best is not None:
                score, (_, assigned, total_cost, transitions) = iteration_best
                deposit = max(1.0, float(score[0])) / (1.0 + max(0.0, total_cost))
                for key in transitions:
                    pheromone[key] = pheromone.get(key, 1.0) + deposit

        if best is None:
            return {aid: [] for aid in self.aircrafts}, sorted_fids
        _, (routes, assigned, _, _) = best
        return routes, [fid for fid in self.flights if fid not in assigned]

    def optimize(self):
        ac_fids = {aid: [] for aid in self.aircrafts}
        assigned = set()
        sorted_fids = sorted(self.flights.keys(), key=lambda x: self.flights[x]['dep'])

        if self.heuristic == 'dijkstra':
            return self._optimize_dijkstra()

        if self.heuristic == 'aco':
            return self._optimize_aco()

        if self.heuristic == 'greedy':
            for fid in sorted_fids:
                best_opt = None
                for aid in self.aircrafts:
                    res = self.get_timeline(aid, ac_fids[aid] + [fid])
                    if res and (best_opt is None or res['cost'] < best_opt[0]):
                        best_opt = (res['cost'], aid)
                if best_opt:
                    ac_fids[best_opt[1]].append(fid)
                    assigned.add(fid)
            return ac_fids, [fid for fid in self.flights if fid not in assigned]

        if self.heuristic == 'insertion':
            for fid in sorted_fids:
                best_ins = self._best_feasible_insertion(ac_fids, fid)
                if best_ins:
                    aid, idx, _ = best_ins
                    ac_fids[aid].insert(idx, fid)
                    assigned.add(fid)
            return ac_fids, [fid for fid in self.flights if fid not in assigned]

        if self.heuristic == 'repair':
            for fid in sorted_fids:
                best_opt = None
                for aid in self.aircrafts:
                    res = self.get_timeline(aid, ac_fids[aid] + [fid])
                    if res and (best_opt is None or res['cost'] < best_opt[0]):
                        best_opt = (res['cost'], aid)
                if best_opt:
                    ac_fids[best_opt[1]].append(fid)
                    assigned.add(fid)

            for _ in range(8):
                improved = False
                still_unassigned = [fid for fid in self.flights if fid not in assigned]
                for fid in still_unassigned:
                    best_ins = self._best_feasible_insertion(ac_fids, fid)
                    if best_ins:
                        aid, idx, _ = best_ins
                        ac_fids[aid].insert(idx, fid)
                        assigned.add(fid)
                        improved = True
                if not improved:
                    break
            return ac_fids, [fid for fid in self.flights if fid not in assigned]

        if self.heuristic == 'local_search':
            for fid in sorted_fids:
                best_opt = None
                for aid in self.aircrafts:
                    res = self.get_timeline(aid, ac_fids[aid] + [fid])
                    if res and (best_opt is None or res['cost'] < best_opt[0]):
                        best_opt = (res['cost'], aid)
                if best_opt:
                    ac_fids[best_opt[1]].append(fid)
                    assigned.add(fid)

            for _ in range(3):
                improved = False
                for fid in sorted_fids:
                    if fid not in assigned:
                        continue
                    move = self._best_feasible_relocation(ac_fids, fid)
                    if move:
                        target_aid, idx, _ = move
                        current_aid = None
                        for aid in self.aircrafts:
                            if fid in ac_fids[aid]:
                                current_aid = aid
                                break
                        if current_aid is None:
                            continue
                        ac_fids[current_aid] = [f for f in ac_fids[current_aid] if f != fid]
                        ac_fids[target_aid].insert(idx, fid)
                        improved = True
                if not improved:
                    break

            for _ in range(4):
                improved = False
                still_unassigned = [fid for fid in self.flights if fid not in assigned]
                for fid in still_unassigned:
                    best_ins = self._best_feasible_insertion(ac_fids, fid)
                    if best_ins:
                        aid, idx, _ = best_ins
                        ac_fids[aid].insert(idx, fid)
                        assigned.add(fid)
                        improved = True
                if not improved:
                    break
            return ac_fids, [fid for fid in self.flights if fid not in assigned]

        # Default: greedy first, then iterative insertion refinement.
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
                best_ins = self._best_feasible_insertion(ac_fids, fid)
                if best_ins:
                    aid, idx, _ = best_ins
                    ac_fids[aid].insert(idx, fid)
                    assigned.add(fid)

        return ac_fids, [fid for fid in self.flights if fid not in assigned]

# ----------------------------
# MILP OPTIMIZER ENGINE
# ----------------------------

class MILP_Sheduler:
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

    # Hierarchy: performing check X also satisfies all lighter checks
    CHECK_HIERARCHY = {
        'A': ['A', 'B', 'C', 'D'],
        'B': ['B', 'C', 'D'],
        'C': ['C', 'D'],
        'D': ['D'],
    }

    def __init__(self, data_path, maintenance_airports=None,
                 max_hour_check_deferral_days=None, enabled_checks=None):
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

        logger = logging.getLogger(__name__)
        
        logging.basicConfig(filename="debug.log" , level=logging.DEBUG)

    
        self.data_path = data_path
        base_checks = list(type(self).CHECK_LIST)
        if enabled_checks is None:
            active_checks = base_checks
        else:
            requested = []
            for check in enabled_checks:
                check_up = str(check).upper()
                if check_up not in requested:
                    requested.append(check_up)
            invalid = [check for check in requested if check not in base_checks]
            if invalid:
                raise ValueError(
                    f"Invalid check type(s): {invalid}. Allowed: {base_checks}"
                )
            active_checks = [check for check in base_checks if check in requested]
            if not active_checks:
                raise ValueError(
                    "enabled_checks resolved to an empty set; "
                    "select at least one of A,B,C,D."
                )
        # Instance-level override used by all constraint builders.
        self.CHECK_LIST = active_checks
        with open(data_path) as f:
            raw = json.load(f)

        logger.debug(f"Loaded data from {data_path}")
        self.max_hour_check_deferral_days = max_hour_check_deferral_days
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

            logger.debug(f"Loaded flight {fid}: {orig} -> {dest}, dep={dep}, arr={arr}, dur={arr - dep}, days={self.flight_data[fid]['day_departure']}-{self.flight_data[fid]['day_arrival']}")
        # ── Aircrafts & initial positions ────────────────────────────────────
        self.aircraft_ids  = raw['Aircrafts']
        logger.debug(f"Loaded aircrafts: {self.aircraft_ids}")
        self.aircraft_init = {int(k): v for k, v in raw['AIRCRAFT_INIT_POS'].items()}
        logger.debug(f"Loaded initial positions: {self.aircraft_init}")

        # ── Airports ─────────────────────────────────────────────────────────
        all_airports = sorted(set(
            fd['origin']      for fd in self.flight_data.values()
        ) | set(
            fd['destination'] for fd in self.flight_data.values()
        ))
        self.airports = all_airports
        logger.debug(f"Loaded airports: {self.airports}")

        cap = raw['Station_Capacity']
        if maintenance_airports is not None:
            self.maint_airports = maintenance_airports
        else:
            self.maint_airports = sorted(a for a in all_airports if cap.get(a, 0) > 0)
        logger.debug(f"Loaded maintenance airports: {self.maint_airports}")

        # station_cap[airport] = max concurrent maintenance slots (all check types combined)
        self.station_cap = {a: cap.get(a, 0) for a in all_airports}
        logger.debug(f"Loaded station capacities: {self.station_cap}")

        # ── Thresholds & durations ───────────────────────────────────────────
        thresh = raw['Maintenance_Thresholds']  # A/B in minutes, C/D in days
        durs   = raw['Maintenance_Durations']   # all in minutes
        logger.debug(f"Loaded maintenance thresholds: {thresh}:{durs}")

        # Hours thresholds used in cumulative flight-hour constraints
        # A/B stored as minutes -> convert; C/D stored as days -> ×24
        self.check_hrs = {
            'A': thresh['A'] / 60.0,
            'B': thresh['B'] / 60.0,
            'C': thresh['C'] * 24.0,
            'D': thresh['D'] * 24.0,
        }
        logger.debug(f"Converted check hour thresholds: {self.check_hrs}")
        # Day-interval thresholds for spacing constraints.
        # A and B thresholds are in flight-minutes (not calendar days);
        # their spacing is handled by C13 (hour accumulation), NOT C12.
        # C and D are already in calendar days.
        # Use None to mark check types with no calendar-day spacing constraint.
        self.check_days = {
            'A': None,          # flight-hour based -> no calendar-day spacing
            'B': None,    # flight-hour based -> no calendar-day spacing
            'C': int(thresh['C']),
            'D': int(thresh['D']),
        }
        self.check_dur     = {k: float(durs[k]) for k in self.CHECK_LIST}  # minutes
        logger.debug(f"Loaded check durations (minutes): {self.check_dur}")
        self.check_dur_days = {k: int(durs[k] // self.DAY_SHIFT) for k in self.CHECK_LIST}
        logger.debug(f"Converted check durations (days): {self.check_dur_days}")

        # ── Initial check state (convert all to hours) ───────────────────────
        # JSON may use 'A','B' (minutes) and 'C','D' or 'C_Days','D_Days' (days)
        init_ck = raw.get('Initial_Checks', {})
        self.init_check_hrs = {}
        for ck in self.CHECK_LIST:
            if ck in ('C', 'D'):
                # Prefer C_Days / D_Days key (values in days); fall back to C/D (minutes)
                day_key = f'{ck}_Days'
                if day_key in init_ck:
                    # values are in days -> convert to hours
                    self.init_check_hrs[ck] = {
                        aid: float(init_ck[day_key].get(str(aid), 0)) * 24.0
                        for aid in self.aircraft_ids
                    }
                else:
                    # values are in minutes -> convert to hours
                    self.init_check_hrs[ck] = {
                        aid: float(init_ck.get(ck, {}).get(str(aid), 0)) / 60.0
                        for aid in self.aircraft_ids
                    }
            else:  # A, B  — always in minutes in both file formats
                self.init_check_hrs[ck] = {
                    aid: float(init_ck.get(ck, {}).get(str(aid), 0)) / 60.0
                    for aid in self.aircraft_ids
                }
        logger.debug(f"Loaded initial check hours: {self.init_check_hrs}")

        # ── Cost matrix ───────────────────────────────────────────────────────
        # cost_matrix[fid-1][aid_index]  (outer index = flight, inner = aircraft)
        self.cost_matrix = raw['Cost_Matrix']
        self._aid_index  = {aid: idx for idx, aid in enumerate(self.aircraft_ids)}

        # Sparse assignment arcs.
        # Treat cost >= 9999 as effectively forbidden; if a flight has no arc
        # below that cutoff, fall back to all aircraft so the model remains
        # constructible.
        self.x_arcs_by_flight = {}
        self.x_arcs_by_aircraft = {aid: [] for aid in self.aircraft_ids}
        self.x_arcs_set = set()
        self.x_var_count = 0
        for fid in self.flight_ids:
            feasible = [aid for aid in self.aircraft_ids
                        if self._flight_cost(fid, aid) < 9999]
            if not feasible:
                feasible = list(self.aircraft_ids)
            self.x_arcs_by_flight[fid] = tuple(feasible)
            self.x_var_count += len(feasible)
            for aid in feasible:
                self.x_arcs_by_aircraft[aid].append(fid)
                self.x_arcs_set.add((fid, aid))

        # ── Planning horizon (days) ───────────────────────────────────────────
        max_day = max(fd['day_arrival'] for fd in self.flight_data.values()) + 1
        max_day = max(8, max_day)
        self.days = list(range(1, max_day + 1))

        # Cached flight groupings to avoid repeated full-table scans inside
        # routing and maintenance constraint builders.
        self._dep_flights_by_airport = {a: [] for a in self.airports}
        self._arr_flights_by_airport = {a: [] for a in self.airports}
        self._dep_flights_by_day_airport = {
            (d, a): [] for d in self.days for a in self.airports
        }
        for fid, fd in self.flight_data.items():
            self._dep_flights_by_airport[fd['origin']].append(fid)
            self._arr_flights_by_airport[fd['destination']].append(fid)
            self._dep_flights_by_day_airport[(fd['day_departure'], fd['origin'])].append(fid)

        # ── Big-M values ──────────────────────────────────────────────────────
        # M_BIG is used in C13/C13b (hour-accumulation) big-M relaxations.
        # Large M is intentional: C13b with tight M makes the LP relaxation
        # harder (more simplex pivots), which slows CPLEX on large instances.
        # M_C14b is used only in C14b (check duration); it only needs to exceed
        # the max check duration in days.
        self.M_BIG  = 9_999_999
        self.M_C14b = max(self.check_dur_days.values()) + 1

        # ── Maintenance-eligible flights (z index restriction) ─────────────────
        # z[i,j,d,c] is only meaningful for flights i arriving at a maintenance
        # airport.  Restricting the z domain reduces variables and constraints
        # by ~42-50% compared to indexing z over all flights.
        ma_set = set(self.maint_airports)
        self.maint_flight_ids = [
            fid for fid, fd in self.flight_data.items()
            if fd['destination'] in ma_set
        ]
        logger.debug(f"Loaded maintenance-eligible flights: {self.maint_flight_ids}")

        # Sparse z-domain cache.
        # A/B checks may start on any day from the trigger flight's arrival day
        # through the end of the horizon. C/D checks only need the consecutive
        # days they occupy; the old model created the full horizon and then
        # forced most of those variables to zero.
        self.z_days_by_flight_check = {}
        self.z_flights_by_day_check = {
            (d, c): [] for d in self.days for c in self.CHECK_LIST
        }
        self.z_var_count = 0
        last_day = self.days[-1]
        for fid in self.maint_flight_ids:
            arr_day = self.flight_data[fid]['day_arrival']
            for ck in self.CHECK_LIST:
                if self.check_days[ck] is None:
                    if self.max_hour_check_deferral_days is None:
                        end_day = last_day
                    else:
                        end_day = min(
                            arr_day + int(self.max_hour_check_deferral_days),
                            last_day,
                        )
                else:
                    span_days = max(1, self.check_dur_days[ck])
                    end_day = min(arr_day + span_days - 1, last_day)
                days_for_key = tuple(range(arr_day, end_day + 1))
                self.z_days_by_flight_check[(fid, ck)] = days_for_key
                self.z_var_count += len(days_for_key) * len(self.aircraft_ids)
                for day in days_for_key:
                    self.z_flights_by_day_check[(day, ck)].append(fid)

        self.c8_same_day_block = {}
        self.c8_escape = {}
        self.c8_same_day_block_feasible = {}
        self.c8_escape_feasible = {}
        self.c8_check_day_departures_feasible = {}
        for fid in self.maint_flight_ids:
            fd_i = self.flight_data[fid]
            apt = fd_i['destination']
            d_i = fd_i['day_arrival']
            arr_i = fd_i['arrivalTime']
            same_day_deps = tuple(self._dep_flights_by_day_airport[(d_i, apt)])
            escape = tuple(fid2 for fid2 in same_day_deps if self.flight_data[fid2]['departureTime'] > arr_i)
            for ck in self.CHECK_LIST:
                dur = self.check_dur[ck]
                same_day_block = tuple(
                    fid2 for fid2 in same_day_deps
                    if arr_i < self.flight_data[fid2]['departureTime'] <= arr_i + dur
                )
                self.c8_same_day_block[(fid, ck)] = same_day_block
                self.c8_escape[(fid, ck)] = escape
                for aid in self.aircraft_ids:
                    self.c8_same_day_block_feasible[(fid, ck, aid)] = tuple(
                        fid2 for fid2 in same_day_block if self._x_has_arc(fid2, aid)
                    )
                    self.c8_escape_feasible[(fid, ck, aid)] = tuple(
                        fid2 for fid2 in escape if self._x_has_arc(fid2, aid)
                    )
            for day in self.days:
                day_deps = tuple(self._dep_flights_by_day_airport[(day, apt)])
                for aid in self.aircraft_ids:
                    self.c8_check_day_departures_feasible[(fid, day, aid)] = tuple(
                        fid2 for fid2 in day_deps if self._x_has_arc(fid2, aid)
                    )

        # Model and results (populated by build_model / solve)
        self.model   = None
        self.results = None

    def _z_days_for(self, fid, check_type):
        return self.z_days_by_flight_check[(fid, check_type)]

    def _z_trigger_flights(self, day, check_type):
        return self.z_flights_by_day_check.get((day, check_type), ())

    def _x_aircrafts_for_flight(self, fid):
        return self.x_arcs_by_flight[fid]

    def _x_flights_for_aircraft(self, aid):
        return self.x_arcs_by_aircraft[aid]

    def _x_has_arc(self, fid, aid):
        return (fid, aid) in self.x_arcs_set

    # ------------------------------------------------------------------
    # Model construction
    # ------------------------------------------------------------------

    def build_model(self,
                    use_day_spacing=True,
                    use_existing_hrs=True,
                    use_check_hierarchy=True,
                    use_sanity=False,
                    use_overlap=True,
                    allow_ferry=True,
                    use_maintenance=True,
                    use_strong_maint_link=False,
                    use_paper_c13=False,
                    soft_coverage=False,
                    coverage_weight=1_000_000.0):
        """Construct the ConcreteModel.  Call before solve().

        Parameters
        ----------
        allow_ferry : bool
            When *True* (default) the C2-C3 equipment-flow / turnaround
            constraints are included.  Set to *False* for a pure
            assignment + maintenance model (smaller, faster; ferry flights
            may be needed to execute the resulting schedule in practice).
        use_maintenance : bool
            When *True* (default) all maintenance constraints (C8-C15,
            check hierarchy, duration, day-spacing, hr-accumulation) are
            added.  Set to *False* to solve a pure flight-assignment model
            (no check scheduling) — dramatically fewer constraints, much
            faster to solve, useful as an upper-bound / relaxation benchmark.
        use_strong_maint_link : bool
            When *True*, use the strengthened sparse trigger-to-assignment
            link for every maintenance check type.  The default preserves
            the baseline formulation.
        use_paper_c13 : bool
            When *True*, add the original Khaled et al. (2018) Eq. (13)
            single-constraint form (vacuous when either endpoint indicator
            is 0; see docs/model_math.tex, Lemma on Constraint (13)) instead
            of the corrected split formulation.  Default *False* uses the
            corrected constraint.
        """
        m = ConcreteModel()
        self.model = m
        self.soft_coverage = bool(soft_coverage)
        self.coverage_weight = float(coverage_weight)
        self._add_sets_and_variables(m)
        self._add_objective(m)
        self._add_c1_coverage(m)
        if allow_ferry:
            # C2-C3: equipment-flow balance (prevents implicit teleportation)
            self._add_c23_turn(m)
        if use_overlap:
            
            self._add_overlap(m)
        if use_maintenance:
            self._add_c8_maint_blocks_flights(m)
            self._add_c9_maint_assignment(m, strong_link=use_strong_maint_link)
            self._add_c10_capacity(m)
            self._add_c11_maint_link(m)
            self._add_hierarchy(m, use_check_hierarchy)
            self._add_c14_one_check_per_day(m)
            self._add_c14b_check_duration(m)
            if use_day_spacing:
                self._add_c12_day_spacing(m)
            self._add_c12b_initial_days(m)   # enforce first C/D check within remaining-days window
            self._add_c12_day_spacing_days(m)
            if use_existing_hrs:
                self._add_c13b_existing_hrs(m)
            self._add_c13_hr_accumulation(m, use_paper_c13=use_paper_c13)
            self._add_c15_no_flight_during_maint(m)
        if use_sanity:
            self._add_sanity(m)
        
        #input("Model built. Press Enter to continue...")  # Debug pause to inspect model before solving
        return m

    def _add_sets_and_variables(self, m):
        """Define Pyomo Sets and Var declarations on model m."""
        m.F   = Set(initialize=self.flight_ids)
        m.FM  = Set(initialize=self.maint_flight_ids)  # flights arriving at MA
        m.P   = Set(initialize=sorted(self.aircraft_ids))
        m.A   = Set(initialize=self.airports)
        m.MA  = Set(initialize=self.maint_airports)
        m.D   = Set(initialize=sorted(self.days))
        m.C   = Set(initialize=self.CHECK_LIST)

        # x[i,j] = 1  iff flight i assigned to aircraft j
        def _x_index_init(_m):
            for i in self.flight_ids:
                for j in self._x_aircrafts_for_flight(i):
                    yield (i, j)
        m.X = Set(dimen=2, initialize=_x_index_init)
        m.x = Var(m.X, domain=Binary, initialize=0)
        if self.soft_coverage:
            m.u = Var(m.F, domain=Binary, initialize=0)
        # z[i,j,d,c] = 1  iff aircraft j does check c on day d triggered by flight i
        # Only indexed over feasible (flight, aircraft, day, check) tuples.
        def _z_index_init(_m):
            for i in self.maint_flight_ids:
                for j in self.aircraft_ids:
                    for c in self.CHECK_LIST:
                        for d in self._z_days_for(i, c):
                            yield (i, j, d, c)
        m.Z = Set(dimen=4, initialize=_z_index_init)
        print("DEBUG |FM| =", len(m.FM))
        print("DEBUG |P| =", len(m.P))
        print("DEBUG |D| =", len(m.D))
        print("DEBUG |C| =", len(m.C))
        print("DEBUG x vars =", self.x_var_count, flush=True)
        print("DEBUG z vars =", self.z_var_count, flush=True)
        m.z = Var(m.Z, domain=Binary, initialize=0)
        # y[j,d,c] = 1  iff aircraft j undergoes check c on day d
        m.y = Var(m.P, m.D, m.C, domain=Binary, initialize=0)
        # mega_check[j,d,c] = 1 if aircraft j has a check of type ≥c on day d (hierarchy)
        m.mega = Var(m.P, m.D, m.C, domain=Binary, initialize=0)

    def _add_objective(self, m):
        """Minimize flight assignment cost + premature maintenance penalty."""
        maint_cost = 100   # flat penalty per maintenance event (can be extended)
        assignment_cost = sum(self._flight_cost(i, j) * m.x[i, j]
                              for i, j in m.X)
        maintenance_cost = sum(maint_cost * m.y[j, d, c]
                               for j in m.P for d in m.D for c in m.C)
        if self.soft_coverage:
            m.obj = Objective(
                expr=(
                    -self.coverage_weight * sum(m.x[i, j] for i, j in m.X)
                    + assignment_cost
                    + maintenance_cost
                ),
                sense=minimize,
            )
            return
        m.obj = Objective(
            expr=(
                assignment_cost + maintenance_cost
            ),
            sense=minimize,
        )

    # ------------------------------------------------------------------
    # Helper index sets (computed lazily from flight_data)
    # ------------------------------------------------------------------
    def _f_arr_k(self, k):
        """Flights landing at airport k."""
        return list(self._arr_flights_by_airport[k])

    def _f_dep_k(self, k):
        """Flights departing from airport k."""
        return list(self._dep_flights_by_airport[k])

    def _f_arr_before(self, k, t, delta):
        """Flights landing at k with arrivalTime ≤ t − delta."""
        return [i for i in self._arr_flights_by_airport[k]
                if self.flight_data[i]['arrivalTime'] <= t - delta]

    def _f_dep_before(self, k, t):
        """Flights departing from k with departureTime < t."""
        return [i for i in self._dep_flights_by_airport[k]
                if self.flight_data[i]['departureTime'] < t]

    def _f_dep_window(self, k, t0, t1):
        """Flights departing from k with t0 < departureTime ≤ t1."""
        return [i for i in self._dep_flights_by_airport[k]
            if t0 < self.flight_data[i]['departureTime'] <= t1]

    def _f_dep_between_days(self, d1, d2):
        """Flights whose day_departure is in (d1, d2]."""
        return [i for i, fd in self.flight_data.items()
                if d1 < fd['day_departure'] <= d2]

    def _f_dep_on_day_airport(self, d, k):
        """Flights departing on day d from airport k."""
        return list(self._dep_flights_by_day_airport[(d, k)])

    def _f_dep_on_day_airport_after(self, d, k, t):
        """Flights departing on day d from airport k after time t."""
        return [i for i, fd in self.flight_data.items() if fd['day_departure'] == d and fd['origin'] == k and fd['departureTime'] > t]

    def _f_dep_on_day_after(self, d, t):
        """Flights departing on day d after time t."""
        return [i for i, fd in self.flight_data.items() if fd['day_departure'] == d and fd['departureTime'] > t]


    def _flight_cost(self, fid, aid):
        return self.cost_matrix[fid - 1][self._aid_index[aid]]
    
    # The set of flights for a given day when departureTime greater than arrivalTime of given flight
    def _f_dep_after(self, d, i):
        """Flights departing on day d with departureTime > arrivalTime of flight i."""
        arr_i = self.flight_data[i]['arrivalTime']
        return [i2 for i2 in self._f_dep_on_day(d)
                if self.flight_data[i2]['departureTime'] > arr_i]

    def F_m(self, a, d):
        """Flights arriving at airport a with day_arrival <= d."""
        return [i for i, fd in self.flight_data.items()
                if fd['destination'] == a and fd['day_arrival'] <= d]

    # ------------------------------------------------------------------
    # Constraint C1 – every flight covered by exactly one aircraft
    # ------------------------------------------------------------------

    def _add_c1_coverage(self, m):
        m.c1 = ConstraintList()
        for i in m.F:
            assigned = sum(m.x[i, j] for j in self._x_aircrafts_for_flight(i))
            if self.soft_coverage:
                m.c1.add(assigned + m.u[i] == 1)
            else:
                m.c1.add(assigned == 1)

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
                    if not self._x_has_arc(i, j):
                        continue
                    t = self.flight_data[i]['departureTime']
                    lhs = (sum(m.x[i1, j] for i1 in self._f_arr_before(k, t, tau)
                                 if self._x_has_arc(i1, j))
                           - sum(m.x[i1, j] for i1 in self._f_dep_before(k, t)
                                 if self._x_has_arc(i1, j)))
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
                for j in (set(self._x_aircrafts_for_flight(i)) & set(self._x_aircrafts_for_flight(i1))):
                    m.c_overlap.add(m.x[i, j] + m.x[i1, j] <= 1)

    # ------------------------------------------------------------------
    # Constraint C8 – maintenance check blocks subsequent same-day flights
    # z[i,j,d,c]=1 means aircraft j does check c on day d after flight i;
    # any flight i2 that departs the same day AFTER flight i is blocked.
    # ------------------------------------------------------------------

    def _add_c8_maint_blocks_flights(self, m):
        """C8: maintenance-triggered flight-blocking constraints.

        Three sub-blocks per (check c, trigger flight i, aircraft j):

        (a) z==0 for d < d_arr_i  — sanity: can't trigger before arrival.

        (b) Same-day trigger (d == d_arr_i): if the check STARTS on the same
            day the trigger flight lands, block departures from the maintenance
            airport that fall WITHIN the check window [t_arr_i, t_arr_i+dur(c)].
            Flights departing AFTER the check ends are NOT blocked here — the
            aircraft is free once maintenance is finished.

        (c) Deferred trigger (d > d_arr_i): if the check START is pushed to a
            later day d, the aircraft must wait at the maintenance airport from
            t_arr_i until day d.  Block:
              c1) escapes on d_arr_i after t_arr_i (can't fly away while waiting)
              c2) all departures from the maintenance airport on day d (check day)
        """
        m.c8 = ConstraintList()

        for c in self.CHECK_LIST:
            dur = self.check_dur[c]
            for i in m.FM:
                fd_i  = self.flight_data[i]
                d_i   = fd_i['day_arrival']
                arr_i = fd_i['arrivalTime']
                apt   = fd_i['destination']   # maintenance airport

                # (b) same-day blocking: WITHIN check window only
                same_day_block = self.c8_same_day_block[(i, c)]

                # (c1) escape list: all maint-airport departures on d_arr_i after arr_i
                #      used for deferred triggers (waiting-period escape prevention)
                escape = self.c8_escape[(i, c)]

                for j in m.P:
                    # (b) same-day: block in-window departures from maint airport
                    same_day_block_j = self.c8_same_day_block_feasible[(i, c, j)]
                    if same_day_block_j:
                        m.c8.add(
                            sum(m.x[i2, j] for i2 in same_day_block_j)
                            <= len(same_day_block) * (1 - m.z[i, j, d_i, c])
                        )

                    # (c) deferred: block escape + check-day departures
                    for d in self._z_days_for(i, c):
                        if d <= d_i:
                            continue
                        escape_j = self.c8_escape_feasible[(i, c, j)]
                        if escape_j:  # c1: waiting-period
                            m.c8.add(
                                sum(m.x[i2, j] for i2 in escape_j)
                                <= len(escape) * (1 - m.z[i, j, d, c])
                            )
                        check_day_departures = self.c8_check_day_departures_feasible[(i, d, j)]
                        if check_day_departures:  # c2: check day
                            m.c8.add(
                                sum(m.x[i2, j] for i2 in check_day_departures)
                                <= len(check_day_departures) * (1 - m.z[i, j, d, c])
                            )

    # ------------------------------------------------------------------
    # Constraint C9 – z[i,j,d,c] can only be 1 if x[i,j]=1
    # (maintenance triggered by a flight requires that flight is assigned)
    # ------------------------------------------------------------------

    def _add_c9_maint_assignment(self, m, strong_link=False):
        m.c9 = ConstraintList()
        for c in self.CHECK_LIST:
            for i in m.FM:  # only maintenance-eligible flights
                z_days = self._z_days_for(i, c)
                start_day = z_days[0]
                for j in self._x_aircrafts_for_flight(i):
                    if strong_link or self.check_days[c] is None:
                        m.c9.add(
                            sum(m.z[i, j, d, c] for d in z_days) <= m.x[i, j]
                        )
                    else:
                        m.c9.add(m.x[i, j] >= m.z[i, j, start_day, c])
                        
                    # di = self.flight_data[i]['day_arrival']
                    # m.c9.add(m.x[i, j] >= m.z[i, j, di, c])

    # ------------------------------------------------------------------
    # Constraint C10 – maintenance capacity per airport per day
    # ------------------------------------------------------------------

    def _add_c10_capacity(self, m):
        """C10: total maintenance slots used at each maintenance airport on each
        day cannot exceed Station_Capacity[airport].  Capacity is shared across
        ALL check types (A/B/C/D combined), matching the JSON semantics."""
        m.c10 = ConstraintList()
        # Direct lookup: station_cap is now {airport: capacity}
        cap = {a: self.station_cap[a] for a in self.maint_airports}
        # Pre-compute maintenance-eligible flights arriving at each maintenance airport
        
        for d in m.D:
            for a in m.MA:
                flights_a = self.F_m(a, d)  # flights arriving at a on or before day d
                if flights_a:
                    # Sum across ALL check types: capacity is airport-wide, not per check
                    m.c10.add(
                        sum(m.z[i, j, d, c]
                            for c in self.CHECK_LIST
                            for i in self._z_trigger_flights(d, c)
                            if i in flights_a
                            for j in m.P) <= cap[a]
                    )

    # ------------------------------------------------------------------
    # Constraint C11 – link z to y:
    # y[j,d,c] = Σ_i  z[i,j,d,c]  (summed over flights landing at MA)
    # ------------------------------------------------------------------

    def _add_c11_maint_link(self, m):
        m.c11 = ConstraintList()
        for c in self.CHECK_LIST:
            for d in m.D:
                for j in m.P:
                    m.c11.add(
                        sum(m.z[i, j, d, c] for i in self._z_trigger_flights(d, c))
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
                        covers = [c2 for c2 in self.CHECK_HIERARCHY[c]
                                  if c2 in self.CHECK_LIST]
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
            for c in self.CHECK_LIST:  # Only A/B have multi-day duration; C/D are single-day checks
                K = self.check_dur_days[c]
                if K <= 1:
                    continue
                for di, d in enumerate(days):
                    end = min(di + K, len(days))
                    if di == 0:
                        m.c14b.add(
                            sum(m.mega[j, days[d1], c] for d1 in range(1, end))
                            + self.M_C14b * (1 - m.mega[j, days[0], c]) >= end - 1
                        )
                        continue
                    if di >= end:
                        continue
                    m.c14b.add(
                        sum(m.mega[j, days[d1], c] for d1 in range(di + 1, end))
                        + self.M_C14b * m.mega[j, days[di - 1], c]
                        + self.M_C14b * (1 - m.mega[j, days[di], c]) >= end - di - 1
                    )

    # ------------------------------------------------------------------
    # Constraint C12 – day-spacing: every check-interval window must
    # contain at least one occurrence of mega[j,·,c]
    # ------------------------------------------------------------------

    def _add_c12_day_spacing(self, m):
        """Sliding-window day-spacing: within every window of `ival` consecutive
        days at least one maintenance check of type c must be scheduled.
        Only applies to check types with a calendar-day interval (C, D).
        A and B checks are regulated by flight-hour accumulation (C13), not
        calendar-day spacing, so they are skipped here.
        Also skips check types whose interval exceeds the planning horizon
        (the constraint would be trivially inactive)."""
        m.c12 = ConstraintList()
        days = sorted(self.days)
        n    = len(days)
        for c in self.CHECK_LIST:  # Only C/D have calendar-day intervals; A/B are flight-hour types
            ival = self.check_days[c]
            if ival is None:        # flight-hour threshold type: skip
                continue
            if ival >= n:           # interval >= horizon: window never filled, skip
                 continue
            for j in m.P:
                for start in range(n - ival + 1):
                    m.c12.add(
                        sum(m.mega[j, days[r], c] for r in range(start, start + ival)) >= 1
                    )

    def _add_c12b_initial_days(self, m):
        """C12b: enforce the *first* C/D calendar-day check within the planning
        horizon when the aircraft's initial elapsed days are close to (or exceed)
        the threshold.

        Logic for each aircraft j and calendar-day check type c:
          remaining = thresh_days - init_elapsed_days
          • remaining <= 0  → already overdue: force a check on day 1
          • 0 < remaining < horizon_length  → force ≥1 check in
            days [days[0] .. first day ≥ remaining]
          • remaining >= horizon_length  → C12 (sliding window) is not
            triggered AND the check need not occur in this horizon → skip

        This complements _add_c12_day_spacing, which is skipped entirely
        when check_days[c] >= n (600 >> 20), but does NOT account for the
        initial-elapsed-days offset that can bring the deadline into the horizon."""
        m.c12b = ConstraintList()
        days = sorted(self.days)
        n    = len(days)
        for c in self.CHECK_LIST:
            thresh_days = self.check_days[c]
            if thresh_days is None:       # A/B: flight-hour type, handled by C13b
                continue
            for j in m.P:
                # init_check_hrs stores hours (converted from days×24 at load time)
                init_days = self.init_check_hrs[c].get(j, 0.0) / 24.0  # hours → days
                remaining = thresh_days - init_days
                if remaining <= 0:
                    # Already overdue – force a check on the very first horizon day
                    m.c12b.add(m.mega[j, days[0], c] >= 1)
                elif remaining < n:
                    # Deadline falls within the horizon.
                    # Collect all horizon days on or before the deadline.
                    cutoff = int(math.ceil(remaining))
                    window = [d for d in days if d <= cutoff]
                    if window:
                        m.c12b.add(
                            sum(m.mega[j, d, c] for d in window) >= 1
                        )
                # else: remaining >= n → deadline beyond horizon, no constraint needed

    def _add_c12_day_spacing_days(self, m):
        """Sliding-window day-spacing: within every window of `ival` consecutive
        days at least one maintenance check of type c must be scheduled.
        Only applies to check types with a calendar-day interval (C, D).
        A and B checks are regulated by flight-hour accumulation (C13), not
        calendar-day spacing, so they are skipped here.
        Also skips check types whose interval exceeds the planning horizon
        (the constraint would be trivially inactive)."""
        m.c12days = ConstraintList()
        days = sorted(self.days)
        n    = len(days)
        for c in self.CHECK_LIST:  # Only C/D have calendar-day intervals; A/B are flight-hour types
            if self.check_days[c] is None:      # A/B: flight-hour type, skip calendar-day spacing
                continue
            ival = self.check_dur_days[c]
                        
            for j in m.P:
                for i in m.FM:  # only maintenance-eligible flights (have z variables)
                        z_days = self._z_days_for(i, c)
                        if not z_days:
                            continue
                        start_day = z_days[0]
                        for d in z_days[1:]:
                            m.c12days.add(m.z[i, j, d, c] == m.z[i, j, start_day, c])
                               

    

    # ------------------------------------------------------------------
    # Constraint C13 – cumulative flight-hour accumulation between checks
    # Between any two days d and d_ (within one check interval), total
    # flight minutes assigned to aircraft j must not exceed threshold
    # unless a check occurs in between (uses big-M relaxation).
    # ------------------------------------------------------------------

    def _add_c13_hr_accumulation(self, m, use_paper_c13=False):
        m.c13 = ConstraintList()
        days  = sorted(self.days)
        n     = len(days)
        for c in self.CHECK_LIST:
            # C13 enforces flight-hour accumulation between checks.
            # A/B thresholds are in flight-minutes; C/D thresholds are calendar
            # days (handled by C12), so skip C/D here to avoid trivial constraints.
            if self.check_days[c] is not None:   # C/D: calendar-day type -> skip
                continue
            hr_limit  = self.check_hrs[c]   # hours (A/B only)
            # For A/B check_days is None; enforce over the full horizon.
            for j in m.P:
                for si in range(n - 1):
                    for ei in range(si + 2, n):
                        d,  d_ = days[si], days[ei]
                        t_sum  = sum(
                            self.flight_data[i]['duration'] * m.x[i, j]
                            for i in self._f_dep_between_days(d, d_)
                            if self._x_has_arc(i, j)
                        )
                        y_mid  = sum(m.mega[j, days[r], c]
                                     for r in range(si + 1, ei))
                        if use_paper_c13:
                            # Original Khaled et al. (2018) Eq. (13): a single
                            # constraint keyed on (2 - mega[d] - mega[d_]), which
                            # is trivially satisfied whenever either endpoint
                            # indicator is 0 (docs/model_math.tex, Lemma).
                            m.c13.add(
                                t_sum <= hr_limit * 60
                                         + self.M_BIG * (2 - m.mega[j, d, c] - m.mega[j, d_, c])
                                         + self.M_BIG * y_mid
                            )
                            continue
                        # Two separate constraints: each relaxed by one boundary
                        # check so the pair is binding whenever either boundary
                        # day (or the interior) has no check.
                        #   row 1: relax when check AT d  (counter reset before window)
                        #   row 2: relax when check AT d_ (counter reset at window end)
                        # Without any check in [d, d_]: both reduce to
                        #   t_sum <= hr_limit*60  → correctly enforced.
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
        """C13b: account for hours accumulated since last check BEFORE the
        planning horizon starts.  Only applies to A/B (flight-hour types);
        C/D are calendar-day types handled by C12."""
        m.c13b = ConstraintList()
        days = sorted(self.days)
        n    = len(days)
        for c in self.CHECK_LIST:
            if self.check_days[c] is not None:   # C/D: skip (calendar-day type)
                continue
            hr_limit = self.check_hrs[c]
            for j in m.P:
                prior_hrs = self.init_check_hrs[c].get(j, 0.0)
                # Iterate up to and including the last day (fixed off-by-one:
                # was range(1, min(n-1, cd)) which dropped the final window).
                for ei in range(1, n):
                    d_   = days[ei]
                    t_sum = sum(
                        self.flight_data[i]['duration'] * m.x[i, j]
                        for i in self._f_dep_between_days(0, d_)
                        if self._x_has_arc(i, j)
                    )
                    y_mid = sum(m.mega[j, days[r], c] for r in range(ei))
                    # Relax when any check occurs in [day_1 .. d_] (y_mid covers
                    # days[0]..days[ei-1]; mega[d_] covers the boundary itself).
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
            for i in m.FM:   # only flights arriving at MA have z vars
                fd   = self.flight_data[i]
                apt  = fd['destination']
                t_arr = fd['arrivalTime']
                d_i   = fd['day_arrival']
                for j in self._x_aircrafts_for_flight(i):
                    for i2 in self._f_dep_window(apt, t_arr, t_arr + dur):
                        if not self._x_has_arc(i2, j):
                            continue
                        # Block i2 for aircraft j when:
                        #   x[i,j]=1  (j flew into apt via flight i)
                        d = self.flight_data[i2]['day_departure']
                        if d !=d_i:
                            m.c15.add(m.mega[j, d, c] + m.x[i2, j] <= 1)

                        # m.c15.add(m.mega[j, d, c] + m.x[i2, j] <= 1)

                        logger.debug(f"Added C15 constraint: if flight {i} triggers check {c} for aircraft {j} on day {d_i}, then flight {i2} departing from {apt} within {dur} minutes is blocked.")
                        
                        

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
                        if not self._x_has_arc(i2, j2):
                            continue
                        m.c15.add(m.mega[j2, d0, c] + m.x[i2, j2] <= 1)
        
        # Note: Multi-day check blocking is already handled by C15a above,
        # which uses absolute departure times (_f_dep_window) spanning the
        # full check duration window across day boundaries.  A separate day-
        # level "C15b" constraint using y[j,d,c] (start-day only) is both
        # redundant and causes infeasibility with routing (C23), so it is omitted.

    # ------------------------------------------------------------------
    # Sanity: z[i,j,d,c]=0 when day d is after arrival day + check duration
    # ------------------------------------------------------------------

    def _add_sanity(self, m):
        m.c_sanity = ConstraintList()
        for c in self.CHECK_LIST:
            for i in m.FM:  # only maintenance-eligible flights
                arr_day = self.flight_data[i]['day_arrival']
                for j in m.P:
                    for d in self._z_days_for(i, c):
                        if d < arr_day:
                            m.c_sanity.add(m.z[i, j, d, c] == 0)

    # ------------------------------------------------------------------
    # Warm-start helpers
    # ------------------------------------------------------------------

    def warm_start_from_heuristic(self):
        """No-op: partial warm-start (x-only) causes CPLEX to reject the MIP
        start as infeasible.  Feasibility-first tuning is applied in solve()
        via solver.options instead.
        """
        pass

    # ------------------------------------------------------------------
    # Solve
    # ------------------------------------------------------------------

    def solve(self, solver_name='cplex', tee=False, out_path=None,
              time_limit=None, warm_start=False):
        """Invoke the solver on the built model.

        Parameters
        ----------
        solver_name : str
            Pyomo solver name ('cplex', 'cbc', 'glpk', …).
        tee : bool
            Stream solver log to stdout.
        out_path : str | None
            If given, write the text report to this file.
        time_limit : int | None
            Solver wall-clock time limit in seconds (None = no limit).

        Returns
        -------
        dict with keys: status, n_vars, n_cons, gap, cpu, obj
        """
        if self.model is None:
            raise RuntimeError("Call build_model() first.")

        if warm_start:
            self.warm_start_from_heuristic()

        solver_name = solver_name or os.environ.get('TAP_PYOMO_SOLVER', 'cplex_direct')
        solver = SolverFactory(solver_name)

        # --- solver-specific time-limit options ---
        _sn = solver_name.lower()
        _solve_kwargs = dict(tee=tee)
        if warm_start and _sn == 'cplex':
            # Skip root-node cut generation passes: the root LP already takes
            # ~265-408s for h=15+; cut generation further delays the first B&C
            # node.  Disable cuts so CPLEX branches immediately after root LP.
            solver.options['mip limits cutpasses'] = 0
        if time_limit is not None:
            if 'gurobi' in _sn:
                solver.options['TimeLimit'] = int(time_limit)
            elif 'cplex' in _sn:
                solver.options['timelimit'] = int(time_limit)
            elif 'cbc' in _sn:
                # Pyomo's CBCSHELL hard-codes '-sec' which AMPL-style CBC 2.10+
                # rejects; pass via timelimit kwarg (same underlying flag) and
                # fall back to no-limit if it still fails.
                _solve_kwargs['timelimit'] = int(time_limit)
            elif 'glpk' in _sn:
                solver.options['tmlim'] = int(time_limit)
            else:  # generic fallback (highs, scip, …)
                solver.options['TimeLimit'] = int(time_limit)

        try:
            self.results = solver.solve(self.model, **_solve_kwargs)
        except NoFeasibleSolutionError:
            self.results = solver.solve(
                self.model,
                load_solutions=False,
                **_solve_kwargs,
            )
        except Exception as _exc:
            # CBC with timelimit kwarg may raise when the selected binary or
            # wrapper cannot enforce the requested limit. Never re-solve
            # without a limit: fail fast to avoid silent unlimited runs.
            if 'cbc' in _sn and 'timelimit' in _solve_kwargs:
                raise RuntimeError(
                    "[CBC] Failed to enforce time_limit. "
                    "Aborting instead of re-solving without a limit. "
                    "Use a CBC binary/wrapper that supports time limits or "
                    "run without --time-limit if unlimited runtime is intended."
                ) from _exc
            else:
                raise

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

        if not summary or summary.get('status') != str(TerminationCondition.optimal):
            report = '\n'.join(lines)
            print(report)
            if out_path:
                with open(out_path, 'w', encoding='utf-8') as handle:
                    handle.write(report)
            return

        _p("\n--- Assignment ---")
        for i in m.F:
            for j in self._x_aircrafts_for_flight(i):
                if pyo_value(m.x[i, j]) > 0.5:
                    _p(f"  Flight {i:4d}  -> Aircraft {j}")

        _p("\n--- Maintenance ---")
        for j in m.P:
            for c in self.CHECK_LIST:
                for d in m.D:
                    val = pyo_value(m.y[j, d, c])
                    if val > 0.5:
                        for i in self._z_trigger_flights(d, c):
                            if pyo_value(m.z[i, j, d, c]) > 0.5:
                                _p(f"  Aircraft {j}  day {d:3d}  check {c} after flight:")
                                _p(f"{i} arr {self.flight_data[i]['arrivalTime']} ")
                                _p("\n")
                        for d1 in m.D:
                            for i1 in m.F:
                                if self.flight_data[i1]['origin'] != self.flight_data[i]['destination'] or self.flight_data[i1]['day_departure'] <= d:
                                    continue
                                if not self._x_has_arc(i1, j):
                                    continue
                                if pyo_value(m.x[i1, j]) > 0.5:
                                    _p(f"  Aircraft {j}  day {d:3d}  check {c} triggered by initial position, assigned flight:")
                                    _p(f"{i1} dep {self.flight_data[i1]['departureTime']} ")
                                    _p("\n")

        for j in m.P:
            for d in m.D:
                for c in self.CHECK_LIST:
                    if pyo_value(m.y[j, d, c]) > 0.5:
                        _p(f"y[{j},{d},{c}] = {pyo_value(m.y[j, d, c])}  (check {c} for aircraft {j} on day {d})")
                    for i in self._z_trigger_flights(d, c):
                        if pyo_value(m.z[i, j, d, c]) > 0.5:
                            _p(f"z[{i},{j},{d},{c}] = {pyo_value(m.z[i, j, d, c])}  (flight {i} triggers check {c} for aircraft {j} on day {d})")
              

        _p(f"\nTotal cost: {pyo_value(m.obj):.2f}")
        text = "\n".join(lines)
        print(text)
        if out_path:
            with open(out_path, 'w', encoding='utf-8') as f:
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
                if not self._x_has_arc(i, j):
                    continue
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
                        'origin':   fd.get('origin', ''),
                        'destination': fd.get('destination', ''),
                    })
            for d in m.D:
                for c in self.CHECK_LIST:
                    if pyo_value(m.y[j, d, c]) > 0.5:
                        # Skip continuation days: only emit one event per
                        # maintenance block (the first day of the check).
                        # A multi-day check sets y[j,d,c]=1 for each day it
                        # spans; emitting one event per day produces duplicate
                        # entries with wrong start/end times for days > 1.
                        prev_d = d - 1
                        if prev_d in m.D and pyo_value(m.y[j, prev_d, c]) > 0.5:
                            continue  # continuation of an earlier block

                        # Find the trigger flight to get the actual start time.
                        # Only use the trigger flight's arrivalTime if it arrives
                        # on the same day d as the maintenance; otherwise fall back
                        # to the start of day d so the event sorts correctly.
                        t_start = (d - 1) * self.DAY_SHIFT
                        for i in self._z_trigger_flights(d, c):
                            if pyo_value(m.z[i, j, d, c]) > 0.5:
                                fd_trig = self.flight_data[i]
                                if fd_trig['day_arrival'] == d:
                                    t_start = fd_trig['arrivalTime']
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

    def plot_gantt(self, save_path=None, show=True, fname=None):
        """Render a Gantt chart from the solved model.

        Parameters
        ----------
        save_path : str | None  Path to save PNG; if None chart is not saved.
        show      : bool        Call plt.show() when True.
        fname     : str | None  Path to save event details; if None details are not saved.
        """
        events    = self.get_events()
        aid_list  = sorted(self.aircraft_ids)
        _plot_gantt(events, aid_list, unassigned_ids=[], save_path=save_path,
                    show=show, title='MILP Aircraft Schedule', fname=fname)


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
                flights_dict=None, save_path=None, show=True, title='Fleet Schedule', fname=None):
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
    if not PLOTTING_AVAILABLE:
        if fname is not None:
            with open(fname, 'w', encoding='utf-8') as fh:
                fh.write('Plotting unavailable in this environment.\n')
        if save_path:
            print(f"Skipping Gantt plot (matplotlib unavailable): {save_path}")
        return

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

    # Write per-aircraft timeline text report
    if fname is not None:
        from collections import defaultdict
        _CHECK_TYPES = ('A', 'B', 'C', 'D')
        by_ac = defaultdict(list)
        for e in events:
            by_ac[e['aircraft']].append(e)
        lines = []
        for aid in aid_list:
            ac_events = sorted(by_ac.get(aid, []), key=lambda e: e['start'])
            if not ac_events:
                continue
            lines.append(f'Aircraft {aid}:')
            for e in ac_events:
                day = e.get('day', '')
                if e['type'] == 'FLIGHT':
                    orig = e.get('origin', '')
                    dest = e.get('destination', '')
                    lines.append(f'  Flight  {e["label"]:6s}  {orig} -> {dest}  day {day}   start {e["start"]:7.1f} - end {e["end"]:7.1f}')
                else:
                    lines.append(f'  Maint   {e["label"]:6s}  day {day}   start {e["start"]:7.1f} - end {e["end"]:7.1f}')

            # --- Per-check-type maintenance statistics ---
            check_types_present = sorted(
                {e.get('check') for e in ac_events if e.get('check') in _CHECK_TYPES}
            )
            if not check_types_present:
                total_flight_mins = sum(
                    e['end'] - e['start'] for e in ac_events if e['type'] == 'FLIGHT'
                )
                lines.append(f'  No maintenance scheduled  |  total flight mins = {total_flight_mins:.1f}')
            else:
                lines.append('  Maintenance statistics:')
                for c in check_types_present:
                    maint_c = sorted(
                        [e for e in ac_events if e.get('check') == c],
                        key=lambda e: e['start'],
                    )
                    if not maint_c:
                        continue
                    prev_end = 0.0
                    parts = []
                    for idx, mev in enumerate(maint_c, 1):
                        # Flight minutes of FLIGHT events strictly within [prev_end, mev.start]
                        flight_mins = sum(
                            min(fe['end'], mev['start']) - max(fe['start'], prev_end)
                            for fe in ac_events
                            if fe['type'] == 'FLIGHT'
                            and fe['start'] < mev['start']
                            and fe['end'] > prev_end
                        )
                        cum_days = (mev['start'] - prev_end) / 1440.0
                        parts.append(
                            f'#{idx}: flight mins before = {flight_mins:7.1f}  '
                            f'cum days before = {cum_days:6.2f}'
                        )
                        prev_end = mev['end']
                    lines.append(f'    Check {c}:  ' + '   |   '.join(parts))

            lines.append('')
        with open(fname, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines))

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

    if mpatches is not None:
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
# RESULT HELPERS
# ----------------------------

def _heuristic_events(sc, final_ac_fids):
    """Extract Gantt-compatible event list from a Scheduler result."""
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
    return events


def _heuristic_df(sc, final_ac_fids):
    """Build a summary DataFrame from a Scheduler result."""
    rows = []
    for aid in sorted(sc.aircrafts):
        res = sc.get_timeline(aid, final_ac_fids[aid])
        if res:
            for e in res['events']:
                label = f"F{e['fid']}" if e['kind'] == 'FLIGHT' else e.get('check', 'FERRY')
                rows.append([
                    aid, e['kind'], label, e.get('orig','-'), e.get('dest','-'),
                    round(e['start'], 1),
                    round(e.get('dur', e['end']-e['start']), 1),
                    round(e.get('rem_a', float('nan')), 1),
                    round(e.get('rem_b', float('nan')), 1),
                    round(e.get('rem_c', float('nan')), 3),
                    round(e.get('rem_d', float('nan')), 3),
                ])
    return pd.DataFrame(rows, columns=[
        'AID','Type','ID','From','To','Dep(min)','Dur(min)',
        'Rem_A(min)','Rem_B(min)','Rem_C(days)','Rem_D(days)'
    ])


def run_heuristic(data_path='data18h.json', csv_path='final_schedule.csv',
                  gantt_path=None, show_gantt=True, verbose=True,
                  allow_ferry=True, heuristic='greedy+insertion'):
    """Run a heuristic strategy and display results."""
    sc = Scheduler(data_path, allow_ferry=allow_ferry, heuristic=heuristic)
    final_ac_fids, unassigned = sc.optimize()

    n_flights  = len(sc.flights)
    n_assigned = n_flights - len(unassigned)

    if verbose:
        max_horizon = max(f['arr'] for f in sc.flights.values())
        print(f"\n--- Aircraft Utilization Summary  [{data_path}] ---")
        for aid in sorted(sc.aircrafts):
            res = sc.get_timeline(aid, final_ac_fids[aid])
            if res:
                busy = sum(e['end'] - e['start'] for e in res['events'])
                print(f"  AC {aid:3d}: busy {busy:7.0f} min  free {max_horizon - busy:7.0f} min  "
                      f"flights {len(final_ac_fids[aid])}")
            else:
                print(f"  AC {aid:3d}: no flights assigned")
        print(f"  Assigned {n_assigned}/{n_flights}  |  Unassigned {len(unassigned)}")
        print("------------------------------------")

    df = _heuristic_df(sc, final_ac_fids)
    if verbose:
        print(df.to_string())
    if csv_path:
        df.to_csv(csv_path, index=False)
        if verbose:
            print(f"\nTable saved -> {csv_path}")

    events = _heuristic_events(sc, final_ac_fids)
    _plot_gantt(events, sorted(sc.aircrafts),
                unassigned_ids=unassigned, flights_dict=sc.flights,
                save_path=gantt_path, show=show_gantt,
                title=f"Heuristic  {data_path}  (assigned {n_assigned}/{n_flights})", fname=f'{csv_path[:-4]}_events.txt' if csv_path else None)

    return sc, final_ac_fids, unassigned


def run_milp(data_path='data18h.json', solver='cplex', tee=False,
             time_limit=None,
             out_txt=None, gantt_path=None, show_gantt=True,
             use_day_spacing=True, use_existing_hrs=True,
             use_check_hierarchy=True, use_sanity=False, use_overlap=True,
             allow_ferry=True, use_maintenance=True, warm_start=True,
             max_hour_check_deferral_days=None, enabled_checks=None,
             use_paper_c13=False, use_strong_maint_link=False,
             soft_coverage=False,
             coverage_weight=1_000_000.0):
    """Build and solve the MILP model, then display results.

    Parameters
    ----------
    time_limit     : int | None  Solver wall-clock time limit in seconds.
    allow_ferry    : bool        When False, C2-C3 routing constraints omitted.
    use_maintenance: bool        When False, all maintenance constraints omitted
                                 (pure flight-assignment relaxation).
    warm_start     : bool        When True (default), seed MILP x-variables with
                                 the greedy heuristic solution before solving.
    enabled_checks : list[str] | None
        Active maintenance check types to model (subset of A,B,C,D).
        None keeps all four checks active.
    use_paper_c13  : bool        When True, use the original (buggy) Khaled
                                 et al. (2018) Constraint (13) instead of the
                                 corrected split formulation.
    use_strong_maint_link : bool When True, use the strengthened sparse
                                 trigger-to-assignment link for all checks.
    soft_coverage  : bool        When True, permit unassigned flights and
                                 maximize coverage before minimizing cost.
    """
    opt = MILP_Sheduler(
        data_path,
        max_hour_check_deferral_days=max_hour_check_deferral_days,
        enabled_checks=enabled_checks,
    )
    opt.build_model(use_day_spacing=use_day_spacing,
                    use_existing_hrs=use_existing_hrs,
                    use_check_hierarchy=use_check_hierarchy,
                    use_sanity=use_sanity,
                    use_overlap=use_overlap,
                    allow_ferry=allow_ferry,
                    use_maintenance=use_maintenance,
                    use_strong_maint_link=use_strong_maint_link,
                    use_paper_c13=use_paper_c13,
                    soft_coverage=soft_coverage,
                    coverage_weight=coverage_weight)
    summary = opt.solve(solver_name=solver, tee=tee, out_path=out_txt,
                        time_limit=time_limit, warm_start=warm_start)
    opt.plot_gantt(save_path=gantt_path, show=show_gantt, fname=f'{out_txt[:-4]}_events.txt' if out_txt else None)
    return opt, summary


# ----------------------------
# BATCH RUNNER
# ----------------------------

def _run_one_heuristic(fp, out_dir, stem, show_gantt, allow_ferry=True,
                       heuristic='greedy+insertion'):
    """Run heuristic on a single file; return metrics dict."""
    import time, os
    csv_out   = os.path.join(out_dir, f'{stem}_heu_schedule.csv')
    gantt_out = os.path.join(out_dir, f'{stem}_heu_gantt.png')
    txt_out   = os.path.join(out_dir, f'{stem}_heu_summary.txt')
    t0 = time.time()
    sc, ac_fids, unassigned = run_heuristic(
        data_path=fp, csv_path=csv_out,
        gantt_path=gantt_out, show_gantt=show_gantt, verbose=False,
        allow_ferry=allow_ferry, heuristic=heuristic,
    )
    cpu = time.time() - t0
    n   = len(sc.flights)
    na  = n - len(unassigned)

    # Cost = sum of assignment costs in solution
    total_cost = sum(
        sc.get_timeline(aid, ac_fids[aid])['cost']
        for aid in sc.aircrafts
        if sc.get_timeline(aid, ac_fids[aid])
    )

    max_h = max(f['arr'] for f in sc.flights.values())
    lines = [f"Dataset : {fp}", f"Mode    : heuristic",
             f"Flights : {na}/{n} assigned  ({len(unassigned)} unassigned)",
             f"Cost    : {total_cost:.0f}",
             f"CPU     : {cpu:.1f}s", "",
             f"{'AID':>5}  {'Flt':>5}  {'Busy(min)':>10}  {'Free(min)':>10}"]
    for aid in sorted(sc.aircrafts):
        res = sc.get_timeline(aid, ac_fids[aid])
        if res:
            busy = sum(e['end'] - e['start'] for e in res['events'])
            lines.append(f"{aid:>5}  {len(ac_fids[aid]):>5}  {busy:>10.0f}  {max_h-busy:>10.0f}")
        else:
            lines.append(f"{aid:>5}  {'0':>5}  {'0':>10}  {max_h:>10.0f}")
    with open(txt_out, 'w') as fh:
        fh.write('\n'.join(lines))

    print(f"    [heu] assigned {na}/{n}  cost {total_cost:.0f}  cpu {cpu:.1f}s")
    print(f"          csv->{csv_out}  png->{gantt_out}")
    return {
        'stem': stem, 'mode': 'heuristic',
        'flights': n, 'assigned': na, 'unassigned': n - na,
        'cost': round(total_cost, 2), 'obj': round(total_cost, 2),
        'gap_%': None, 'status': 'heuristic', 'cpu_s': round(cpu, 2),
    }


def _run_one_milp(fp, out_dir, stem, solver, tee, show_gantt, time_limit,
                  allow_ferry=True, use_maintenance=True,
                  use_overlap=True, use_sanity=False, warm_start=True,
                  use_check_hierarchy=True, max_hour_check_deferral_days=None,
                  enabled_checks=None, use_paper_c13=False,
                  use_strong_maint_link=False):
    """Run MILP on a single file; return metrics dict."""
    import time, os
    gantt_out = os.path.join(out_dir, f'{stem}_milp_gantt.png')
    txt_out   = os.path.join(out_dir, f'{stem}_milp_summary.txt')
    t0 = time.time()
    opt, info = run_milp(
        data_path=fp, solver=solver, tee=tee,
        time_limit=time_limit,
        out_txt=txt_out, gantt_path=gantt_out, show_gantt=show_gantt,
        allow_ferry=allow_ferry,
        use_maintenance=use_maintenance,
        use_overlap=use_overlap,
        use_sanity=use_sanity,
        warm_start=warm_start,
        use_check_hierarchy=use_check_hierarchy,
        max_hour_check_deferral_days=max_hour_check_deferral_days,
        enabled_checks=enabled_checks,
        use_paper_c13=use_paper_c13,
        use_strong_maint_link=use_strong_maint_link,
    )
    cpu = time.time() - t0

    # Count assigned flights from model
    m = opt.model
    n_assigned = sum(
        1 for i in m.F for j in opt._x_aircrafts_for_flight(i)
        if pyo_value(m.x[i, j]) > 0.5
    )
    n_total    = len(list(m.F))

    print(f"    [milp] status={info.get('status')}  obj={info.get('obj')}  "
          f"gap={f"{info['gap']*100:.2f}%" if info.get('gap') else '-'}  cpu={cpu:.1f}s")
    print(f"          png->{gantt_out}")
    return {
        'stem': stem, 'mode': 'milp',
        'flights': n_total, 'assigned': n_assigned, 'unassigned': n_total - n_assigned,
        'cost': round(info.get('obj') or 0, 2), 'obj': round(info.get('obj') or 0, 2),
        'gap_%': round(info['gap'] * 100, 4) if info.get('gap') else None,
        'status': info.get('status'), 'cpu_s': round(cpu, 2),
    }


def _plot_comparison(rows, out_dir):
    """Bar-chart comparison of heuristic vs MILP across all datasets."""
    import os
    import numpy as np

    if not PLOTTING_AVAILABLE:
        print("[batch] Skipping comparison chart (matplotlib unavailable)")
        return

    df = pd.DataFrame(rows)
    if df.empty or 'mode' not in df.columns:
        return

    heu  = df[df['mode'] == 'heuristic'].set_index('stem')
    milp = df[df['mode'] == 'milp'].set_index('stem')
    stems = sorted(set(df['stem']))

    if heu.empty or milp.empty:
        return

    x   = np.arange(len(stems))
    w   = 0.35
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle('Heuristic vs MILP – Batch Comparison', fontsize=13, fontweight='bold')

    def _bar(ax, col, title, ylabel, fmt='{:.0f}'):
        hvals = [heu.loc[s, col] if s in heu.index else 0 for s in stems]
        mvals = [milp.loc[s, col] if s in milp.index else 0 for s in stems]
        bars1 = ax.bar(x - w/2, hvals, w, label='Heuristic', color='#3498db')
        bars2 = ax.bar(x + w/2, mvals, w, label='MILP',      color='#e74c3c')
        for b, v in zip(bars1, hvals):
            if v:
                ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.01*max(hvals+mvals),
                        fmt.format(v), ha='center', va='bottom', fontsize=8)
        for b, v in zip(bars2, mvals):
            if v:
                ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.01*max(hvals+mvals),
                        fmt.format(v), ha='center', va='bottom', fontsize=8)
        ax.set_title(title); ax.set_ylabel(ylabel)
        ax.set_xticks(x); ax.set_xticklabels([s[-20:] for s in stems], rotation=20, ha='right')
        ax.legend()

    _bar(axes[0], 'assigned', 'Flights Assigned',     'Count')
    _bar(axes[1], 'obj',      'Objective / Cost',     'Cost',   fmt='{:.0f}')
    _bar(axes[2], 'cpu_s',    'Computation Time (s)', 'Seconds', fmt='{:.1f}')

    plt.tight_layout()
    cmp_path = os.path.join(out_dir, '_comparison.png')
    plt.savefig(cmp_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"\n[batch] Comparison chart -> {cmp_path}")


def run_batch(input_dir='Inputs', output_dir='Outputs', mode='both',
              solver='cplex', tee=False, show_gantt=False, time_limit=300,
              allow_ferry=True, heuristic='greedy+insertion',
              use_maintenance=True,
              use_overlap=True, use_sanity=False, warm_start=True,
              use_check_hierarchy=True, max_hour_check_deferral_days=None,
              enabled_checks=None, use_paper_c13=False,
              use_strong_maint_link=False):
    """Process every JSON file in *input_dir* and write results to *output_dir*.

    For each dataset the following files are created in output_dir::

      <stem>_heu_schedule.csv   – heuristic event table
      <stem>_heu_gantt.png      – heuristic Gantt chart
      <stem>_heu_summary.txt    – heuristic utilisation report
      <stem>_milp_gantt.png     – MILP Gantt chart  (when mode includes milp)
      <stem>_milp_summary.txt   – MILP solver report
      _batch_summary.csv        – master metrics table (all files × modes)
      _comparison.png           – side-by-side bar chart (when mode='both')

    Parameters
    ----------
    input_dir      : str   Folder containing *.json data files.
    output_dir     : str   Destination folder (created if absent).
    mode           : str   'heuristic', 'milp', or 'both'.
    solver         : str   Pyomo solver name  (default: 'cplex').
    tee            : bool  Stream solver stdout.
    show_gantt     : bool  Pop up interactive Gantt windows.
    time_limit     : int   Solver time-limit in seconds (default: 300).
    allow_ferry    : bool  When False, C2-C3 routing constraints omitted.
    use_maintenance: bool  When False, all maintenance constraints omitted
                           (pure flight-assignment relaxation; much smaller model).
    use_overlap    : bool  When False, pairwise overlap constraints (c_overlap) omitted.
    use_sanity     : bool  When False, sanity-fixing bounds constraints omitted.
    use_check_hierarchy: bool  When False, check hierarchy constraints omitted. 
    enabled_checks : list[str] | None
        Active maintenance check types to model (subset of A,B,C,D).
    """
    import os, glob, time

    os.makedirs(output_dir, exist_ok=True)
    json_files = sorted(glob.glob(os.path.join(input_dir, '*.json')))
    if not json_files:
        print(f"[batch] No JSON files found in '{input_dir}'"); return

    run_heu  = mode in ('heuristic', 'both')
    run_milp_ = mode in ('milp', 'both')

    ferry_label = "ON" if allow_ferry else "OFF"
    maint_label = "ON" if use_maintenance else "OFF"
    over_label  = "ON" if use_overlap else "OFF"
    san_label   = "ON" if use_sanity  else "OFF"
    check_label = "ON" if use_check_hierarchy else "OFF"
    print(f"[batch] {len(json_files)} file(s) in '{input_dir}'")
    print(f"[batch] mode={mode}  solver={solver}  time_limit={time_limit}s")
    print(f"[batch] ferry={ferry_label}  maintenance={maint_label}  overlap={over_label}  sanity={san_label}  check_hierarchy={check_label}")
    if max_hour_check_deferral_days is not None:
        print(f"[batch] max_hour_check_deferral_days={max_hour_check_deferral_days}")
    if enabled_checks is not None:
        print(f"[batch] enabled_checks={','.join(enabled_checks)}")
    print(f"[batch] output -> '{output_dir}'\n")

    all_rows = []

    for fp in json_files:
        stem = os.path.splitext(os.path.basename(fp))[0]
        print(f"\n{'─'*60}")
        print(f"  ▶  {stem}")

        if run_heu:
            try:
                row = _run_one_heuristic(fp, output_dir, stem, show_gantt,
                                         allow_ferry=allow_ferry,
                                         heuristic=heuristic)
                all_rows.append(row)
            except Exception as exc:
                print(f"  ✗ [heuristic] {exc}")
                import traceback; traceback.print_exc()

        if run_milp_:
            try:
                row = _run_one_milp(fp, output_dir, stem, solver, tee,
                                    show_gantt, time_limit,
                                    allow_ferry=allow_ferry,
                                    use_maintenance=use_maintenance,
                                    use_overlap=use_overlap,
                                    use_sanity=use_sanity,
                                    warm_start=warm_start,
                                    use_check_hierarchy=use_check_hierarchy,
                                    max_hour_check_deferral_days=max_hour_check_deferral_days,
                                    enabled_checks=enabled_checks,
                                    use_paper_c13=use_paper_c13,
                                    use_strong_maint_link=use_strong_maint_link,
                                    )
                all_rows.append(row)
            except Exception as exc:
                print(f"  ✗ [milp] {exc}")
                import traceback; traceback.print_exc()

    print(f"\n{'─'*60}")

    # Master summary CSV
    if all_rows:
        master = pd.DataFrame(all_rows)
        master_path = os.path.join(output_dir, '_batch_summary.csv')
        master.to_csv(master_path, index=False)
        print(f"[batch] Master summary -> {master_path}")
        # Pretty console table
        disp_cols = ['stem','mode','flights','assigned','unassigned','obj','gap_%','cpu_s']
        disp = master[[c for c in disp_cols if c in master.columns]]
        print(disp.to_string(index=False))

        # Comparison chart (only when both modes ran)
        if mode == 'both':
            _plot_comparison(all_rows, output_dir)

    return all_rows


# ----------------------------
# UNIFIED MAIN
# ----------------------------

def main():
    """Entry point.  Examples::

        # single file – heuristic (default)
        py -3 heu180h.py --data data18h.json

        # single file – MILP
        py -3 heu180h.py --mode milp --data data18h.json --solver cplex --tee

        # batch folder run – heuristic
        py -3 heu180h.py --mode batch --input-dir Inputs --output-dir Outputs

        # batch folder run – MILP
        py -3 heu180h.py --mode batch --input-dir Inputs --output-dir Outputs \\
                          --solver cplex
    """
    import argparse

    def _parse_check_tokens(tokens):
        checks = []
        for token in tokens or []:
            for part in str(token).split(','):
                check = part.strip().upper()
                if check:
                    checks.append(check)
        return checks

    def _resolve_enabled_checks(only_tokens, disable_tokens):
        base = ['A', 'B', 'C', 'D']
        only_checks = _parse_check_tokens(only_tokens)
        disable_checks = _parse_check_tokens(disable_tokens)

        invalid = [c for c in only_checks + disable_checks if c not in base]
        if invalid:
            parser.error(
                f"Invalid check type(s): {sorted(set(invalid))}. Allowed: A,B,C,D."
            )

        enabled = base if not only_checks else [c for c in base if c in only_checks]
        if disable_checks:
            disabled = set(disable_checks)
            enabled = [c for c in enabled if c not in disabled]

        if not enabled:
            parser.error(
                "Selected checks are empty after applying --only-checks/--disable-checks."
            )
        return enabled

    parser = argparse.ArgumentParser(
        description='Aircraft Schedule Optimizer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  py -3 heu180h.py                                          # heuristic on data18h.json\n"
            "  py -3 heu180h.py --mode milp --solver cplex_direct --tee  # MILP single file\n"
            "  py -3 heu180h.py --mode batch --input-dir Inputs          # heuristic batch\n"
            "  py -3 heu180h.py --mode batch --batch-mode both --solver cplex_direct  # both + compare\n"
        )
    )
    parser.add_argument('--mode',        default='heuristic',
                        choices=['heuristic', 'milp', 'batch'],
                        help='Run mode (default: heuristic)')
    parser.add_argument('--batch-mode',  default='both',
                        choices=['heuristic', 'milp', 'both'],
                        help='Which optimizers to run in batch (default: both)')
    parser.add_argument('--data',        default='data18h.json',
                        help='JSON data file  (single-file modes)')
    parser.add_argument('--input-dir',   default='Inputs',
                        help='Input folder for batch mode  (default: Inputs)')
    parser.add_argument('--output-dir',  default='Outputs',
                        help='Output folder for batch mode  (default: Outputs)')
    parser.add_argument('--solver',      default=os.environ.get('TAP_PYOMO_SOLVER', 'cplex_direct'),
                        help='Pyomo solver name  (default: TAP_PYOMO_SOLVER or cplex_direct)')
    parser.add_argument('--time-limit',  type=int, default=300,
                        help='Solver time limit in seconds for MILP  (default: 300)')
    parser.add_argument('--tee',         action='store_true',
                        help='Stream solver log to stdout  (MILP modes)')
    parser.add_argument('--out',         default=None,
                        help='Output path: CSV for heuristic, TXT for MILP')
    parser.add_argument('--gantt',       default=None,
                        help='Save Gantt chart PNG to this path')
    parser.add_argument('--no-show',     dest='show', action='store_false',
                        help='Do not display Gantt interactively')
    parser.add_argument('--heuristic', default='greedy+insertion',
                        choices=['greedy', 'insertion', 'greedy+insertion', 'repair', 'local_search', 'dijkstra', 'aco'],
                        help='Heuristic strategy to use in heuristic and batch modes '
                             '(default: greedy+insertion).')
    parser.add_argument('--no-ferry',    dest='allow_ferry', action='store_false',
                        help='Disable repositioning (ferry) legs in heuristic and MILP modes.')
    parser.add_argument('--no-maintenance', dest='use_maintenance', action='store_false',
                        help='Omit ALL maintenance constraints from MILP '
                             '(pure flight-assignment relaxation; much smaller/faster).')
    parser.add_argument('--soft-coverage', action='store_true',
                        help='Allow unassigned flights and maximize assigned-flight coverage first.')
    parser.add_argument('--coverage-weight', type=float, default=1_000_000.0,
                        help='Coverage priority weight for --soft-coverage.')
    parser.add_argument('--no-overlap',  dest='use_overlap', action='store_false',
                        help='Omit pairwise time-overlap constraints (c_overlap) from MILP.')
    parser.add_argument('--no-sanity',   dest='use_sanity', action='store_false',
                        help='Omit sanity-fixing bound constraints from MILP.')
    parser.add_argument('--no-warm-start', dest='warm_start', action='store_false',
                        help='Do not seed MILP with heuristic solution (warm start OFF).')
    parser.add_argument('--no-check-hierarchy', dest='use_check_hierarchy', action='store_false',
                        help='Omit check hierarchy constraints from MILP.')
    parser.add_argument('--max-hour-check-deferral-days', type=int, default=None,
                        help='Cap how many days after arrival an A/B check may be deferred. '
                             'Use 0 for same-day only; default keeps the full horizon.')
    parser.add_argument('--only-checks', nargs='+', default=None,
                        metavar='CHECK',
                        help='Enable only selected maintenance check types (A B C D). '
                             'Comma-separated values are also accepted.')
    parser.add_argument('--disable-checks', nargs='+', default=None,
                        metavar='CHECK',
                        help='Disable selected maintenance check types (A B C D). '
                             'Comma-separated values are also accepted.')
    parser.add_argument('--use-paper-c13', dest='use_paper_c13', action='store_true',
                        help='Use the original (buggy) Khaled et al. (2018) Constraint (13) '
                             'instead of the corrected split formulation.')
    parser.add_argument('--strong-maint-link', dest='use_strong_maint_link',
                        action='store_true',
                        help='Enable strengthened sparse trigger-to-assignment '
                            'linking for all maintenance check types.')
    parser.set_defaults(show=True, allow_ferry=True, use_maintenance=True,
                        use_overlap=True, use_sanity=False, warm_start=True,
                        use_check_hierarchy=True, use_paper_c13=False,
                        use_strong_maint_link=False)
    args = parser.parse_args()
    enabled_checks = _resolve_enabled_checks(args.only_checks, args.disable_checks)

    if args.mode == 'heuristic':
        sc, ac_fids, unassigned = run_heuristic(
                      data_path=args.data,
                      csv_path=args.out or 'final_schedule.csv',
                      gantt_path=args.gantt,
                      show_gantt=args.show,
                      allow_ferry=args.allow_ferry,
                      heuristic=args.heuristic)
        n = len(sc.flights)
        na = n - len(unassigned)
        total_cost = sum(
            sc.get_timeline(aid, ac_fids[aid])['cost']
            for aid in sc.aircrafts if sc.get_timeline(aid, ac_fids[aid])
        )
        # parseable summary for run_batch.py
        print("Status  : heuristic")
        print(f"Flights : {na}/{n} assigned")
        print(f"Obj     : {total_cost:.0f}")
    elif args.mode == 'milp':
        run_milp(data_path=args.data,
                 solver=args.solver, tee=args.tee,
                 time_limit=args.time_limit,
                 out_txt=args.out, gantt_path=args.gantt, show_gantt=args.show,
                 allow_ferry=args.allow_ferry,
                 use_maintenance=args.use_maintenance,
                 use_overlap=args.use_overlap,
                 use_sanity=args.use_sanity,
                 warm_start=args.warm_start,
                 use_check_hierarchy=args.use_check_hierarchy,
                 max_hour_check_deferral_days=args.max_hour_check_deferral_days,
                 enabled_checks=enabled_checks,
                 use_paper_c13=args.use_paper_c13,
                 use_strong_maint_link=args.use_strong_maint_link,
                 soft_coverage=args.soft_coverage,
                 coverage_weight=args.coverage_weight,
                 )
    else:  # batch
        run_batch(input_dir=args.input_dir,
                  output_dir=args.output_dir,
                  mode=args.batch_mode,
                  solver=args.solver, tee=args.tee,
                  heuristic=args.heuristic,
                  time_limit=args.time_limit,
                  show_gantt=args.show,
                  allow_ferry=args.allow_ferry,
                  use_maintenance=args.use_maintenance,
                  use_overlap=args.use_overlap,
                  use_sanity=args.use_sanity,
                  warm_start=args.warm_start,
                  use_check_hierarchy=args.use_check_hierarchy,
                  max_hour_check_deferral_days=args.max_hour_check_deferral_days,
                  enabled_checks=enabled_checks,
                  use_paper_c13=args.use_paper_c13,
                  use_strong_maint_link=args.use_strong_maint_link,
                  )
        


if __name__ == '__main__':
    main()
