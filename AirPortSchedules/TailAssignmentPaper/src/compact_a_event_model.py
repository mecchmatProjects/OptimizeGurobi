"""Compact A-check-only event formulation.

This prototype keeps explicit route arcs ``w[i, l, j]`` and the exact event
state machinery from :mod:`src.event_model`, but instantiates only A checks.
It is intentionally separate from the full A/B/C/D formulation so its parity
with the A-only legacy model can be tested before extending the hierarchy.
"""

from pyomo.environ import (
    Binary,
    ConcreteModel,
    ConstraintList,
    NonNegativeReals,
    NonNegativeIntegers,
    Objective,
    Set,
    Var,
    minimize,
    value,
)

from .model import MILP_Sheduler
from .event_model import EventMILPScheduler


def _peak_concurrency(windows):
    """Largest number of half-open windows that can be simultaneously active."""
    deltas = []
    for low, high in windows:
        deltas.append((low, 1))
        deltas.append((high, -1))
    peak = current = 0
    for _, step in sorted(deltas):
        current += step
        peak = max(peak, current)
    return peak


class CompactAEventMILPScheduler(EventMILPScheduler):
    """A-check-only successor-arc prototype retained for comparison tests.

    The paper-facing ordered E1-E15 implementation is
    :class:`OrderedAEventMILPScheduler` below.
    """

    CHECK_LIST = ("A",)
    HOUR_CHECKS = ("A",)
    CALENDAR_CHECKS = ()
    FORMULATION_ID = "compact_a_event"


