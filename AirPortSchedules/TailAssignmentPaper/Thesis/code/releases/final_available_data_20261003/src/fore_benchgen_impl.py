"""fore-benchgen v2 — fleet maintenance benchmark generator.

Adds to v1:
  * a strengthened validator that checks maintenance THRESHOLD COMPLIANCE
    (v1 certified flow, overlap and capacity but never checked that a tail
    stayed below its check limits, so a PASS was not a feasibility proof);
  * a metrics module measuring instance/solution complexity across four
    families plus a composite index;
  * a feasibility-preserving Metropolis perturbation that random-walks the
    space of feasible schedules to destroy the trivial block structure;
  * an optional factor/copula cost model (feasibility-neutral) replacing the
    i.i.d. noise that made the cost matrix uninformative.
"""
from __future__ import annotations
import argparse, csv, hashlib, itertools, json, math, random, sys, zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

VERSION = "2.0.0"
CHECKS = ("A", "B", "C", "D")
THRESHOLDS = {"A": 27000, "B": 90000, "C": 600, "D": 3000}
DURATIONS = {"A": 360, "B": 720, "C": 10080, "D": 60480}
DAY = 1440
# Two legs may be connected if the ground time is at least the minimum turn and
# at most this window; longer gaps are overnight rests, not connections.
MAX_CONNECT_MINUTES = 720


@dataclass
class Config:
    family: str = "small"
    fleet_size: int = 8
    n_stations: int = 12
    horizon_days: int = 60
    legs_per_tail_day: float = 2.0
    capable_fraction: float = 0.4
    usage_tightness: float = 0.6
    cost_dispersion: float = 0.15
    min_turn_minutes: int = 45
    root_seed: int = 20260814
    # v2 additions
    cost_model: str = "iid"          # "iid" (v1 behaviour) or "factor"
    cost_factor_rho: float = 0.7     # correlation strength for the factor model
    cost_tie_band: float = 0.02      # fraction of legs forced into near-ties
    # v1 sized its maintenance lookahead on a NOMINAL 120-minute block while
    # actual blocks run to 150, so a day of long legs could overshoot a
    # threshold (reproducible on stress_synchronised, tail 2, day 71). True
    # uses the worst-case block; set False to reproduce v1 byte-for-byte.
    safe_lookahead: bool = True
    # "out_and_back" reproduces v1: every tail flies home->away->home, so its
    # route is a star centred on its base and no two tails are ever on the
    # ground together away from base -- mid-day exchanges are geometrically
    # impossible and the routing is pre-solved. "tours" instead routes every
    # tail through a SHARED daily station pool on a closed walk that returns
    # to base, so flow continuity still holds by construction (a closed walk
    # is balanced in the Eulerian sense) while aircraft genuinely meet.
    # "out_and_back" is v1: a star per tail, no repositioning, pre-solved.
    # "tours" adds shared intermediate stations but still parks every tail back
    # at its own base each night, so the fleet never mixes.
    # "euler" builds each day's arc set as a union of CLOSED CYCLES through the
    # bases of a group of tails, then cuts each cycle at its base visits and
    # hands one open walk to each tail. The day's digraph is balanced by
    # construction - every node has equal in- and out-degree - so by Euler's
    # theorem it decomposes into closed walks, which is verified with
    # Hierholzer rather than assumed. Aircraft swap bases overnight, which is
    # what finally lets two tails be in the same place at the same time.
    route_topology: str = "out_and_back"
    euler_group_size: int = 3      # tails per rotation cycle in "euler" mode
    bank_slot_minutes: int = 190   # departure grid spacing in "tours" mode
    # "legacy" keeps v1's limits, under which C (600 days) and D (3000 days)
    # exceed every preset horizon and can never fire. "coprime" rescales all
    # four limits to PAIRWISE-COPRIME day periods shorter than the horizon, so
    # every check type fires and - because the periods share no common factor -
    # the reset epochs of different checks never fall into a common rhythm.
    threshold_mode: str = "legacy"
    maintenance_lead_days: int = 4   # how early a check may be pulled forward
    application_compatible: bool = False

    def validate(self):
        if self.fleet_size < 1: raise ValueError("fleet_size must be positive")
        if self.n_stations < 3: raise ValueError("n_stations must be >= 3")
        if self.horizon_days < 1: raise ValueError("horizon_days must be positive")
        if not 0 < self.capable_fraction <= 1:
            raise ValueError("capable_fraction must be in (0,1]")
        if not 0 <= self.usage_tightness < 1:
            raise ValueError("usage_tightness must be in [0,1)")
        if self.legs_per_tail_day <= 0:
            raise ValueError("legs_per_tail_day must be positive")
        if self.cost_model not in ("iid", "factor"):
            raise ValueError("cost_model must be 'iid' or 'factor'")
        if not 0 <= self.cost_factor_rho < 1:
            raise ValueError("cost_factor_rho must be in [0,1)")
        if self.route_topology not in ("out_and_back", "tours", "euler"):
            raise ValueError(
                "route_topology must be 'out_and_back', 'tours' or 'euler'")
        if self.euler_group_size < 1:
            raise ValueError("euler_group_size must be positive")
        if self.threshold_mode not in ("legacy", "coprime"):
            raise ValueError("threshold_mode must be 'legacy' or 'coprime'")
        if self.maintenance_lead_days < 0:
            raise ValueError("maintenance_lead_days must be non-negative")
        return self


PRESETS = {
 "validation": dict(family="validation", fleet_size=3, n_stations=6,
                    horizon_days=30, legs_per_tail_day=2, usage_tightness=.9),
 "small": dict(family="small", fleet_size=8, n_stations=12,
               horizon_days=60, legs_per_tail_day=2),
 "sma1": dict(family="sma1", fleet_size=8, n_stations=12,
               horizon_days=8, legs_per_tail_day=2),
 "sma2": dict(family="sma2", fleet_size=8, n_stations=12,
               horizon_days=21, legs_per_tail_day=2),
 "sma3": dict(family="sma3", fleet_size=8, n_stations=12,
               horizon_days=35, legs_per_tail_day=2),
 "sma4": dict(family="sma4", fleet_size=8, n_stations=12,
               horizon_days=60, legs_per_tail_day=2),
 "sma5": dict(family="sma5", fleet_size=8, n_stations=12,
               horizon_days=120, legs_per_tail_day=2),
 "sma6": dict(family="sma6", fleet_size=8, n_stations=12,
               horizon_days=180, legs_per_tail_day=2),
 "medium": dict(family="medium", fleet_size=20, n_stations=21,
                horizon_days=180, legs_per_tail_day=2),
 "med1": dict(family="med1", fleet_size=20, n_stations=19,
                horizon_days=8, legs_per_tail_day=2),
 "med2": dict(family="med2", fleet_size=20, n_stations=19,
                horizon_days=21, legs_per_tail_day=2),
 "med3": dict(family="med3", fleet_size=20, n_stations=19,
                horizon_days=35, legs_per_tail_day=2),
 "med4": dict(family="med4", fleet_size=20, n_stations=19,
                horizon_days=60, legs_per_tail_day=2),
 "med5": dict(family="med5", fleet_size=20, n_stations=19,
                horizon_days=120, legs_per_tail_day=2),
 "med6": dict(family="med6", fleet_size=20, n_stations=19,
                horizon_days=180, legs_per_tail_day=2),
 "large": dict(family="large", fleet_size=60, n_stations=40,
               horizon_days=180, legs_per_tail_day=2),
 "lge1": dict(family="lge1", fleet_size=60, n_stations=40,
               horizon_days=8, legs_per_tail_day=2),
 "lge2": dict(family="lge1", fleet_size=60, n_stations=40,
               horizon_days=21, legs_per_tail_day=2),
 "lge3": dict(family="lge1", fleet_size=60, n_stations=40,
               horizon_days=35, legs_per_tail_day=2),
 "lge4": dict(family="lge1", fleet_size=60, n_stations=40,
               horizon_days=60, legs_per_tail_day=2),
 "lge5": dict(family="lge1", fleet_size=60, n_stations=40,
               horizon_days=120, legs_per_tail_day=2),
 "lge6": dict(family="lge1", fleet_size=60, n_stations=40,
               horizon_days=180, legs_per_tail_day=2),
 "stress_capacity": dict(family="stress_capacity", fleet_size=20,
                n_stations=21, horizon_days=180, legs_per_tail_day=3,
                capable_fraction=.1, usage_tightness=.7),
 "stress_synchronised": dict(family="stress_synchronised", fleet_size=20,
                n_stations=21, horizon_days=180, legs_per_tail_day=2,
                capable_fraction=.25, usage_tightness=.95),
}


def preset(name, **overrides):
    d = dict(PRESETS[name]); d.update(overrides)
    return Config(**d).validate()


def derive_seed(root, *parts):
    data = "|".join([str(root), *map(str, parts)]).encode()
    return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")


def fingerprint(obj):
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------- generation

def build_costs(cfg, flights, assignment, tails, rng):
    """Cost matrix.

    "iid"    reproduces v1 exactly: base cost times uniform noise, plus a flat
             penalty for any tail other than the planted one.
    "factor" uses a low-rank Gaussian factor structure (a discrete copula):
             cost = base * (1 + rho*(tail_effect + station_effect) + eps).
             Correlated columns leave the LP relaxation fractional, which is
             what actually drives branch-and-bound effort; i.i.d. noise does
             the opposite. A configurable share of legs is pushed into a
             near-tie band to inflate the search tree without moving the
             optimum.
    """
    if cfg.cost_model == "iid":
        costs = []
        for flight in flights:
            preferred = assignment[str(flight[0])]
            block = flight[4] - flight[3]
            row = []
            for tail in tails:
                noise = rng.uniform(-cfg.cost_dispersion, cfg.cost_dispersion)
                row.append(round((1000 + 3 * block) * (1 + noise) +
                                 (0 if tail == preferred else 80), 1))
            costs.append(row)
        return costs

    rho = cfg.cost_factor_rho
    tail_effect = {t: rng.gauss(0, 1) for t in tails}
    station_effect = defaultdict(lambda: rng.gauss(0, 1))
    # tail x station interaction: a second factor so no tail is globally cheap
    inter = {}
    costs = []
    for flight in flights:
        preferred = assignment[str(flight[0])]
        block = flight[4] - flight[3]
        base = 1000 + 3 * block
        origin = flight[1]
        se = station_effect[origin]
        row = []
        for tail in tails:
            key = (tail, origin)
            if key not in inter:
                inter[key] = rng.gauss(0, 1)
            common = rho * (0.6 * tail_effect[tail] + 0.4 * se)
            idio = math.sqrt(max(0.0, 1 - rho * rho)) * inter[key]
            z = common + idio
            row.append((base * (1 + cfg.cost_dispersion * z) +
                        (0 if tail == preferred else 80)))
        if cfg.cost_tie_band > 0 and rng.random() < cfg.cost_tie_band:
            # collapse this row into a near-tie band around its own mean
            mean = sum(row) / len(row)
            row = [mean + (v - mean) * 0.02 for v in row]
        costs.append([round(v, 1) for v in row])
    return costs


