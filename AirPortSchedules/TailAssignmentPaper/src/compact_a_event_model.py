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
        model.q = Var(model.Q, domain=NonNegativeReals, initialize=0)
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
            # E15 follows the paper's ordered-trigger indexing: each r is a
            # possible immediate-start event time, and active event flights i
            # are selected by the displayed [arrival(r), arrival(r)+delta_A)
            # window over their departure timestamps.
            for trigger in model.F:
                trigger_arrival = self.flight_data[trigger]["arrivalTime"]
                active = [
                    model.z[flight, aircraft, check]
                    for flight, aircraft, check in model.Z
                    if self.flight_data[flight]["destination"] == airport
                    and trigger_arrival
                    <= self.flight_data[flight]["departureTime"]
                    < trigger_arrival + self.check_dur[check]
                ]
                if active:
                    model.e15_maintenance_capacity.add(sum(active) <= capacity)

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
                    model.e9_e13_prefix_state.add(state <= state_ub)

        if self.CALENDAR_CHECKS:
            self._add_ordered_calendar_limits(
                model,
                candidate_pruning=calendar_candidate_pruning,
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
