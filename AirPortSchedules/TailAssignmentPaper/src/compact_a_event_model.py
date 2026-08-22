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
    Objective,
    Set,
    Var,
    minimize,
    value,
)

from .model import MILP_Sheduler
from .event_model import EventMILPScheduler


class CompactAEventMILPScheduler(EventMILPScheduler):
    """A-check-only event model with timestamp-based state propagation."""

    CHECK_LIST = ("A",)
    HOUR_CHECKS = ("A",)
    CALENDAR_CHECKS = ()
    FORMULATION_ID = "compact_a_event"


class OrderedHourEventMILPScheduler(MILP_Sheduler):
    """Hour-check event model using chronological prefix states instead of w arcs."""

    CHECK_LIST = ("A",)
    HOUR_CHECKS = ("A",)
    CALENDAR_CHECKS = ()
    FORMULATION_ID = "ordered_hour_event"

    def build_model(self, overlap_mode='clique', tight_state_big_m=True):
        model = ConcreteModel(name=self.FORMULATION_ID)
        self.model = model
        model.F = Set(initialize=self.flight_ids, ordered=True)
        model.P = Set(initialize=sorted(self.aircraft_ids), ordered=True)
        model.A = Set(initialize=self.airports, ordered=True)
        model.MA = Set(initialize=self.maint_airports, ordered=True)
        model.C = Set(initialize=self.CHECK_LIST, ordered=True)
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
        aircraft_ordered_flights = {
            aircraft: sorted(
                self._x_flights_for_aircraft(aircraft),
                key=lambda flight: (
                    self.flight_data[flight]["departureTime"], flight
                ),
            )
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
        self._add_ordered_maintenance(
            model,
            aircraft_ordered_flights,
            tight_state_big_m=tight_state_big_m,
        )
        return model

    def _add_ordered_maintenance(self, model, aircraft_ordered_flights, tight_state_big_m=True):
        model.c5_event = ConstraintList()
        for flight, aircraft, check in model.Z:
            model.c5_event.add(model.z[flight, aircraft, check] <= model.x[flight, aircraft])

        model.c6_event = ConstraintList()
        for flight in self.maint_flight_ids:
            for aircraft in self._x_aircrafts_for_flight(flight):
                events = [
                    model.z[flight, aircraft, check]
                    for check in self.CHECK_LIST
                    if (flight, aircraft, check) in model.Z
                ]
                if events:
                    model.c6_event.add(sum(events) <= 1)

        model.c8_event = ConstraintList()
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
                                model.c8_event.add(
                                    model.x[following, aircraft]
                                    + model.z[trigger, aircraft, check]
                                    <= 1
                                )

        model.c9_event = ConstraintList()
        for airport in self.maint_airports:
            capacity = self.station_cap.get(airport, 0)
            checkpoints = sorted(
                {
                    self.flight_data[flight]["arrivalTime"]
                    for flight in self.maint_flight_ids
                    if self.flight_data[flight]["destination"] == airport
                }
                | {
                    self.flight_data[flight]["arrivalTime"] + self.check_dur[check]
                    for flight in self.maint_flight_ids
                    if self.flight_data[flight]["destination"] == airport
                    for check in self.CHECK_LIST
                }
            )
            for timestamp in checkpoints:
                active = [
                    model.z[flight, aircraft, check]
                    for flight, aircraft, check in model.Z
                    if self.flight_data[flight]["destination"] == airport
                    and self.flight_data[flight]["arrivalTime"] <= timestamp
                    < self.flight_data[flight]["arrivalTime"] + self.check_dur[check]
                ]
                if active:
                    model.c9_event.add(sum(active) <= capacity)

        model.c11_state = ConstraintList()
        state_limit = {
            check: self.check_hrs[check] * 60.0 for check in self.HOUR_CHECKS
        }
        for aircraft in self.aircraft_ids:
            flights = aircraft_ordered_flights[aircraft]
            for position, flight in enumerate(flights):
                duration = self.flight_data[flight]["duration"]
                assigned = model.x[flight, aircraft]
                for check in self.HOUR_CHECKS:
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

                    model.c11_state.add(state >= previous - m_eq * assigned)
                    model.c11_state.add(state <= previous + m_eq * assigned)
                    model.c11_state.add(
                        state >= previous + duration - m_flow * (1 - assigned) - m_flow * checked
                    )
                    model.c11_state.add(
                        state <= previous + duration + m_flow * (1 - assigned) + m_flow * checked
                    )
                    model.c11_state.add(
                        state <= duration * checked + threshold * (assigned - checked)
                        + m_unassigned * (1 - assigned)
                    )
                    model.c11_state.add(
                        previous + duration
                        <= threshold + m_threshold * (1 - assigned)
                    )
                    model.c11_state.add(state <= state_ub)

        if self.CALENDAR_CHECKS:
            self._add_ordered_calendar_limits(model)

    def _add_ordered_calendar_limits(self, model):
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