def digraph_balance(arcs):
    """Per-node out-degree minus in-degree, and the worst imbalance."""
    indeg = Counter(b for _, b in arcs)
    outdeg = Counter(a for a, _ in arcs)
    nodes = set(indeg) | set(outdeg)
    delta = {v: outdeg[v] - indeg[v] for v in nodes}
    return delta, max((abs(d) for d in delta.values()), default=0)


def hierholzer(arcs):
    """Decompose a balanced digraph into edge-disjoint closed walks.

    Euler's theorem: a directed multigraph admits a closed walk using every arc
    exactly once on each connected component precisely when every node has equal
    in-degree and out-degree. Hierholzer's algorithm constructs those walks in
    linear time. Returns None if the graph is not balanced, so the caller can
    treat "decomposes" as a property that was verified rather than assumed.
    """
    delta, worst = digraph_balance(arcs)
    if worst != 0:
        return None
    remaining = defaultdict(list)
    for a, b in arcs:
        remaining[a].append(b)
    circuits, used, total = [], 0, len(arcs)
    while used < total:
        start = next((v for v, e in remaining.items() if e), None)
        if start is None:
            break
        stack, circuit = [start], []
        while stack:
            v = stack[-1]
            if remaining.get(v):
                stack.append(remaining[v].pop())
                used += 1
            else:
                circuit.append(stack.pop())
        circuits.append(list(reversed(circuit)))
    return circuits if used == total else None


PRIMES = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61,
          67, 71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113, 127, 131, 137,
          139, 149, 151, 157, 163, 167, 173, 179, 181, 191, 193, 197, 199]


def _nearest_prime(target, used):
    best = None
    for p in PRIMES:
        if p in used:
            continue
        d = abs(p - target)
        if best is None or d < best[0]:
            best = (d, p)
    return best[1] if best else None


def derive_thresholds(cfg, daily_block):
    """Maintenance limits expressed as pairwise-coprime day periods.

    v1's limits are absolute constants: C is 600 elapsed days and D is 3000,
    against a horizon that never exceeds 180, so those two checks are
    unreachable and the cascading reset that a C or D check triggers is dead
    code. Here each check instead gets a period drawn from the primes near
    horizon/8, horizon/5, horizon/3.2 and horizon/2. Distinct primes are
    pairwise coprime, so the least common multiple of any two periods exceeds
    the horizon: no two checks ever settle into a shared rhythm, and the reset
    pattern stays aperiodic across the whole dataset. Periods below the horizon
    also guarantee that every check type actually fires.

    A and B are counted in flight minutes, so their periods are converted using
    the fleet's estimated daily block time; C and D are counted in days and
    used directly.
    """
    if cfg.threshold_mode == "legacy":
        return dict(THRESHOLDS), dict(DURATIONS), None
    h = cfg.horizon_days
    used, periods = set(), []
    for target in (h / 8.0, h / 5.0, h / 3.2, h / 2.0):
        p = _nearest_prime(max(2.0, target), used)
        while p is not None and periods and p <= periods[-1]:
            used.add(p)
            p = _nearest_prime(max(2.0, target), used)
        if p is None:
            raise ValueError("horizon too short for coprime thresholds")
        used.add(p); periods.append(p)
    pA, pB, pC, pD = periods
    thresholds = {"A": max(120, int(round(pA * daily_block))),
                  "B": max(240, int(round(pB * daily_block))),
                  "C": pC, "D": pD}
    # A check must be short relative to its own period or the aircraft spends
    # the horizon on the ground.
    durations = {"A": 360, "B": 720,
                 "C": int(max(DAY, round(pC / 8) * DAY)),
                 "D": int(max(2 * DAY, round(pD / 6) * DAY))}
    if cfg.application_compatible:
        durations["C"] = 720
        durations["D"] = 720
    return thresholds, durations, dict(zip(CHECKS, periods))