class OrderedHourEventMILPScheduler(MILP_Sheduler):
    """Event E1-E15 model using chronological prefix states instead of w arcs."""

    CHECK_LIST = ("A",)
    HOUR_CHECKS = ("A",)
    CALENDAR_CHECKS = ()
    FORMULATION_ID = "ordered_hour_event"
    INCLUDE_EVENT_COUNT = True
    INCLUDE_TYPE_EXCLUSIVITY = True
    INCLUDE_STATE_BOUND_ROW = True
    DEDUPLICATE_CAPACITY_ROWS = False
    NATIVE_STATE_BOUNDS = False
    FLEXIBLE_MAINTENANCE = False
    MAX_MAINT_DEFER = 1440.0

    def build_model(
        self,
        overlap_mode='both',
        tight_state_big_m=True,
        local_state_indexing=True,
        calendar_candidate_pruning=True,
    ):
        model = ConcreteModel(name=self.FORMULATION_ID)
        self.model = model
        model.F = Set(initialize=self.flight_ids, ordered=True)
        model.P = Set(initialize=sorted(self.aircraft_ids), ordered=True)
        model.A = Set(initialize=self.airports, ordered=True)
        model.MA = Set(initialize=self.maint_airports, ordered=True)
        model.C = Set(initialize=self.CHECK_LIST, ordered=True)
        if self.INCLUDE_EVENT_COUNT:
            model.D = Set(
                initialize=sorted(
                    {
                        int(self.flight_data[flight]["arrivalTime"] // self.DAY_SHIFT)
                        for flight in self.flight_ids
                    }
                ),
                ordered=True,
            )
        model.X = Set(
            dimen=2,
            initialize=(
                (flight, aircraft)
                for flight in self.flight_ids
                for aircraft in self._x_aircrafts_for_flight(flight)
            ),
        )
        model.Z = Set(
            dimen=3,
            initialize=(
                (flight, aircraft, check)
                for flight in self.maint_flight_ids
                for aircraft in self._x_aircrafts_for_flight(flight)
                for check in self.CHECK_LIST
            ),
        )
        global_ordered_flights = sorted(
            self.flight_ids,
            key=lambda flight: (
                self.flight_data[flight]["departureTime"], flight
            ),
        )
        if local_state_indexing:
            aircraft_ordered_flights = {
                aircraft: sorted(
                    self._x_flights_for_aircraft(aircraft),
                    key=lambda flight: (
                        self.flight_data[flight]["departureTime"], flight
                    ),
                )
                for aircraft in self.aircraft_ids
            }
        else:
            aircraft_ordered_flights = {
                aircraft: global_ordered_flights
                for aircraft in self.aircraft_ids
            }
        model.Q = Set(
            dimen=3,
            initialize=(
                (position, aircraft, check)
                for aircraft in self.aircraft_ids
                for position in range(len(aircraft_ordered_flights[aircraft]))
                for check in self.HOUR_CHECKS
            ),
        )
        model.x = Var(model.X, domain=Binary, initialize=0)
        model.z = Var(model.Z, domain=Binary, initialize=0)
        if self.NATIVE_STATE_BOUNDS:
            def state_bounds(_model, _position, aircraft, check):
                threshold = self.check_hrs[check] * 60.0
                initial = self.init_check_hrs[check][aircraft] * 60.0
                return 0.0, max(threshold, initial)

            model.q = Var(
                model.Q,
                domain=NonNegativeReals,
                bounds=state_bounds,
                initialize=0,
            )
        else:
            model.q = Var(model.Q, domain=NonNegativeReals, initialize=0)
        if self.INCLUDE_EVENT_COUNT:
            model.event_count = Var(
                model.P,
                model.D,
                domain=NonNegativeIntegers,
                initialize=0,
            )

        model.obj = Objective(
            expr=(
                sum(self._flight_cost(flight, aircraft) * model.x[flight, aircraft]
                    for flight, aircraft in model.X)
                + sum(
                    100 * max(1, int(self.check_dur[check] / self.DAY_SHIFT + 0.999999))
                    * model.z[flight, aircraft, check]
                    for flight, aircraft, check in model.Z
                )
            ),
            sense=minimize,
        )
        self._add_c1_coverage(model)
        self._add_c23_turn(model)
        self._add_overlap(model, mode=overlap_mode)
        self._rename_ordered_route_components(model)
        self._add_ordered_maintenance(
            model,
            aircraft_ordered_flights,
            tight_state_big_m=tight_state_big_m,
            local_state_indexing=local_state_indexing,
            calendar_candidate_pruning=calendar_candidate_pruning,
        )
        return model

    @staticmethod
    def _rename_ordered_route_components(model):
        """Expose the ordered formulation's route rows under E-family names."""
        for old_name, new_name in (
            ("c1", "e4_coverage"),
            ("c23", "e5_e6_continuity_turn"),
            ("c4_pairwise_overlap", "e7_pairwise_overlap"),
            ("c5_clique_overlap", "e7_clique_strengthening"),
        ):
            component = getattr(model, old_name, None)
            if component is not None:
                model.del_component(old_name)
                model.add_component(new_name, component)

    def _add_ordered_maintenance(
        self,
        model,
        aircraft_ordered_flights,
        tight_state_big_m=True,
        local_state_indexing=True,
        calendar_candidate_pruning=True,
    ):
        model.e8_event_assignment = ConstraintList()
        for flight, aircraft, check in model.Z:
            model.e8_event_assignment.add(model.z[flight, aircraft, check] <= model.x[flight, aircraft])

        # C11 aggregation without a binary day indicator: multiple events on
        # one calendar day remain representable instead of being forbidden.
        if self.INCLUDE_EVENT_COUNT:
            model.c11_event_count = ConstraintList()
            for aircraft in model.P:
                for day in model.D:
                    model.c11_event_count.add(
                        model.event_count[aircraft, day]
                        == sum(
                            model.z[flight, aircraft, check]
                            for flight, candidate_aircraft, check in model.Z
                            if candidate_aircraft == aircraft
                            and int(
                                self.flight_data[flight]["arrivalTime"] // self.DAY_SHIFT
                            )
                            == day
                        )
                    )

        if self.INCLUDE_TYPE_EXCLUSIVITY:
            model.event_type_exclusivity = ConstraintList()
            for flight in self.maint_flight_ids:
                for aircraft in self._x_aircrafts_for_flight(flight):
                    events = [
                        model.z[flight, aircraft, check]
                        for check in self.CHECK_LIST
                        if (flight, aircraft, check) in model.Z
                    ]
                    if events:
                        model.event_type_exclusivity.add(sum(events) <= 1)

        if self.FLEXIBLE_MAINTENANCE:
            self._add_flexible_maintenance_timing(model)
        else:
            self._add_immediate_maintenance_timing(model)

        model.e9_e13_prefix_state = ConstraintList()
        state_limit = {
            check: self.check_hrs[check] * 60.0 for check in self.HOUR_CHECKS
        }
        for aircraft in self.aircraft_ids:
            flights = aircraft_ordered_flights[aircraft]
            for position, flight in enumerate(flights):
                duration = self.flight_data[flight]["duration"]
                has_arc = (flight, aircraft) in model.X
                assigned = model.x[flight, aircraft] if has_arc else 0
                for check in self.HOUR_CHECKS:
                    if not has_arc:
                        initial = self.init_check_hrs[check][aircraft] * 60.0
                        previous = (
                            initial
                            if position == 0
                            else model.q[position - 1, aircraft, check]
                        )
                        state = model.q[position, aircraft, check]
                        model.e9_e13_prefix_state.add(state == previous)
                        continue
                    checked = sum(
                        model.z[flight, aircraft, reset_check]
                        for reset_check in self.CHECK_HIERARCHY[check]
                        if reset_check in self.CHECK_LIST
                        and (flight, aircraft, reset_check) in model.Z
                    )
                    previous = (
                        self.init_check_hrs[check][aircraft] * 60.0
                        if position == 0
                        else model.q[position - 1, aircraft, check]
                    )
                    state = model.q[position, aircraft, check]
                    threshold = state_limit[check]
                    initial = self.init_check_hrs[check][aircraft] * 60.0
                    state_ub = max(threshold, initial)
                    if tight_state_big_m:
                        m_eq = state_ub
                        m_flow = state_ub + duration
                        m_unassigned = state_ub
                        m_threshold = max(0.0, state_ub + duration - threshold)
                    else:
                        coarse = state_ub + duration
                        m_eq = coarse
                        m_flow = coarse
                        m_unassigned = coarse
                        m_threshold = coarse

                    model.e9_e13_prefix_state.add(state >= previous - m_eq * assigned)
                    model.e9_e13_prefix_state.add(state <= previous + m_eq * assigned)
                    model.e9_e13_prefix_state.add(
                        state >= previous + duration - m_flow * (1 - assigned) - m_flow * checked
                    )
                    model.e9_e13_prefix_state.add(
                        state <= previous + duration + m_flow * (1 - assigned) + m_flow * checked
                    )
                    model.e9_e13_prefix_state.add(
                        state <= threshold * (assigned - checked)
                        + m_unassigned * (1 - assigned)
                    )
                    model.e9_e13_prefix_state.add(
                        previous + duration
                        <= threshold + m_threshold * (1 - assigned)
                    )
                    if self.INCLUDE_STATE_BOUND_ROW:
                        model.e9_e13_prefix_state.add(state <= state_ub)

        if self.CALENDAR_CHECKS:
            self._add_ordered_calendar_limits(
                model,
                candidate_pruning=calendar_candidate_pruning,
            )

    def _add_immediate_maintenance_timing(self, model):
        """E14-E15: every event starts immediately after its triggering flight."""
        model.e14_maintenance_block = ConstraintList()
        for trigger in self.maint_flight_ids:
            trigger_data = self.flight_data[trigger]
            for aircraft in self._x_aircrafts_for_flight(trigger):
                for following in self._f_dep_window(
                    trigger_data["destination"],
                    trigger_data["arrivalTime"],
                    trigger_data["arrivalTime"] + max(
                        self.check_dur[check] for check in self.CHECK_LIST
                    ) + self.MIN_TURN,
                ):
                    if self._x_has_arc(following, aircraft):
                        for check in self.CHECK_LIST:
                            if self.flight_data[following]["departureTime"] < (
                                trigger_data["arrivalTime"]
                                + self.check_dur[check]
                                + self.MIN_TURN
                            ):
                                model.e14_maintenance_block.add(
                                    model.x[following, aircraft]
                                    + model.z[trigger, aircraft, check]
                                    <= 1
                                )

        model.e15_maintenance_capacity = ConstraintList()
        for airport in self.maint_airports:
            capacity = self.station_cap.get(airport, 0)
            emitted_capacity_rows = set()
            # E15 follows the paper's ordered-trigger indexing: each r is a
            # possible immediate-start event time, and active event flights i
            # are selected by the displayed [arrival(r), arrival(r)+delta_A)
            # window over their departure timestamps.
            for trigger in model.F:
                trigger_arrival = self.flight_data[trigger]["arrivalTime"]
                active_indices = [
                    (flight, aircraft, check)
                    for flight, aircraft, check in model.Z
                    if self.flight_data[flight]["destination"] == airport
                    and trigger_arrival
                    <= self.flight_data[flight]["departureTime"]
                    < trigger_arrival + self.check_dur[check]
                ]
                if not active_indices:
                    continue
                signature = tuple(active_indices)
                if self.DEDUPLICATE_CAPACITY_ROWS:
                    if signature in emitted_capacity_rows or len(signature) <= capacity:
                        continue
                    emitted_capacity_rows.add(signature)
                model.e15_maintenance_capacity.add(
                    sum(model.z[index] for index in active_indices) <= capacity
                )

    def _add_flexible_maintenance_timing(self, model):
        """E14_flex-E16_flex: the maintenance completion offset is a decision.

        ``s[r, j]`` is the offset from the arrival of trigger flight ``i_r`` to the
        completion of the type-A check, so the event occupies
        ``[tI(i_r) + s - delta_A, tI(i_r) + s)``.  Deferral is capped by
        :attr:`MAX_MAINT_DEFER` to keep the E15_flex conflict graph sparse.
        """
        check = self.CHECK_LIST[0]
        duration = self.check_dur[check]
        defer = float(self.MAX_MAINT_DEFER)
        max_offset = duration + defer

        model.s = Var(model.Z, domain=NonNegativeReals, bounds=(0.0, max_offset), initialize=0)

        # E4 assigns each flight to exactly one aircraft, so at most one s[r, *]
        # is nonzero and the per-flight aggregate is the realised offset.
        model.FM = Set(initialize=self.maint_flight_ids, ordered=True)
        model.sigma = Var(model.FM, domain=NonNegativeReals, bounds=(0.0, max_offset), initialize=0)

        events_by_flight = {
            flight: [
                (flight, aircraft, check)
                for aircraft in self._x_aircrafts_for_flight(flight)
                if (flight, aircraft, check) in model.Z
            ]
            for flight in self.maint_flight_ids
        }
        selected = {
            flight: sum(model.z[key] for key in keys) if keys else 0
            for flight, keys in events_by_flight.items()
        }

        model.e16_flex_completion_window = ConstraintList()
        for flight, keys in events_by_flight.items():
            for key in keys:
                model.e16_flex_completion_window.add(model.s[key] >= duration * model.z[key])
                model.e16_flex_completion_window.add(model.s[key] <= max_offset * model.z[key])
            if keys:
                model.e16_flex_completion_window.add(
                    model.sigma[flight] == sum(model.s[key] for key in keys)
                )
            else:
                model.e16_flex_completion_window.add(model.sigma[flight] == 0.0)

        model.e14_flex_maintenance_block = ConstraintList()
        for trigger in self.maint_flight_ids:
            trigger_data = self.flight_data[trigger]
            arrival = trigger_data["arrivalTime"]
            block_limit = arrival + max_offset + self.MIN_TURN
            candidates = self._f_dep_window(
                trigger_data["destination"], arrival, block_limit
            )
            for aircraft in self._x_aircrafts_for_flight(trigger):
                key = (trigger, aircraft, check)
                if key not in model.Z:
                    continue
                for following in candidates:
                    if not self._x_has_arc(following, aircraft):
                        continue
                    departure = self.flight_data[following]["departureTime"]
                    model.e14_flex_maintenance_block.add(
                        arrival + model.s[key] + self.MIN_TURN
                        <= departure
                        + block_limit
                        * (2 - model.x[following, aircraft] - model.z[key])
                    )

        self._add_flexible_capacity(model, selected, duration, defer)

    def _add_flexible_capacity(self, model, selected, duration, defer):
        """E15_flex: disjunctive occupancy rows, emitted only where capacity can bind."""
        model.e15_flex_separation = ConstraintList()
        model.e15_flex_maintenance_capacity = ConstraintList()

        conflict_pairs = []
        conflicts = {}
        capacity_by_flight = {}
        check = self.CHECK_LIST[0]
        for airport in self.maint_airports:
            capacity = self.station_cap.get(airport, 0)
            flights = [
                flight
                for flight in self.maint_flight_ids
                if self.flight_data[flight]["destination"] == airport
                and any(
                    (flight, aircraft, check) in model.Z
                    for aircraft in self._x_aircrafts_for_flight(flight)
                )
            ]
            windows = {
                flight: (
                    self.flight_data[flight]["arrivalTime"],
                    self.flight_data[flight]["arrivalTime"] + duration + defer,
                )
                for flight in flights
            }
            if _peak_concurrency(windows.values()) <= capacity:
                continue
            for outer, first in enumerate(flights):
                for second in flights[outer + 1:]:
                    low_a, high_a = windows[first]
                    low_b, high_b = windows[second]
                    if low_a < high_b and low_b < high_a:
                        conflict_pairs.append((first, second))
                        conflicts.setdefault(first, []).append(second)
                        conflicts.setdefault(second, []).append(first)
            for flight in flights:
                capacity_by_flight[flight] = capacity

        if not conflict_pairs:
            return

        model.SPAIR = Set(dimen=2, initialize=conflict_pairs, ordered=True)
        model.flex_overlap = Var(model.SPAIR, domain=Binary, initialize=0)
        model.flex_order = Var(model.SPAIR, domain=Binary, initialize=0)

        horizon_end = max(
            self.flight_data[flight]["arrivalTime"] for flight in self.flight_ids
        )
        big_m = horizon_end + 2.0 * (duration + defer)

        def completion(flight):
            return self.flight_data[flight]["arrivalTime"] + model.sigma[flight]

        for first, second in conflict_pairs:
            overlap = model.flex_overlap[first, second]
            order = model.flex_order[first, second]
            slack = (
                overlap
                + (1 - selected[first])
                + (1 - selected[second])
            )
            model.e15_flex_separation.add(
                completion(second) - completion(first)
                >= duration - big_m * (order + slack)
            )
            model.e15_flex_separation.add(
                completion(first) - completion(second)
                >= duration - big_m * ((1 - order) + slack)
            )
            model.e15_flex_separation.add(overlap <= selected[first])
            model.e15_flex_separation.add(overlap <= selected[second])

        for flight, neighbours in conflicts.items():
            capacity = capacity_by_flight[flight]
            terms = [
                model.flex_overlap[flight, other]
                if (flight, other) in model.SPAIR
                else model.flex_overlap[other, flight]
                for other in neighbours
            ]
            model.e15_flex_maintenance_capacity.add(
                sum(terms)
                <= (capacity - 1) + len(terms) * (1 - selected[flight])
            )

    def _add_ordered_calendar_limits(self, model, candidate_pruning=True):
        """Enforce C/D check deadlines directly on timestamped z events."""
        model.c14_calendar = ConstraintList()
        horizon_end = max(
            self.flight_data[flight]["arrivalTime"] for flight in self.flight_ids
        )
        for aircraft in self.aircraft_ids:
            for requirement in self.CALENDAR_CHECKS:
                limit = self.check_days[requirement] * self.DAY_SHIFT
                elapsed = self.init_check_hrs[requirement][aircraft] * 60.0
                first_deadline = limit - elapsed
                qualifying = [
                    (flight, check)
                    for flight, candidate_aircraft, check in model.Z
                    if candidate_aircraft == aircraft
                    and check in self.CHECK_HIERARCHY[requirement]
                ]

                if candidate_pruning:
                    by_flight = {}
                    for flight, check in qualifying:
                        by_flight.setdefault(flight, []).append(check)

                    first_events = [
                        sum(model.z[flight, aircraft, check] for check in checks)
                        for flight, checks in by_flight.items()
                        if self.flight_data[flight]["arrivalTime"] <= first_deadline
                    ]
                else:
                    by_flight = None
                    first_events = [
                        model.z[flight, aircraft, check]
                        for flight, check in qualifying
                        if self.flight_data[flight]["arrivalTime"] <= first_deadline
                    ]

                if first_deadline <= horizon_end:
                    if not first_events:
                        raise ValueError(
                            f"No reachable {requirement} event meets the initial deadline "
                            f"for aircraft {aircraft}"
                        )
                    model.c14_calendar.add(sum(first_events) >= 1)

                if candidate_pruning:
                    for flight, checks in by_flight.items():
                        start = self.flight_data[flight]["arrivalTime"]
                        if start + limit > horizon_end:
                            continue
                        rhs = sum(model.z[flight, aircraft, check] for check in checks)
                        following = [
                            sum(model.z[next_flight, aircraft, next_check] for next_check in next_checks)
                            for next_flight, next_checks in by_flight.items()
                            if start
                            < self.flight_data[next_flight]["arrivalTime"]
                            <= start + limit
                        ]
                        model.c14_calendar.add(sum(following) >= rhs)
                else:
                    for flight, check in qualifying:
                        start = self.flight_data[flight]["arrivalTime"]
                        if start + limit > horizon_end:
                            continue
                        following = [
                            model.z[next_flight, aircraft, next_check]
                            for next_flight, next_check in qualifying
                            if start
                            < self.flight_data[next_flight]["arrivalTime"]
                            <= start + limit
                        ]
                        model.c14_calendar.add(
                            sum(following) >= model.z[flight, aircraft, check]
                        )

    def print_report(self, out_path=None, summary=None):
        """Print the compact model's solved assignment and A events."""
        lines = ["", "=== Ordered Hour Event MILP Aircraft Assignment Report ==="]
        if summary:
            lines.extend([
                f"  Status : {summary['status']}",
                f"  Vars   : {summary['n_vars']}   Constraints: {summary['n_cons']}",
                f"  Obj    : {summary['obj']}",
            ])
        lines.append("\n--- Assignment ---")
        for flight, aircraft in self.model.X:
            if value(self.model.x[flight, aircraft]) > 0.5:
                lines.append(f"  Flight {flight:4d}  -> Aircraft {aircraft}")
        lines.append("\n--- A maintenance events ---")
        for flight, aircraft, check in self.model.Z:
            if value(self.model.z[flight, aircraft, check]) > 0.5:
                lines.append(f"  Aircraft {aircraft} {check} after flight {flight}")
        text = "\n".join(lines)
        print(text)
        if out_path:
            Path(out_path).write_text(text, encoding="utf-8")


class OrderedAEventMILPScheduler(OrderedHourEventMILPScheduler):
    """A-check-only ordered event formulation."""

    CHECK_LIST = ("A",)
    HOUR_CHECKS = ("A",)
    FORMULATION_ID = "ordered_a_event"


class PaperEventBasedMILPScheduler(OrderedAEventMILPScheduler):
    """Paper-facing identifier for the ordered A-only event formulation."""

    FORMULATION_ID = "event_based"


class OptimizedPaperEventBasedMILPScheduler(OrderedAEventMILPScheduler):
    """Equivalent A-only E1-E15 implementation with redundant rows removed."""

    FORMULATION_ID = "event_based_optimized"
    INCLUDE_EVENT_COUNT = False
    INCLUDE_TYPE_EXCLUSIVITY = False
    INCLUDE_STATE_BOUND_ROW = False
    DEDUPLICATE_CAPACITY_ROWS = True
    NATIVE_STATE_BOUNDS = True

    def build_model(self, **kwargs):
        kwargs["overlap_mode"] = "clique"
        return super().build_model(**kwargs)


class FlexiblePaperEventBasedMILPScheduler(OptimizedPaperEventBasedMILPScheduler):
    """E1-E13 with deferrable maintenance timing (E14_flex-E16_flex).

    Setting every offset to ``delta_A`` reproduces the immediate-start model, so
    this formulation is a relaxation of ``event_based_optimized``.
    """

    FORMULATION_ID = "event_based_flex"
    FLEXIBLE_MAINTENANCE = True
    MAX_MAINT_DEFER = 1440.0


class OrderedABEventMILPScheduler(OrderedHourEventMILPScheduler):
    """A/B hour-check ordered event formulation with hierarchy resets."""

    CHECK_LIST = ("A", "B")
    HOUR_CHECKS = ("A", "B")
    FORMULATION_ID = "ordered_ab_event"


class OrderedABCDEventMILPScheduler(OrderedHourEventMILPScheduler):
    """Full-hierarchy ordered event prototype with direct C/D deadlines."""

    CHECK_LIST = ("A", "B", "C", "D")
    HOUR_CHECKS = ("A", "B")
    CALENDAR_CHECKS = ("C", "D")
    FORMULATION_ID = "ordered_abcd_event"