def generate(cfg: Config, replicate=1):
    cfg.validate()
    rng = random.Random(derive_seed(cfg.root_seed, cfg.family, replicate))
    tails = list(range(cfg.fleet_size))
    stations = [chr(65 + i) if i < 26 else f"S{i:02d}"
                for i in range(cfg.n_stations)]
    capable_n = max(1, math.ceil(cfg.n_stations * cfg.capable_fraction))
    capable = stations[:capable_n]
    slots = max(1, math.ceil(cfg.fleet_size / capable_n))
    if cfg.application_compatible:
        slots = cfg.fleet_size
    capacity = {s: slots if s in capable else 0 for s in stations}

    rotations = max(1, round(cfg.legs_per_tail_day / 2))
    hops = max(2, round(cfg.legs_per_tail_day))
    legs_per_day = (hops if cfg.route_topology in ("tours", "euler")
                    else 2 * rotations)
    if cfg.route_topology in ("tours", "euler"):
        max_block = max(60, cfg.bank_slot_minutes - cfg.min_turn_minutes - 25)
        mean_block = (60 + max_block) / 2
    else:
        mean_block = 105
    daily_block = legs_per_day * mean_block
    thresholds, durations, periods = derive_thresholds(cfg, daily_block)
    projected_block = legs_per_day * (150 if cfg.safe_lookahead else 120)

    positions, state = {}, {}
    initial = {"A": {}, "B": {}, "C_Days": {}, "D_Days": {}}
    keys = {"A": "A", "B": "B", "C": "C_Days", "D": "D_Days"}
    for tail in tails:
        positions[str(tail)] = capable[tail % capable_n]
        state[tail] = {}
        for check in CHECKS:
            # Stratified staggering plus seeded perturbation.
            rank = (tail + .5) / cfg.fleet_size
            frac = min(.97, cfg.usage_tightness *
                       (.35 + .65 * rank) * rng.uniform(.92, 1.08))
            value = int(thresholds[check] * frac)
            if cfg.application_compatible and check in ("A", "B"):
                value = min(value, max(0, thresholds[check] - projected_block))
            if cfg.application_compatible and check in ("C", "D"):
                value = min(value, max(0, thresholds[check] - 1))
            initial[keys[check]][str(tail)] = value
            state[tail][check] = float(value)

    # Euler mode repositions aircraft overnight, so the live `positions` map
    # changes as the horizon is built. The instance must publish where each
    # tail STARTED, not where it ended up.
    initial_positions = dict(positions)

    flights, assignment, events = [], {}, []
    available = {t: 0 for t in tails}
    occupancy = Counter()
    # src/model.py indexes Cost_Matrix using ``flight_id - 1``. Publish
    # one-based IDs so generated instances use the shared application schema.
    leg_id = 1

    def days_to_due(tail, check):
        """Days of operation left before this check comes due."""
        remaining = thresholds[check] - state[tail][check]
        if check in ("C", "D"):
            return remaining
        return remaining / max(1.0, daily_block)

    def cycle_days(check):
        """Length of this check's cycle, in days of operation."""
        if check in ("C", "D"):
            return float(thresholds[check])
        return thresholds[check] / max(1.0, daily_block)

    def effective_lead(check):
        """How early this check may be pulled forward.

        Never more than half its own cycle. A fixed lead longer than the cycle
        makes a check permanently 'due soon': it is redone the day after every
        reset, the aircraft never flies again, and the horizon yields no
        flights at all. Short coprime A periods hit this immediately.
        """
        return min(cfg.maintenance_lead_days, cycle_days(check) / 2.0)

    def can_ground(station, day, check):
        """Is there a maintenance slot at this station for the whole check?"""
        span = int(math.ceil(durations[check] / DAY))
        limit = capacity.get(station, 0)
        return all(occupancy[(station, day + k)] < limit for k in range(span))

    def daily_tour(tail, day, home):
        """A closed walk home -> shared stations -> home. Returning to base
        every evening keeps each tail's daily sub-route balanced, so flow
        continuity holds no matter how the stations in between are chosen."""
        pool = [stations[(day * 2 + k * 3 + (tail // 4)) % len(stations)]
                for k in range(hops - 1)]
        seq = [home] + pool + [home]
        for k in range(1, len(seq)):
            if seq[k] == seq[k - 1]:
                seq[k] = stations[(stations.index(seq[k]) + 1) % len(stations)]
        if seq[-1] != home:                     # never strand a tail away
            seq[-1] = home
            if len(seq) > 2 and seq[-2] == home:
                seq[-2] = stations[(stations.index(home) + 1) % len(stations)]
        return seq

    euler_audit = []

    def emit_leg(tail, origin, dest, dep, arr):
        nonlocal leg_id
        flights.append([leg_id, origin, dest, dep, arr])
        assignment[str(leg_id)] = tail
        leg_id += 1
        state[tail]["A"] += arr - dep
        state[tail]["B"] += arr - dep

    def cycle_segments(day, group):
        """Cut one closed cycle through the group's bases into an open walk per
        tail: tail j flies base_j -> intermediates -> base_(j+1), and the last
        tail closes the cycle back to base_0.

        Concatenating the segments reproduces the cycle exactly, so the arc set
        is balanced at every node: the intermediates contribute one in and one
        out each, and each base is left once and entered once. The multiset of
        overnight positions is therefore preserved, which is the balance
        condition restated at fleet level.
        """
        bases = [positions[str(t)] for t in group]
        segments = []
        for j, tail in enumerate(group):
            src, dst = bases[j], bases[(j + 1) % len(group)]
            # Intermediates are shared daily HUBS, identical for every tail and
            # every group, rather than a per-tail function. Keying them on the
            # tail scatters the fleet across the map so no two aircraft are
            # ever at the same station at the same time, which is the very
            # thing the decomposition is meant to create. A common hub per hop
            # concentrates the whole fleet into one bank.
            seq = [src] + [stations[(day * 2 + s * 3) % len(stations)]
                           for s in range(hops - 1)] + [dst]
            for k in range(1, len(seq) - 1):     # only intermediates may move
                guard = 0
                while (seq[k] == seq[k - 1] or seq[k] == seq[k + 1]) \
                        and guard < len(stations):
                    seq[k] = stations[(stations.index(seq[k]) + 1)
                                      % len(stations)]
                    guard += 1
            segments.append((tail, seq))
        return segments

    def fly_euler_day(day, day0):
        """Emit one day of flying as a balanced arc set, then verify it."""
        # A tail whose check finishes before the first departure bank can
        # still fly that day, exactly as it can in the other topologies.
        ready = [t for t in tails if available[t] <= day0 + 360]
        rng.shuffle(ready)
        size = max(1, min(cfg.euler_group_size, len(ready) or 1))
        groups = [ready[i:i + size] for i in range(0, len(ready), size)]
        slot = cfg.bank_slot_minutes
        max_block = max(60, slot - cfg.min_turn_minutes - 25)
        day_arcs = []
        for group in groups:
            plan, ok = [], True
            for tail, seq in cycle_segments(day, group):
                legs = []
                earliest = max(day0 + 360, available[tail])
                for k in range(len(seq) - 1):
                    dep = day0 + 360 + k * slot + rng.randint(0, 20)
                    block = rng.randint(60, max_block)
                    arr = dep + block
                    if dep < earliest or arr >= day0 + 1430:
                        ok = False
                        break
                    legs.append((seq[k], seq[k + 1], dep, arr))
                if not ok:
                    break
                plan.append((tail, seq, legs))
            if not ok:
                # Emit a cycle whole or not at all. A partial cycle would leave
                # a station with more departures than arrivals, breaking the
                # balance the decomposition depends on.
                continue
            for tail, seq, legs in plan:
                for origin, dest, dep, arr in legs:
                    emit_leg(tail, origin, dest, dep, arr)
                    day_arcs.append((origin, dest))
                positions[str(tail)] = seq[-1]
                available[tail] = legs[-1][3]
        _, worst = digraph_balance(day_arcs)
        circuits = hierholzer(day_arcs) if day_arcs else []
        euler_audit.append({"day": day, "arcs": len(day_arcs),
                            "max_imbalance": worst,
                            "decomposes": circuits is not None,
                            "circuits": len(circuits) if circuits else 0})

    def schedule_after_arrivals(day, day0):
        """Emit an MILP-representable check after a tail's final arrival."""
        for tail in tails:
            if not day0 < available[tail] < day0 + DAY:
                continue
            due = next((
                check for check in ("D", "C", "B", "A")
                if (state[tail][check] >= thresholds[check]
                    if check in ("C", "D")
                    else state[tail][check] + projected_block >= thresholds[check])
            ), None)
            if due is None:
                continue
            station = positions[str(tail)]
            start = available[tail]
            end = start + durations[due]
            if end > day0 + DAY or not can_ground(station, day, due):
                continue
            events.append({"tail": tail, "check": due, "station": station,
                           "start": start, "end": end})
            occupancy[(station, day)] += 1
            available[tail] = end
            for lower in CHECKS[:CHECKS.index(due) + 1]:
                state[tail][lower] = 0

    for day in range(cfg.horizon_days):
        day0 = day * DAY
        for tail in tails:
            home = positions[str(tail)]
            if available[tail] <= day0:
                state[tail]["C"] += 1
                state[tail]["D"] += 1

                if cfg.application_compatible:
                    continue

                projected = projected_block
                order = ("D", "C", "B", "A")

                def mandatory(check):
                    if check in ("C", "D"):
                        return state[tail][check] + 1 >= thresholds[check]
                    return state[tail][check] + projected >= thresholds[check]

                due = next((c for c in order if mandatory(c)), None)
                if due is None and cfg.maintenance_lead_days:
                    # Pull a check forward into a free slot. Once C and D fire
                    # regularly, waiting until the last legal day piles every
                    # tail's check onto the same few station-days and overruns
                    # capacity. Doing a check early is always legal, so taking
                    # a free slot when one exists keeps the plan feasible while
                    # letting capacity become genuinely binding.
                    due = next((c for c in order
                                if days_to_due(tail, c) <= effective_lead(c)
                                and can_ground(home, day, c)), None)

                if due:
                    start, end = day0, day0 + durations[due]
                    events.append({"tail": tail, "check": due, "station": home,
                                   "start": start, "end": end})
                    for k in range(int(math.ceil(durations[due] / DAY))):
                        occupancy[(home, day + k)] += 1
                    available[tail] = end
                    for lower in CHECKS[:CHECKS.index(due) + 1]:
                        state[tail][lower] = 0

        # Flying is decided AFTER every tail's maintenance is settled, because
        # the Euler construction needs to know which tails are grounded before
        # it can build a balanced arc set out of the ones that are flying.
        if cfg.route_topology == "euler":
            fly_euler_day(day, day0)
            if cfg.application_compatible:
                schedule_after_arrivals(day, day0)
            continue

        for tail in tails:
            home = positions[str(tail)]
            start_time = max(day0 + 360, available[tail])

            if cfg.route_topology == "tours":
                # Departures sit on a daily BANK grid rather than chaining off
                # each arrival. Chained timing makes every tail's ground window
                # a narrow turn-length sliver at a different moment, so two
                # tails are never on the ground together and no exchange is
                # ever feasible. A bank grid holds departures to a common slot
                # while block times vary, which is what actually creates
                # overlapping ground presence - the same reason real hub
                # carriers bank their arrivals.
                seq = daily_tour(tail, day, home)
                slot = cfg.bank_slot_minutes
                max_block = max(60, slot - cfg.min_turn_minutes - 25)
                tour, ok = [], True
                for k in range(len(seq) - 1):
                    dep = day0 + 360 + k * slot + rng.randint(0, 20)
                    if dep < start_time:
                        ok = False
                        break
                    block = rng.randint(60, max_block)
                    arr = dep + block
                    if arr >= day0 + 1430:
                        ok = False
                        break
                    tour.append((seq[k], seq[k + 1], dep, arr))
                if ok and tour:
                    for origin, dest, dep, arr in tour:
                        flights.append([leg_id, origin, dest, dep, arr])
                        assignment[str(leg_id)] = tail; leg_id += 1
                        state[tail]["A"] += arr - dep
                        state[tail]["B"] += arr - dep
                    available[tail] = tour[-1][3]
                continue

            for rotation in range(rotations):
                if start_time >= day0 + 1260: break
                away = stations[(tail + day + rotation + capable_n)
                                % len(stations)]
                if away == home:
                    away = stations[(stations.index(home) + 1) % len(stations)]

                b1 = rng.randint(60, 150)
                dep1 = start_time + rng.randint(0, 15)
                arr1 = dep1 + b1
                dep2 = arr1 + cfg.min_turn_minutes + rng.randint(0, 20)
                b2 = rng.randint(60, 150)
                arr2 = dep2 + b2
                if arr2 >= day0 + 1430: break

                flights.append([leg_id, home, away, dep1, arr1])
                assignment[str(leg_id)] = tail; leg_id += 1
                flights.append([leg_id, away, home, dep2, arr2])
                assignment[str(leg_id)] = tail; leg_id += 1
                state[tail]["A"] += b1 + b2
                state[tail]["B"] += b1 + b2
                available[tail] = arr2
                start_time = arr2 + cfg.min_turn_minutes

        if cfg.application_compatible:
            schedule_after_arrivals(day, day0)

    costs = build_costs(cfg, flights, assignment, tails, rng)
    if not flights:
        raise ValueError("configuration produced no flights")

    instance = {
      "Original_Filename":
        f"{cfg.family}_p{cfg.fleet_size}_h{cfg.horizon_days}_r{replicate}.json",
      "Parameters": {"Input_Horizon_Days": cfg.horizon_days,
                     "Target_Horizon_Days": cfg.horizon_days,
                     "Min_Turn_Minutes": cfg.min_turn_minutes},
      "Aircrafts": tails,
      "AIRCRAFT_INIT_POS": initial_positions,
      "Flights": flights,
      "Cost_Matrix": costs,
      "Maintenance_Thresholds": dict(thresholds),
      "Maintenance_Durations": dict(durations),
      "Station_Capacity": capacity,
      "Initial_Checks": initial,
      "Units": {"time": "minutes from horizon origin",
                "A_B_counters": "flight minutes",
                "C_D_counters": "elapsed days"},
      "Generator": {"name": "fore-benchgen-reconstruction",
                    "version": VERSION, "replicate": replicate,
                    "check_periods_days": periods,
                    "euler_audit": ({
                       "days": len(euler_audit),
                       "days_balanced": sum(1 for d in euler_audit
                                            if d["max_imbalance"] == 0),
                       "days_decomposing": sum(1 for d in euler_audit
                                               if d["decomposes"]),
                       "max_imbalance": max((d["max_imbalance"]
                                             for d in euler_audit), default=0),
                       "mean_circuits_per_day": round(
                           sum(d["circuits"] for d in euler_audit) /
                           max(1, len(euler_audit)), 2),
                     } if euler_audit else None),
                    "configuration": asdict(cfg)}
    }
    instance["Generator"]["sha256"] = fingerprint(instance)
    certificate = {"assignment": assignment,
                   "maintenance_events": events,
                   "instance_sha256": instance["Generator"]["sha256"]}
    report = validate(instance, certificate)
    instance["Validation"] = report
    return instance, certificate, report


# ------------------------------------------------------- routes and replay

def build_routes(instance, certificate):
    """Turn (flights + assignment + events) into one ordered activity list per
    tail. A route is the unit the Metropolis moves operate on."""
    assignment = certificate["assignment"]
    routes = defaultdict(list)
    for f in instance["Flights"]:
        tail = assignment[str(f[0])]
        routes[tail].append({"kind": "F", "id": f[0], "from": f[1], "to": f[2],
                             "start": f[3], "end": f[4]})
    for e in certificate.get("maintenance_events", []):
        routes[e["tail"]].append({"kind": "M", "id": None,
                                  "from": e["station"], "to": e["station"],
                                  "start": e["start"], "end": e["end"],
                                  "check": e["check"]})
    for tail in instance["Aircrafts"]:
        routes.setdefault(tail, [])
        routes[tail].sort(key=lambda a: (a["start"], a["end"]))
    return dict(routes)


def routes_to_certificate(routes, instance_sha):
    assignment, events = {}, []
    for tail, route in routes.items():
        for a in route:
            if a["kind"] == "F":
                assignment[str(a["id"])] = tail
            else:
                events.append({"tail": tail, "check": a["check"],
                               "station": a["from"], "start": a["start"],
                               "end": a["end"]})
    events.sort(key=lambda e: (e["start"], e["tail"]))
    return {"assignment": assignment, "maintenance_events": events,
            "instance_sha256": instance_sha}


def _gap_required(prev, nxt, turn):
    """Ground time required between two consecutive activities. A turn is only
    needed between two flights; a tail leaving maintenance may depart at once."""
    if prev is None or nxt is None:
        return 0
    return turn if (prev["kind"] == "F" and nxt["kind"] == "F") else 0


def replay_route(route, initial_counters, horizon_days, thresholds):
    """Replay a route under the generator's own counter semantics and report
    threshold compliance.

    A/B accrue flight minutes; C/D accrue one per calendar day on which the
    tail is free at day start (matching the generator, which skips days spent
    in maintenance). A check event resets its own counter and all lower ones.
    Returns (violations, peak_utilisation, end_counters).
    """
    ctr = {c: float(initial_counters[c]) for c in CHECKS}
    by_day_events = defaultdict(list)
    by_day_flights = defaultdict(list)
    busy = []
    for a in route:
        if a["kind"] == "M":
            by_day_events[a["start"] // DAY].append(a)
            busy.append((a["start"], a["end"]))
        else:
            by_day_flights[a["start"] // DAY].append(a)
            busy.append((a["start"], a["end"]))
    busy.sort()

    def free_at(t):
        for s, e in busy:
            if s < t < e:
                return False
            if s >= t:
                break
        return True

    violations, peak = [], 0.0
    order = list(CHECKS)
    for day in range(horizon_days):
        day0 = day * DAY
        if free_at(day0):
            ctr["C"] += 1
            ctr["D"] += 1
        for ev in by_day_events[day]:
            for lower in order[:order.index(ev["check"]) + 1]:
                ctr[lower] = 0.0
        for fl in by_day_flights[day]:
            block = fl["end"] - fl["start"]
            ctr["A"] += block
            ctr["B"] += block
        for c in CHECKS:
            util = ctr[c] / thresholds[c]
            peak = max(peak, util)
            if ctr[c] >= thresholds[c]:
                violations.append({"check": c, "day": day,
                                   "counter": round(ctr[c], 1),
                                   "threshold": thresholds[c]})
    return violations, peak, ctr


def route_is_time_feasible(route, init_station, turn):
    prev = None
    position = init_station
    for a in route:
        if a["from"] != position:
            return False
        if prev is not None and prev["end"] + _gap_required(prev, a, turn) > a["start"]:
            return False
        position, prev = a["to"], a
    return True


# ---------------------------------------------------------------- validation

def validate(instance, certificate=None, strict_thresholds=True):
    errors, warnings = [], []
    required = ("Aircrafts", "AIRCRAFT_INIT_POS", "Flights", "Cost_Matrix",
      "Maintenance_Thresholds", "Maintenance_Durations",
      "Station_Capacity", "Initial_Checks", "Parameters")
    for f in required:
        if f not in instance: errors.append(f"missing field: {f}")
    if errors: return {"feasibility_status": "FAIL",
                       "errors": errors, "warnings": warnings}

    tails, flights = instance["Aircrafts"], instance["Flights"]
    stations = set(instance["Station_Capacity"])
    ids = [f[0] for f in flights]
    if len(ids) != len(set(ids)): errors.append("duplicate flight IDs")
    for f in flights:
        if len(f) != 5 or f[1] not in stations or f[2] not in stations:
            errors.append(f"invalid flight {f}")
        elif f[3] >= f[4]: errors.append(f"non-positive block time {f[0]}")
    matrix = instance["Cost_Matrix"]
    if len(matrix) != len(flights) or any(len(x) != len(tails) for x in matrix):
        errors.append("cost matrix dimension mismatch")

    metrics = {"n_legs": len(flights), "fleet_size": len(tails)}

    if certificate:
        assignment = certificate.get("assignment", {})
        if set(assignment) != set(map(str, ids)):
            errors.append("certificate does not cover every flight")
        by_tail = defaultdict(list)
        for f in flights:
            if str(f[0]) in assignment:
                by_tail[assignment[str(f[0])]].append(f)
        turn = instance["Parameters"].get("Min_Turn_Minutes", 0)
        for tail, sequence in by_tail.items():
            sequence.sort(key=lambda x: x[3])
            position = instance["AIRCRAFT_INIT_POS"][str(tail)]
            previous = None
            for f in sequence:
                if f[1] != position:
                    errors.append(f"flow break: tail {tail}, flight {f[0]}")
                if previous and previous[4] + turn > f[3]:
                    errors.append(f"overlap: tail {tail}, flight {f[0]}")
                position, previous = f[2], f

        occupied = Counter()
        for event in certificate.get("maintenance_events", []):
            first = int(event["start"] // DAY)
            last = int(math.ceil(event["end"] / DAY))
            for day in range(first, last):
                occupied[(event["station"], day)] += 1
            for f in by_tail.get(event["tail"], []):
                if max(f[3], event["start"]) < min(f[4], event["end"]):
                    errors.append(f"flight during maintenance: {f[0]}")
        for (station, day), count in occupied.items():
            if count > instance["Station_Capacity"].get(station, 0):
                errors.append(f"capacity exceeded: {station}, day {day}")

        # --- v2: maintenance threshold compliance -------------------------
        # v1 never verified that usage counters stayed below their limits, so
        # a PASS did not certify maintenance feasibility. Replay every route.
        if not errors:
            thresholds = instance["Maintenance_Thresholds"]
            horizon = instance["Parameters"]["Target_Horizon_Days"]
            init = instance["Initial_Checks"]
            keymap = {"A": "A", "B": "B", "C": "C_Days", "D": "D_Days"}
            routes = build_routes(instance, certificate)
            worst, total_violations = 0.0, 0
            for tail in tails:
                counters = {c: init[keymap[c]][str(tail)] for c in CHECKS}
                viol, peak, _ = replay_route(routes.get(tail, []), counters,
                                             horizon, thresholds)
                worst = max(worst, peak)
                total_violations += len(viol)
                for v in viol[:3]:
                    msg = (f"threshold breach: tail {tail} check {v['check']} "
                           f"reached {v['counter']} of {v['threshold']} "
                           f"on day {v['day']}")
                    (errors if strict_thresholds else warnings).append(msg)
            metrics["peak_threshold_utilisation"] = round(worst, 4)
            metrics["threshold_violations"] = total_violations

    status = "FAIL" if errors else ("WARN" if warnings else "PASS")
    return {"feasibility_status": status, "errors": errors,
            "warnings": warnings, "metrics": metrics}


# ------------------------------------------------------------------ metrics

def connection_graph(instance, max_connect=MAX_CONNECT_MINUTES):
    """Time-feasible connection arcs between legs.

    Arc f -> g exists when g departs the station f arrives at, no earlier than
    the minimum turn and no later than `max_connect` afterwards (a longer gap
    is an overnight rest, not a connection). This graph depends only on the
    instance, never on the solution, so it is the honest measure of how much
    routing freedom the instance itself offers.
    """
    turn = instance["Parameters"].get("Min_Turn_Minutes", 0)
    flights = instance["Flights"]
    by_origin = defaultdict(list)
    for f in flights:
        by_origin[f[1]].append(f)
    for k in by_origin:
        by_origin[k].sort(key=lambda x: x[3])
    import bisect
    starts = {k: [x[3] for x in v] for k, v in by_origin.items()}
    pairs = []
    for f in flights:
        cand = by_origin.get(f[2], [])
        if not cand:
            continue
        lo = bisect.bisect_left(starts[f[2]], f[4] + turn)
        hi = bisect.bisect_right(starts[f[2]], f[4] + turn + max_connect)
        for g in cand[lo:hi]:
            if g[0] != f[0]:
                pairs.append((f[0], g[0]))
    return pairs


def _entropy(counts):
    total = sum(counts)
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            h -= p * math.log2(p)
    return h


def _algebraic_connectivity(instance):
    """Fiedler value of the undirected station graph. Low values mean a
    bottlenecked network, which is harder to route across."""
    stations = sorted(instance["Station_Capacity"])
    idx = {s: i for i, s in enumerate(stations)}
    n = len(stations)
    adj = [[0] * n for _ in range(n)]
    for f in instance["Flights"]:
        a, b = idx[f[1]], idx[f[2]]
        if a != b:
            adj[a][b] = adj[b][a] = 1
    try:
        import numpy as np
        A = np.array(adj, dtype=float)
        L = np.diag(A.sum(axis=1)) - A
        w = np.linalg.eigvalsh(L)
        lam2 = float(sorted(w)[1]) if n > 1 else 0.0
        return max(0.0, lam2), n
    except Exception:
        return None, n


def _overnight_stations(route):
    """Where a tail ends each day. A fleet that always parks at its own base
    has exactly one of these per tail; repositioning shows up as more."""
    last_of_day = {}
    for a in route:
        last_of_day[a["end"] // DAY] = a["to"]
    return set(last_of_day.values())


def _splice_points(route, init_station):
    INF = float("inf")
    pts = []
    for i in range(len(route) + 1):
        prev = route[i - 1] if i > 0 else None
        nxt = route[i] if i < len(route) else None
        pts.append({"i": i,
                    "station": prev["to"] if prev else init_station,
                    "free_from": prev["end"] if prev else 0,
                    "next_start": nxt["start"] if nxt else INF,
                    "prev": prev, "next": nxt})
    return pts


def _candidate_tails(instance, routes, leg, owner, turn):
    """How many tails could legally operate this leg in place of its owner.
    Uses a local insertion test: the tail must be on the ground at the leg's
    origin with enough room before its next commitment."""
    count = 0
    for tail, route in routes.items():
        if tail == owner:
            count += 1
            continue
        init = instance["AIRCRAFT_INIT_POS"][str(tail)]
        position = init
        prev = None
        fits = False
        for a in list(route) + [None]:
            nxt = a
            if position == leg[1]:
                pre_gap = turn if (prev is not None and prev["kind"] == "F") else 0
                post_gap = turn if (nxt is not None and nxt["kind"] == "F") else 0
                free_from = prev["end"] if prev else 0
                next_start = nxt["start"] if nxt else float("inf")
                if free_from + pre_gap <= leg[3] and leg[4] + post_gap <= next_start:
                    fits = True
                    break
            if nxt is None:
                break
            position, prev = nxt["to"], nxt
        count += 1 if fits else 0
    return count


def compute_metrics(instance, certificate, conn_pairs=None, sample=500,
                    seed=12345):
    """Complexity metrics in four families plus a composite index.

    Family A - decision freedom (how much choice the instance actually offers)
    Family B - constraint tightness (how close the plan runs to its limits)
    Family C - relaxation hardness proxies (what drives branch-and-bound)
    Family D - network structure and symmetry
    """
    turn = instance["Parameters"].get("Min_Turn_Minutes", 0)
    flights = instance["Flights"]
    tails = instance["Aircrafts"]
    assignment = certificate["assignment"]
    owner = {f[0]: assignment[str(f[0])] for f in flights}
    routes = build_routes(instance, certificate)
    pairs = connection_graph(instance) if conn_pairs is None else conn_pairs
    rng = random.Random(seed)

    # ---- Family A: decision freedom
    n_legs = len(flights)
    density = len(pairs) / n_legs if n_legs else 0.0
    same = sum(1 for a, b in pairs if owner[a] == owner[b])
    cross_ratio = (len(pairs) - same) / len(pairs) if pairs else 0.0

    sampled = flights if n_legs <= sample else rng.sample(flights, sample)
    bits, k_values = 0.0, []
    for f in sampled:
        k = _candidate_tails(instance, routes, f, owner[f[0]], turn)
        k_values.append(k)
        bits += math.log2(max(1, k))
    mean_bits = bits / len(sampled) if sampled else 0.0

    # ---- Family B: constraint tightness
    occupied = Counter()
    for e in certificate.get("maintenance_events", []):
        for d in range(int(e["start"] // DAY), int(math.ceil(e["end"] / DAY))):
            occupied[(e["station"], d)] += 1
    cap = instance["Station_Capacity"]
    utils = [c / cap[s] for (s, d), c in occupied.items() if cap.get(s, 0) > 0]
    peak_cap = max(utils) if utils else 0.0
    mean_cap = sum(utils) / len(utils) if utils else 0.0

    thresholds = instance["Maintenance_Thresholds"]
    horizon = instance["Parameters"]["Target_Horizon_Days"]
    keymap = {"A": "A", "B": "B", "C": "C_Days", "D": "D_Days"}
    peaks = []
    for tail in tails:
        counters = {c: instance["Initial_Checks"][keymap[c]][str(tail)]
                    for c in CHECKS}
        _, peak, _ = replay_route(routes.get(tail, []), counters, horizon,
                                  thresholds)
        peaks.append(peak)
    mean_peak = sum(peaks) / len(peaks) if peaks else 0.0
    slacks = [max(0.0, 1 - p) for p in peaks]
    mean_slack = sum(slacks) / len(slacks) if slacks else 0.0
    if len(slacks) > 1 and mean_slack > 0:
        var = sum((s - mean_slack) ** 2 for s in slacks) / (len(slacks) - 1)
        slack_cv = math.sqrt(var) / mean_slack
    else:
        slack_cv = 0.0
    events = certificate.get("maintenance_events", [])
    ev_mix = Counter(e["check"] for e in events)
    checks_active = sum(1 for c in CHECKS if ev_mix.get(c, 0) > 0)

    # ---- Family C: relaxation hardness proxies
    matrix = instance["Cost_Matrix"]
    argmins, margins, spreads = [], [], []
    for row in matrix:
        best = min(row)
        argmins.append(row.index(best))
        second = sorted(row)[1] if len(row) > 1 else best
        margins.append((second - best) / best if best else 0.0)
        spreads.append((max(row) - best) / best if best else 0.0)
    planted_optimal = sum(1 for f, a in zip(flights, argmins)
                          if owner[f[0]] == tails[a]) / n_legs if n_legs else 0
    mean_margin = sum(margins) / len(margins) if margins else 0.0
    mean_spread = sum(spreads) / len(spreads) if spreads else 0.0
    tie_rate = sum(1 for m in margins if m < 0.005) / len(margins) if margins else 0

    # ---- Family D: network structure and symmetry
    outdeg = Counter(f[1] for f in flights)
    deg_entropy = _entropy(list(outdeg.values()))
    max_deg_entropy = math.log2(len(cap)) if len(cap) > 1 else 1.0
    lam2, n_stations = _algebraic_connectivity(instance)
    # Eulerian balance, recomputed from the published flight list rather than
    # trusted from the generator: a day whose arcs are balanced decomposes into
    # closed walks by Euler's theorem, which is what makes the routing
    # rearrangeable instead of frozen.
    arcs_by_day = defaultdict(list)
    for f in flights:
        arcs_by_day[f[3] // DAY].append((f[1], f[2]))
    imbalances, decomposing = [], 0
    for d, arcs in arcs_by_day.items():
        _, worst = digraph_balance(arcs)
        imbalances.append(worst)
        if hierholzer(arcs) is not None:
            decomposing += 1
    n_days = max(1, len(arcs_by_day))
    balanced_days = sum(1 for x in imbalances if x == 0)

    groups = Counter()
    for t in tails:
        sig = (instance["AIRCRAFT_INIT_POS"][str(t)],
               tuple(round(instance["Initial_Checks"][keymap[c]][str(t)] /
                           thresholds[c], 2) for c in CHECKS))
        groups[sig] += 1
    log_aut = sum(math.log10(math.factorial(v)) for v in groups.values())

    # ---- composite index (geometric mean, so any collapsed dimension shows)
    def clamp(x, hi=1.0):
        return max(0.01, min(1.0, x / hi))
    sub = {
        "freedom_density": clamp(density, 3.0),
        "freedom_cross_tail": clamp(cross_ratio, 0.5),
        "freedom_bits": clamp(mean_bits, 2.0),
        "tightness_capacity": clamp(peak_cap, 1.0),
        "tightness_threshold": clamp(mean_peak, 1.0),
        "hardness_cost_signal": clamp(1 - planted_optimal, 1.0),
        "hardness_ties": clamp(tie_rate, 0.10),
        "structure_bottleneck": clamp(1 - (lam2 / n_stations if lam2 else 0), 1.0),
        "structure_balance": clamp(balanced_days / n_days, 1.0),
    }
    composite = math.exp(sum(math.log(v) for v in sub.values()) / len(sub))

    return {
      "A_decision_freedom": {
        "n_legs": n_legs,
        "connection_arcs": len(pairs),
        "connection_density": round(density, 4),
        "cross_tail_ratio": round(cross_ratio, 4),
        "mean_bits_per_leg": round(mean_bits, 4),
        "total_assignment_entropy_bits": round(mean_bits * n_legs, 1),
        "mean_candidate_tails": round(sum(k_values) / len(k_values), 3)
                                if k_values else 0,
        "sampled_legs": len(sampled),
      },
      "B_constraint_tightness": {
        "peak_capacity_utilisation": round(peak_cap, 4),
        "mean_capacity_utilisation": round(mean_cap, 4),
        "occupied_station_days": len(occupied),
        "mean_peak_threshold_utilisation": round(mean_peak, 4),
        "mean_slack_ratio": round(mean_slack, 4),
        "slack_cv": round(slack_cv, 4),
        "maintenance_events": len(events),
        "event_mix": dict(ev_mix),
        "check_types_active": checks_active,
      },
      "C_relaxation_hardness": {
        "planted_solution_is_greedy_optimal": round(planted_optimal, 4),
        "mean_top2_margin": round(mean_margin, 5),
        "mean_cost_spread": round(mean_spread, 4),
        "near_tie_rate": round(tie_rate, 4),
      },
      "D_structure_symmetry": {
        "station_degree_entropy_bits": round(deg_entropy, 4),
        "station_degree_entropy_normalised":
            round(deg_entropy / max_deg_entropy, 4) if max_deg_entropy else 0,
        "algebraic_connectivity":
            round(lam2, 5) if lam2 is not None else None,
        "n_stations": n_stations,
        "interchangeable_tail_groups": len(groups),
        "log10_symmetry_group_size": round(log_aut, 3),
        "eulerian_balanced_day_fraction": round(balanced_days / n_days, 4),
        "eulerian_decomposing_day_fraction": round(decomposing / n_days, 4),
        "max_daily_imbalance": max(imbalances) if imbalances else 0,
        "distinct_overnight_stations_per_tail": round(
            sum(len(_overnight_stations(r)) for r in routes.values()) /
            max(1, len(routes)), 3),
      },
      "composite": {
        "subscores": {k: round(v, 4) for k, v in sub.items()},
        "complexity_index": round(composite, 4),
        "note": "geometric mean of subscores; a collapsed dimension drags the "
                "whole index down by design",
      },
    }


# ------------------------------------------- feasibility-preserving walk

class FeasibleWalk:
    """Metropolis random walk over the space of FEASIBLE schedules.

    The move is a *segment exchange*: two tails that are both on the ground at
    the same station swap a bounded run of activities. Because both segments
    are spliced in at a common station, station-to-station flow continuity is
    preserved structurally; the maintenance event multiset is unchanged, so
    station capacity occupancy is invariant; and the two rebuilt routes are
    re-checked for turn times and maintenance threshold compliance before the
    move is even scored. A proposal that would break feasibility is discarded
    rather than penalised, so the walk cannot leave the feasible region -
    feasibility is an invariant of the chain, not a soft objective.

    The move is its own inverse (exchanging the same two segments back
    restores the previous state), which keeps the proposal distribution
    symmetric and the Metropolis acceptance rule valid.

    Energy is the negation of a weighted complexity score, so the chain drifts
    toward schedules that are harder while remaining provably feasible.
    """

    DEFAULT_WEIGHTS = {"cross_tail": 1.0, "cost_signal": 0.6,
                       "tightness": 0.5, "mixing": 0.4}

    def __init__(self, instance, certificate, weights=None, seed=7,
                 max_segment=8, dayblock_share=0.35, meetpoint_share=0.5,
                 objective="complexity", cost_weight=1.0):
        self.instance = instance
        self.dayblock_share = dayblock_share
        self.meetpoint_share = meetpoint_share
        self.rng = random.Random(seed)
        self.max_segment = max_segment
        self.weights = dict(self.DEFAULT_WEIGHTS)
        if weights:
            self.weights.update(weights)
        self.turn = instance["Parameters"].get("Min_Turn_Minutes", 0)
        self.horizon = instance["Parameters"]["Target_Horizon_Days"]
        self.thresholds = instance["Maintenance_Thresholds"]
        self.tails = list(instance["Aircrafts"])
        self.init_pos = {t: instance["AIRCRAFT_INIT_POS"][str(t)]
                         for t in self.tails}
        self.n_stations = max(2, len(instance["Station_Capacity"]))
        self.routes = build_routes(instance, certificate)
        for t in self.tails:
            self.routes.setdefault(t, [])

        keymap = {"A": "A", "B": "B", "C": "C_Days", "D": "D_Days"}
        self.initial = {t: {c: instance["Initial_Checks"][keymap[c]][str(t)]
                            for c in CHECKS} for t in self.tails}

        self.pairs = connection_graph(instance)
        self.pairs_by_leg = defaultdict(list)
        for k, (a, b) in enumerate(self.pairs):
            self.pairs_by_leg[a].append(k)
            self.pairs_by_leg[b].append(k)

        self.owner = {}
        for t, route in self.routes.items():
            for a in route:
                if a["kind"] == "F":
                    self.owner[a["id"]] = t
        self.same_pairs = sum(1 for a, b in self.pairs
                              if self.owner[a] == self.owner[b])

        matrix = instance["Cost_Matrix"]
        self.objective = objective
        self.cost_weight = cost_weight
        self.tail_index = {t: k for k, t in enumerate(self.tails)}
        self.cost_row = {f[0]: row for f, row in zip(instance["Flights"], matrix)}
        # A valid lower bound on ANY feasible schedule: every leg must be flown
        # by some tail, so the sum of per-leg minima can never be exceeded from
        # below. It ignores routing and maintenance, so it is loose - but it is
        # sound, which is what makes it usable as a MILP sanity bracket.
        self.cost_lower_bound = sum(min(row) for row in matrix)
        self.cost_scale = max(1.0, sum(sum(r) / len(r) for r in matrix) /
                              max(1, len(matrix)))
        self.cheapest = {}
        for f, row in zip(instance["Flights"], matrix):
            self.cheapest[f[0]] = self.tails[row.index(min(row))]
        self.n_legs = len(instance["Flights"])
        self.greedy_hits = sum(1 for lid, t in self.owner.items()
                               if self.cheapest[lid] == t)

        self.total_cost = sum(self.cost_row[lid][self.tail_index[t]]
                              for lid, t in self.owner.items())
        self.peaks = {}
        self.mix = {}
        for t in self.tails:
            _, peak, _ = replay_route(self.routes[t], self.initial[t],
                                      self.horizon, self.thresholds)
            self.peaks[t] = peak
            self.mix[t] = self._mixing(self.routes[t])
        self.accepted = 0
        self.proposed = 0
        self.rejected_infeasible = 0
        self.planted = dict(self.owner)
        self.visited = set()

    # -- scoring -----------------------------------------------------------
    def _mixing(self, route):
        counts = Counter(a["to"] for a in route if a["kind"] == "F")
        return _entropy(list(counts.values())) / math.log2(self.n_stations)

    def score(self):
        cross = ((len(self.pairs) - self.same_pairs) / len(self.pairs)
                 if self.pairs else 0.0)
        cost_signal = 1 - (self.greedy_hits / self.n_legs if self.n_legs else 0)
        tightness = sum(self.peaks.values()) / len(self.peaks)
        mixing = sum(self.mix.values()) / len(self.mix)
        w = self.weights
        return (w["cross_tail"] * cross + w["cost_signal"] * cost_signal +
                w["tightness"] * tightness + w["mixing"] * mixing)

    def energy(self):
        """complexity - drift toward harder schedules;
           cost       - descend toward a cheap incumbent, giving a tight upper
                        bound to check a MILP optimum against;
           mixed      - cheap AND structurally awkward."""
        normalised_cost = self.total_cost / self.cost_scale
        if self.objective == "cost":
            return normalised_cost
        if self.objective == "mixed":
            return self.cost_weight * normalised_cost - self.score()
        return -self.score()

    # -- moves -------------------------------------------------------------
    def _propose(self):
        if len(self.tails) < 2:
            return None
        u, v = self.rng.sample(self.tails, 2)
        ru, rv = self.routes[u], self.routes[v]
        pu = _splice_points(ru, self.init_pos[u])
        pv = _splice_points(rv, self.init_pos[v])
        by_station = defaultdict(list)
        for p in pv:
            by_station[p["station"]].append(p)
        start_u = self.rng.choice(pu)
        options = by_station.get(start_u["station"])
        if not options:
            return None
        start_v = self.rng.choice(options)
        lu = self.rng.randint(0, self.max_segment)
        lv = self.rng.randint(0, self.max_segment)
        if lu == 0 and lv == 0:
            return None
        iu1, iv1 = start_u["i"], start_v["i"]
        iu2, iv2 = min(iu1 + lu, len(ru)), min(iv1 + lv, len(rv))
        if iu2 == iu1 and iv2 == iv1:
            return None
        seg_u, seg_v = ru[iu1:iu2], rv[iv1:iv2]
        new_u = ru[:iu1] + seg_v + ru[iu2:]
        new_v = rv[:iv1] + seg_u + rv[iv2:]
        return u, v, seg_u, seg_v, new_u, new_v

    def _day_block(self, route, lo, hi):
        """Indices of the maximal run of activities lying entirely inside the
        half-open time window [lo, hi)."""
        first, last = None, None
        for k, a in enumerate(route):
            if a["start"] >= lo and a["end"] <= hi:
                if first is None:
                    first = k
                last = k
            elif first is not None and a["start"] >= hi:
                break
        if first is None:
            return None
        return first, last + 1

    def _propose_dayblock(self):
        """Exchange whole day-blocks between two tails.

        Aircraft sit on the ground overnight, so day boundaries are where the
        widest ground windows are and where an exchange is most likely to be
        feasible. Proposing there rather than at uniformly random splice points
        raises the acceptance rate by orders of magnitude on schedules whose
        aircraft return to base each evening.
        """
        if len(self.tails) < 2:
            return None
        u, v = self.rng.sample(self.tails, 2)
        ru, rv = self.routes[u], self.routes[v]
        if not ru or not rv:
            return None
        span = self.rng.randint(1, max(1, self.max_segment // 2))
        last_day = max(ru[-1]["end"], rv[-1]["end"]) // DAY
        day = self.rng.randint(0, max(0, int(last_day)))
        lo, hi = day * DAY, (day + span) * DAY
        bu = self._day_block(ru, lo, hi)
        bv = self._day_block(rv, lo, hi)
        if bu is None and bv is None:
            return None
        iu1, iu2 = bu if bu else (len(ru), len(ru))
        iv1, iv2 = bv if bv else (len(rv), len(rv))
        seg_u, seg_v = ru[iu1:iu2], rv[iv1:iv2]
        new_u = ru[:iu1] + seg_v + ru[iu2:]
        new_v = rv[:iv1] + seg_u + rv[iv2:]
        return u, v, seg_u, seg_v, new_u, new_v

    def _propose_meetpoint(self):
        """Exchange the run of activities between two stations where BOTH
        tails are on the ground.

        A whole-day exchange relabels two routes without changing which
        connections are same-tail and which are cross-tail, so it cannot move
        the routing-freedom metrics at all. Splicing at a shared intermediate
        station does: it re-cuts the routes mid-day, which is the only move
        that genuinely re-partitions the connection graph. The segment is
        bounded at both ends by a station both tails actually visit, so flow
        continuity is guaranteed before the timing check ever runs.
        """
        if len(self.tails) < 2:
            return None
        u, v = self.rng.sample(self.tails, 2)
        ru, rv = self.routes[u], self.routes[v]
        pu, pv = _splice_points(ru, self.init_pos[u]), _splice_points(rv, self.init_pos[v])
        pv_by_station = defaultdict(list)
        for p in pv:
            pv_by_station[p["station"]].append(p)
        starts = [p for p in pu if p["station"] in pv_by_station]
        if not starts:
            return None
        s1 = self.rng.choice(starts)
        t1 = self.rng.choice(pv_by_station[s1["station"]])

        ends_u = [p for p in pu if s1["i"] <= p["i"] <= s1["i"] + self.max_segment]
        cand = []
        for eu in ends_u:
            for ev in pv_by_station.get(eu["station"], ()):
                if t1["i"] <= ev["i"] <= t1["i"] + self.max_segment:
                    if eu["i"] > s1["i"] or ev["i"] > t1["i"]:
                        cand.append((eu, ev))
        if not cand:
            return None
        e1, e2 = self.rng.choice(cand)
        seg_u, seg_v = ru[s1["i"]:e1["i"]], rv[t1["i"]:e2["i"]]
        new_u = ru[:s1["i"]] + seg_v + ru[e1["i"]:]
        new_v = rv[:t1["i"]] + seg_u + rv[e2["i"]:]
        return u, v, seg_u, seg_v, new_u, new_v

    def _feasible(self, u, v, new_u, new_v):
        """Every feasibility condition, checked before the move can be scored.
        Station capacity is not re-checked here because the exchange moves
        whole maintenance activities between routes without changing their
        station or timing, leaving occupancy identical by construction."""
        if not route_is_time_feasible(new_u, self.init_pos[u], self.turn):
            return None
        if not route_is_time_feasible(new_v, self.init_pos[v], self.turn):
            return None
        vio_u, peak_u, _ = replay_route(new_u, self.initial[u], self.horizon,
                                        self.thresholds)
        if vio_u:
            return None
        vio_v, peak_v, _ = replay_route(new_v, self.initial[v], self.horizon,
                                        self.thresholds)
        if vio_v:
            return None
        return peak_u, peak_v

    def _apply(self, u, v, seg_u, seg_v, new_u, new_v, peaks):
        changed = [a["id"] for a in seg_u if a["kind"] == "F"] + \
                  [a["id"] for a in seg_v if a["kind"] == "F"]
        touched = set()
        for lid in changed:
            touched.update(self.pairs_by_leg[lid])
        before = sum(1 for k in touched
                     if self.owner[self.pairs[k][0]] == self.owner[self.pairs[k][1]])
        before_hits = sum(1 for lid in changed
                          if self.cheapest[lid] == self.owner[lid])
        before_cost = sum(self.cost_row[lid][self.tail_index[self.owner[lid]]]
                          for lid in changed)
        for a in seg_u:
            if a["kind"] == "F":
                self.owner[a["id"]] = v
        for a in seg_v:
            if a["kind"] == "F":
                self.owner[a["id"]] = u
        after = sum(1 for k in touched
                    if self.owner[self.pairs[k][0]] == self.owner[self.pairs[k][1]])
        after_hits = sum(1 for lid in changed
                         if self.cheapest[lid] == self.owner[lid])
        after_cost = sum(self.cost_row[lid][self.tail_index[self.owner[lid]]]
                         for lid in changed)
        self.total_cost += after_cost - before_cost
        self.same_pairs += after - before
        self.greedy_hits += after_hits - before_hits
        self.routes[u], self.routes[v] = new_u, new_v
        self.peaks[u], self.peaks[v] = peaks
        self.mix[u] = self._mixing(new_u)
        self.mix[v] = self._mixing(new_v)

    def _revert_owner(self, seg_u, seg_v, u, v):
        for a in seg_u:
            if a["kind"] == "F":
                self.owner[a["id"]] = u
        for a in seg_v:
            if a["kind"] == "F":
                self.owner[a["id"]] = v

    # -- driver ------------------------------------------------------------
    def run(self, iterations=4000, t_start=0.08, t_end=0.004, trace_every=0):
        """Geometric cooling from t_start to t_end. Returns a trace."""
        trace = []
        current = self.energy()
        cooling = (t_end / t_start) ** (1 / max(1, iterations - 1))
        temperature = t_start
        for step in range(iterations):
            self.proposed += 1
            roll = self.rng.random()
            if roll < self.dayblock_share:
                move = self._propose_dayblock()
            elif roll < self.dayblock_share + self.meetpoint_share:
                move = self._propose_meetpoint()
            else:
                move = self._propose()
            if move:
                u, v, seg_u, seg_v, new_u, new_v = move
                peaks = self._feasible(u, v, new_u, new_v)
                if peaks is None:
                    self.rejected_infeasible += 1
                else:
                    snapshot = (self.routes[u], self.routes[v],
                                self.same_pairs, self.greedy_hits,
                                self.peaks[u], self.peaks[v],
                                self.mix[u], self.mix[v], self.total_cost)
                    self._apply(u, v, seg_u, seg_v, new_u, new_v, peaks)
                    candidate = self.energy()
                    delta = candidate - current
                    if delta <= 0 or self.rng.random() < math.exp(-delta / temperature):
                        current = candidate
                        self.accepted += 1
                        self.visited.add(hash(tuple(sorted(self.owner.items()))))
                    else:
                        (self.routes[u], self.routes[v], self.same_pairs,
                         self.greedy_hits, self.peaks[u], self.peaks[v],
                         self.mix[u], self.mix[v], self.total_cost) = snapshot
                        self._revert_owner(seg_u, seg_v, u, v)
            if trace_every and step % trace_every == 0:
                trace.append({"step": step, "temperature": round(temperature, 5),
                              "score": round(-current, 5),
                              "accepted": self.accepted})
            temperature *= cooling
        return trace

    def certificate(self):
        return routes_to_certificate(self.routes,
                                     self.instance["Generator"]["sha256"])

    def hamming(self):
        """Legs assigned to a different tail than in the planted solution."""
        return sum(1 for lid, t in self.owner.items() if self.planted[lid] != t)

    def stats(self):
        return {"proposed": self.proposed, "accepted": self.accepted,
                "acceptance_rate": round(self.accepted / max(1, self.proposed), 4),
                "rejected_infeasible": self.rejected_infeasible,
                "final_score": round(self.score(), 5),
                "hamming_from_planted": self.hamming(),
                "hamming_fraction": round(self.hamming() / max(1, self.n_legs), 4),
                "distinct_feasible_schedules_seen": len(self.visited),
                "objective": self.objective,
                "total_cost": round(self.total_cost, 2),
                "cost_lower_bound": round(self.cost_lower_bound, 2)}


def perturb(instance, certificate, iterations=4000, seed=7, weights=None,
            max_segment=8, t_start=0.08, t_end=0.004, dayblock_share=0.35,
            meetpoint_share=0.5, objective="complexity", cost_weight=1.0):
    """Run the walk and return (new_certificate, validation_report, stats)."""
    walk = FeasibleWalk(instance, certificate, weights=weights, seed=seed,
                        max_segment=max_segment, dayblock_share=dayblock_share,
                        meetpoint_share=meetpoint_share, objective=objective,
                        cost_weight=cost_weight)
    walk.run(iterations=iterations, t_start=t_start, t_end=t_end)
    new_cert = walk.certificate()
    report = validate(instance, new_cert)
    return new_cert, report, walk.stats()


def schedule_cost(instance, certificate):
    """Total cost of a schedule under the instance cost matrix."""
    tail_index = {t: k for k, t in enumerate(instance["Aircrafts"])}
    total = 0.0
    for f, row in zip(instance["Flights"], instance["Cost_Matrix"]):
        total += row[tail_index[certificate["assignment"][str(f[0])]]]
    return round(total, 2)


def cost_lower_bound(instance):
    """Sound lower bound on every feasible schedule.

    Each leg must be flown by some tail, so no schedule can cost less than the
    sum of the per-leg minima. The bound ignores routing continuity and
    maintenance, so it is loose - but it is valid, which is what makes it a
    usable bracket for checking a MILP result.
    """
    return round(sum(min(row) for row in instance["Cost_Matrix"]), 2)


def plant_optimum(instance, certificate, margin=0.04):
    """Rewrite costs so that a designated schedule is PROVABLY optimal.

    For every leg the designated tail is priced strictly below every other
    tail. The per-leg minima are then attained simultaneously by that one
    schedule, so its cost equals the lower bound - and a bound that is attained
    is the optimum. That gives an exact ground-truth objective value for
    checking that a MILP converges to the true least-cost solution rather than
    merely to a good feasible one.

    The trade-off is unavoidable and worth stating: any instance whose optimum
    coincides with the per-leg minima is also solvable greedily. Use this mode
    to validate CORRECTNESS, and the unplanted mode - where the optimum is
    bracketed but unknown - to measure PERFORMANCE.
    """
    tail_index = {t: k for k, t in enumerate(instance["Aircrafts"])}
    for f, row in zip(instance["Flights"], instance["Cost_Matrix"]):
        j = tail_index[certificate["assignment"][str(f[0])]]
        others = [v for k, v in enumerate(row) if k != j]
        if not others:
            continue
        row[j] = round(max(1.0, min(others) * (1 - margin)), 1)
    optimum = schedule_cost(instance, certificate)
    bound = cost_lower_bound(instance)
    instance["Known_Optimum"] = {
        "objective": optimum,
        "lower_bound": bound,
        "proof": "per-leg cost minima are attained simultaneously by a "
                 "certified-feasible schedule, so the bound is tight",
        "is_tight": abs(optimum - bound) < 1e-6,
        "margin": margin,
    }
    instance["Generator"].pop("sha256", None)
    instance.pop("Validation", None)
    instance["Generator"]["sha256"] = fingerprint(instance)
    certificate["instance_sha256"] = instance["Generator"]["sha256"]
    return instance, certificate


def solution_pool(instance, certificate, size=5, iterations=3000, seed=7,
                  **kw):
    """Several DISTINCT certified-feasible schedules, ranked by cost.

    Half the runs descend on cost to drive the incumbent - the tightest upper
    bound on the optimum - and half wander on complexity to spread the pool out
    across the feasible region. A MILP result can then be checked three ways:
    it must not beat the lower bound, it must not be beaten by any pool member,
    and where an optimum is planted it must match it exactly.
    """
    planted_cost = schedule_cost(instance, certificate)
    bound = cost_lower_bound(instance)
    entries, seen = [], {fingerprint(certificate["assignment"])}
    pool = [{"origin": "planted", "cost": planted_cost,
             "hamming_from_planted": 0, "status": "PASS",
             "certificate": certificate}]
    for k in range(size):
        objective = "cost" if k % 2 == 0 else "complexity"
        cert, report, stats = perturb(instance, certificate,
                                      iterations=iterations, seed=seed + 13 * k,
                                      objective=objective, **kw)
        if report["feasibility_status"] == "FAIL":
            continue
        key = fingerprint(cert["assignment"])
        if key in seen:
            continue
        seen.add(key)
        pool.append({"origin": objective, "cost": schedule_cost(instance, cert),
                     "hamming_from_planted": stats["hamming_from_planted"],
                     "status": report["feasibility_status"],
                     "certificate": cert})
    pool.sort(key=lambda e: e["cost"])
    for rank, entry in enumerate(pool, start=1):
        entry["rank"] = rank
    best = pool[0]["cost"]
    known = instance.get("Known_Optimum")
    return {
      "lower_bound": bound,
      "planted_cost": planted_cost,
      "best_known_cost": best,
      "worst_known_cost": pool[-1]["cost"],
      "gap_best_to_lower_bound": round((best - bound) / bound, 6) if bound else None,
      "known_optimum": known["objective"] if known else None,
      "optimum_is_proven": bool(known and known["is_tight"]),
      "n_distinct_solutions": len(pool),
      "cost_spread": round(pool[-1]["cost"] - best, 2),
      "milp_checks": {
        "must_not_be_below": bound,
        "must_not_exceed": known["objective"] if known else best,
        "note": "a reported objective below the lower bound means the model is "
                "under-constrained; above the best known feasible cost means "
                "it stopped early or the search is not converging",
      },
      "solutions": [{"rank": e["rank"], "origin": e["origin"], "cost": e["cost"],
                     "hamming_from_planted": e["hamming_from_planted"],
                     "status": e["status"],
                     "assignment": e["certificate"]["assignment"],
                     "maintenance_events": e["certificate"]["maintenance_events"]}
                    for e in pool],
    }


# ------------------------------------------------------------------ export

def export(instance, certificate, report, out_dir, formats, metrics=None,
           pool=None):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    stem = Path(instance["Original_Filename"]).stem
    made = []
    if "json" in formats:
        p = out / f"{stem}.json"
        p.write_text(json.dumps(instance, indent=2) + "\n"); made.append(p)
    if "csv" in formats:
        p = out / f"{stem}.flights.csv"
        with p.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(("id", "origin", "destination", "departure", "arrival"))
            w.writerows(instance["Flights"])
        made.append(p)
    c = out / f"{stem}.solution.json"
    c.write_text(json.dumps(certificate, indent=2) + "\n"); made.append(c)
    v = out / f"{stem}.validation.json"
    v.write_text(json.dumps(report, indent=2) + "\n"); made.append(v)
    if metrics is not None:
        m = out / f"{stem}.metrics.json"
        m.write_text(json.dumps(metrics, indent=2) + "\n"); made.append(m)
    if pool:
        p = out / f"{stem}.pool.json"
        p.write_text(json.dumps(pool, indent=2) + "\n"); made.append(p)
    if "zip" in formats:
        z = out / f"{stem}.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as archive:
            for q in made:
                archive.write(q, q.name)
        made.append(z)
    manifest = {q.name: {"bytes": q.stat().st_size,
      "sha256": hashlib.sha256(q.read_bytes()).hexdigest()} for q in made}
    mf = out / f"{stem}.manifest.json"
    mf.write_text(json.dumps(manifest, indent=2) + "\n"); made.append(mf)
    return [str(x) for x in made]


def load_config(path=None, preset_name="small"):
    cfg = preset(preset_name)
    if path:
        data = json.loads(Path(path).read_text())
        cfg = Config(**data).validate()
    return cfg


def benchmark(cfg, factors, replications, out_dir, with_metrics=True,
              perturb_iterations=0):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    keys = list(factors); rows = []; number = 0
    for values in itertools.product(*(factors[k] for k in keys)):
        for replicate in range(1, replications + 1):
            data = asdict(cfg); data.update(dict(zip(keys, values)))
            local = Config(**data).validate()
            instance, certificate, report = generate(local, replicate)
            stats = None
            if perturb_iterations:
                certificate, report, stats = perturb(
                    instance, certificate, iterations=perturb_iterations,
                    seed=local.root_seed % 100000 + replicate)
                instance["Validation"] = report
            metrics = compute_metrics(instance, certificate) if with_metrics else None
            export(instance, certificate, report, out, ["json"], metrics=metrics)
            row = {"number": number, "replicate": replicate,
                   **dict(zip(keys, values)), **report["metrics"],
                   "status": report["feasibility_status"]}
            if metrics:
                row["complexity_index"] = metrics["composite"]["complexity_index"]
                row["cross_tail_ratio"] = \
                    metrics["A_decision_freedom"]["cross_tail_ratio"]
                row["connection_density"] = \
                    metrics["A_decision_freedom"]["connection_density"]
            if stats:
                row["hamming_fraction"] = stats["hamming_fraction"]
            rows.append(row); number += 1
    (out / "benchmark.json").write_text(json.dumps(rows, indent=2) + "\n")
    return rows


# --------------------------------------------------------------------- CLI

def _add_generation_flags(p):
    p.add_argument("--preset", choices=PRESETS, default="small")
    p.add_argument("--config")
    p.add_argument("--root-seed", type=int)
    p.add_argument("--topology", choices=("out_and_back", "tours", "euler"),
                   help="euler builds each day as a balanced arc set decomposed "
                        "into per-tail walks, so aircraft reposition between "
                        "bases overnight; tours shares stations but parks every "
                        "tail back at its own base each night")
    p.add_argument("--cost-model", choices=("iid", "factor"),
                   help="factor uses correlated costs that leave the LP "
                        "relaxation fractional")
    p.add_argument("--legs-per-tail-day", type=float)
    p.add_argument("--thresholds", choices=("legacy", "coprime"),
                   help="coprime rescales all four check limits to pairwise "
                        "coprime day periods below the horizon, so C and D "
                        "checks actually fire")
    p.add_argument("--application-compatible", action="store_true",
                    help="emit only certificates representable by the current "
                        "flight-triggered TAP MILP")


def _apply_generation_flags(cfg, args):
    if getattr(args, "root_seed", None) is not None:
        cfg.root_seed = args.root_seed
    if getattr(args, "topology", None):
        cfg.route_topology = args.topology
    if getattr(args, "cost_model", None):
        cfg.cost_model = args.cost_model
    if getattr(args, "legs_per_tail_day", None):
        cfg.legs_per_tail_day = args.legs_per_tail_day
    if getattr(args, "thresholds", None):
        cfg.threshold_mode = args.thresholds
    if getattr(args, "application_compatible", False):
        cfg.application_compatible = True
    return cfg.validate()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="fore-benchgen")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="build one instance")
    _add_generation_flags(g)
    g.add_argument("--replicate", type=int, default=1)
    g.add_argument("--out-dir", default="instances")
    g.add_argument("--format", nargs="+", choices=("json", "csv", "zip"),
                   default=["json"])
    g.add_argument("--perturb", type=int, default=0, metavar="ITERATIONS",
                   help="run the feasibility-preserving Metropolis walk")
    g.add_argument("--pool", type=int, default=0, metavar="N",
                   help="also emit N distinct certified-feasible schedules "
                        "ranked by cost, for checking a MILP objective")
    g.add_argument("--plant-optimum", action="store_true",
                   help="reprice so the reference schedule is provably the "
                        "least-cost one, giving an exact ground-truth optimum")
    g.add_argument("--optimum-margin", type=float, default=0.04)
    g.add_argument("--no-metrics", action="store_true")

    v = sub.add_parser("validate", help="check an instance and certificate")
    v.add_argument("instance"); v.add_argument("--solution")
    v.add_argument("--lenient-thresholds", action="store_true",
                   help="report threshold breaches as warnings, not errors")

    m = sub.add_parser("metrics", help="score an existing instance")
    m.add_argument("instance"); m.add_argument("--solution", required=True)

    p = sub.add_parser("perturb", help="walk an existing certificate")
    p.add_argument("instance"); p.add_argument("--solution", required=True)
    p.add_argument("--iterations", type=int, default=4000)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--max-segment", type=int, default=8)
    p.add_argument("--objective", choices=("complexity", "cost", "mixed"),
                   default="complexity")
    p.add_argument("--out-dir", default="instances")

    b = sub.add_parser("benchmark", help="factorial sweep")
    _add_generation_flags(b)
    b.add_argument("--factors", default="config/benchmark.json")
    b.add_argument("--replications", type=int, default=2)
    b.add_argument("--out-dir", default="benchmark")
    b.add_argument("--perturb", type=int, default=0)

    sub.add_parser("self-test")
    args = parser.parse_args(argv)

    if args.command == "generate":
        cfg = _apply_generation_flags(load_config(args.config, args.preset), args)
        instance, certificate, report = generate(cfg, args.replicate)
        stats = None
        if args.perturb:
            certificate, report, stats = perturb(instance, certificate,
                                                 iterations=args.perturb)
            instance["Validation"] = report
        if args.plant_optimum:
            instance, certificate = plant_optimum(instance, certificate,
                                                  margin=args.optimum_margin)
            report = validate(instance, certificate)
            instance["Validation"] = report
        metrics = None if args.no_metrics else compute_metrics(instance, certificate)
        pool = solution_pool(instance, certificate, size=args.pool) if args.pool else None
        files = export(instance, certificate, report, args.out_dir,
                       args.format, metrics=metrics, pool=pool)
        out = {"files": files, "validation": report}
        if stats:
            out["perturbation"] = stats
        if metrics:
            out["complexity_index"] = metrics["composite"]["complexity_index"]
            out["subscores"] = metrics["composite"]["subscores"]
            out["check_types_active"] = \
                metrics["B_constraint_tightness"]["check_types_active"]
        if instance.get("Known_Optimum"):
            out["known_optimum"] = instance["Known_Optimum"]
        if pool:
            out["solution_pool"] = {k: v for k, v in pool.items()
                                    if k != "solutions"}
        print(json.dumps(out, indent=2))
        return report["feasibility_status"] == "FAIL"

    if args.command == "validate":
        instance = json.loads(Path(args.instance).read_text())
        solution = (json.loads(Path(args.solution).read_text())
                    if args.solution else None)
        report = validate(instance, solution,
                          strict_thresholds=not args.lenient_thresholds)
        print(json.dumps(report, indent=2))
        return report["feasibility_status"] == "FAIL"

    if args.command == "metrics":
        instance = json.loads(Path(args.instance).read_text())
        solution = json.loads(Path(args.solution).read_text())
        print(json.dumps(compute_metrics(instance, solution), indent=2))
        return 0

    if args.command == "perturb":
        instance = json.loads(Path(args.instance).read_text())
        solution = json.loads(Path(args.solution).read_text())
        before = compute_metrics(instance, solution)
        cert, report, stats = perturb(instance, solution,
                                      iterations=args.iterations,
                                      seed=args.seed,
                                      max_segment=args.max_segment,
                                      objective=args.objective)
        after = compute_metrics(instance, cert)
        files = export(instance, cert, report, args.out_dir, ["json"],
                       metrics=after)
        print(json.dumps({"files": files, "validation": report,
                          "perturbation": stats,
                          "complexity_index_before":
                              before["composite"]["complexity_index"],
                          "complexity_index_after":
                              after["composite"]["complexity_index"]}, indent=2))
        return report["feasibility_status"] == "FAIL"

    if args.command == "benchmark":
        cfg = _apply_generation_flags(load_config(args.config, args.preset), args)
        factors = json.loads(Path(args.factors).read_text())
        rows = benchmark(cfg, factors, args.replications, args.out_dir,
                         perturb_iterations=args.perturb)
        print(f"generated {len(rows)} benchmark instances")
        return 0

    # ---- self-test
    cfg = preset("validation", root_seed=17)
    a, ca, ra = generate(cfg); b, cb, rb = generate(cfg)
    assert a == b and ca == cb, "generation is not deterministic"
    assert ra["feasibility_status"] == "PASS", ra["errors"][:3]

    # every preset must certify, under EVERY topology and cost model
    for name in PRESETS:
        for topo in ("out_and_back", "tours", "euler"):
            c2 = preset(name, route_topology=topo, cost_model="factor")
            inst, cert, rep = generate(c2, 1)
            assert rep["feasibility_status"] == "PASS", \
                f"{name}/{topo}: {rep['errors'][:2]}"

    # Euler mode: every day's arc set must be balanced and must actually
    # decompose, verified from the PUBLISHED flights rather than trusted from
    # the generator - and aircraft must genuinely reposition, or the
    # decomposition bought nothing.
    for name in PRESETS:
        ec = preset(name, route_topology="euler", threshold_mode="coprime")
        einst, ecert, erep = generate(ec, 1)
        assert erep["feasibility_status"] == "PASS", f"{name}: {erep['errors'][:2]}"
        emet = compute_metrics(einst, ecert)["D_structure_symmetry"]
        assert emet["max_daily_imbalance"] == 0, \
            f"{name}: unbalanced day, imbalance {emet['max_daily_imbalance']}"
        assert emet["eulerian_balanced_day_fraction"] == 1.0, name
        assert emet["eulerian_decomposing_day_fraction"] == 1.0, \
            f"{name}: a balanced day failed to decompose"
        assert emet["distinct_overnight_stations_per_tail"] > 1.0, \
            f"{name}: aircraft never repositioned"
        audit = einst["Generator"]["euler_audit"]
        assert audit["days_balanced"] == audit["days"] == audit["days_decomposing"]

    # the walk must preserve feasibility and must actually move
    cfg = preset("small", route_topology="tours", cost_model="factor")
    inst, cert, rep = generate(cfg)
    new_cert, new_rep, stats = perturb(inst, cert, iterations=3000, seed=11)
    assert new_rep["feasibility_status"] == "PASS", new_rep["errors"][:3]
    assert stats["accepted"] > 0, "walk never moved"
    assert stats["hamming_from_planted"] > 0, "walk returned the planted plan"

    # a deliberately corrupted certificate must be REJECTED
    broken = json.loads(json.dumps(new_cert))
    first = inst["Flights"][0][0]
    others = [t for t in inst["Aircrafts"] if t != broken["assignment"][str(first)]]
    broken["assignment"][str(first)] = others[0]
    assert validate(inst, broken)["feasibility_status"] == "FAIL", \
        "validator accepted a corrupted certificate"

    # metrics must be computable and bounded
    met = compute_metrics(inst, new_cert)
    assert 0 <= met["composite"]["complexity_index"] <= 1

    # coprime thresholds must make EVERY check type fire, on every preset
    for name in PRESETS:
        cc = preset(name, threshold_mode="coprime", route_topology="tours")
        ci, cc2, cr = generate(cc, 1)
        assert cr["feasibility_status"] == "PASS", f"{name}: {cr['errors'][:2]}"
        fired = Counter(e["check"] for e in cc2["maintenance_events"])
        assert all(fired.get(c, 0) > 0 for c in CHECKS), \
            f"{name}: checks that never fired: " \
            f"{[c for c in CHECKS if not fired.get(c)]}"
        periods = ci["Generator"]["check_periods_days"]
        vals = list(periods.values())
        for x in range(len(vals)):
            for y in range(x + 1, len(vals)):
                assert math.gcd(vals[x], vals[y]) == 1, \
                    f"{name}: periods {vals[x]} and {vals[y]} share a factor"

    # the solution pool must hold several DISTINCT, individually certified
    # schedules at DISTINCT costs, or it cannot discriminate a MILP result
    cfg = preset("small", threshold_mode="coprime", route_topology="tours",
                 cost_model="factor")
    inst, cert, rep = generate(cfg)
    pool = solution_pool(inst, cert, size=6, iterations=2500)
    assert pool["n_distinct_solutions"] >= 3, pool["n_distinct_solutions"]
    assert pool["cost_spread"] > 0, "all pool solutions cost the same"
    costs = [e["cost"] for e in pool["solutions"]]
    assert costs == sorted(costs), "pool is not ranked by cost"
    for entry in pool["solutions"]:
        single = {"assignment": entry["assignment"],
                  "maintenance_events": entry["maintenance_events"]}
        assert validate(inst, single)["feasibility_status"] == "PASS", \
            f"pool solution {entry['rank']} does not certify"
    assert pool["best_known_cost"] >= pool["lower_bound"], "bound violated"

    # a planted optimum must be exact, attained, and unbeatable
    inst, cert = plant_optimum(inst, cert)
    assert validate(inst, cert)["feasibility_status"] == "PASS"
    known = inst["Known_Optimum"]
    assert known["is_tight"], "planted optimum does not attain its bound"
    planted_pool = solution_pool(inst, cert, size=4, iterations=2000)
    assert planted_pool["best_known_cost"] >= known["objective"] - 1e-6, \
        "a feasible schedule beat the supposed optimum"
    assert planted_pool["optimum_is_proven"]

    print("PASS: determinism; all presets certify under all three topologies; "
          "every Euler day is balanced, decomposes and repositions aircraft; the "
          "walk preserves feasibility while moving "
          f"{stats['hamming_fraction']:.0%} of legs; corrupted certificates are "
          "rejected; metrics in range; coprime periods are pairwise coprime and "
          "fire all four check types on every preset; solution pools hold "
          f"{pool['n_distinct_solutions']} distinct certified schedules spanning "
          f"{pool['cost_spread']:.0f} in cost; planted optima are provably tight")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
