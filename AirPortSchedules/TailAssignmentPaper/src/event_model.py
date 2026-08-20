"""Event-based tail-assignment MILP without day-indexed decision variables.

The model keeps the legacy JSON input format but replaces ``z[i,j,d,c]``,
``y[j,d,c]``, and ``mega[j,d,c]`` with sparse route arcs ``y[i,l,j]`` and
maintenance events ``z[i,j,c]``. Absolute flight timestamps provide all
calendar information.
"""

import bisect
import math
import os

from pyomo.environ import (
    Binary,
    ConcreteModel,
    Constraint,
    ConstraintList,
    Expression,
    NonNegativeReals,
    Objective,
    Set,
    Var,
    minimize,
    value as pyo_value,
)

try:
    from .model import MILP_Sheduler
except ImportError:
    from model import MILP_Sheduler


class EventMILPScheduler(MILP_Sheduler):
    """Exact-state flight-event formulation from ``docs/update_improve.tex``."""

    FORMULATION_ID = "event_exact_state"

    HOUR_CHECKS = ("A", "B")
    CALENDAR_CHECKS = ("C", "D")

    def __init__(self, data_path, maintenance_airports=None):
        super().__init__(data_path, maintenance_airports=maintenance_airports)
        self.horizon_start = 0.0
        max_arrival = max(
            data["arrivalTime"] for data in self.flight_data.values()
        )
        self.horizon_end = max(
            self.DAY_SHIFT,
            math.ceil(max_arrival / self.DAY_SHIFT) * self.DAY_SHIFT,
        )
        self.route_arcs = self._build_route_arcs()
        self.predecessors = {key: [] for key in self.x_arcs_set}
        self.successors = {key: [] for key in self.x_arcs_set}
        for first, second, aircraft in self.route_arcs:
            self.predecessors[(second, aircraft)].append(first)
            self.successors[(first, aircraft)].append(second)

        self.source_arcs = {
            (flight, aircraft)
            for flight, aircraft in self.x_arcs_set
            if self.flight_data[flight]["origin"] == self.aircraft_init[aircraft]
            and self.flight_data[flight]["departureTime"] >= self.horizon_start
        }
        self.z_arcs = {
            (flight, aircraft, check)
            for flight in self.maint_flight_ids
            for aircraft in self._x_aircrafts_for_flight(flight)
            for check in self.CHECK_LIST
            if self._maintenance_end(flight, check) <= self.horizon_end
        }
        self.maintenance_pairs = sorted(
            {(flight, aircraft) for flight, aircraft, _ in self.z_arcs}
        )
        self.calendar_events = {}
        for aircraft in self.aircraft_ids:
            for check in self.CALENDAR_CHECKS:
                events = [
                    (self.flight_data[flight]["arrivalTime"], flight, check)
                    for flight, candidate_aircraft, candidate_check in self.z_arcs
                    if candidate_aircraft == aircraft
                    and candidate_check == check
                    and self._reachable(flight, aircraft)
                ]
                self.calendar_events[aircraft, check] = sorted(events)
        self.calendar_event_times = {
            key: [event[0] for event in events]
            for key, events in self.calendar_events.items()
        }

    def _build_route_arcs(self):
        arcs = []
        for aircraft in self.aircraft_ids:
            flights = self._x_flights_for_aircraft(aircraft)
            departures_by_origin = {}
            for flight in flights:
                origin = self.flight_data[flight]["origin"]
                departures_by_origin.setdefault(origin, []).append(flight)
            departure_index = {}
            for origin, candidates in departures_by_origin.items():
                candidates.sort(
                    key=lambda flight: self.flight_data[flight]["departureTime"]
                )
                departure_index[origin] = (
                    [self.flight_data[flight]["departureTime"] for flight in candidates],
                    candidates,
                )
            for first in flights:
                first_data = self.flight_data[first]
                departure_times, candidates = departure_index.get(
                    first_data["destination"], ([], [])
                )
                start = bisect.bisect_left(
                    departure_times,
                    first_data["arrivalTime"] + self.MIN_TURN,
                )
                arcs.extend(
                    (first, second, aircraft)
                    for second in candidates[start:]
                    if second != first
                )
        return tuple(arcs)

    def _maintenance_end(self, flight, check):
        return self.flight_data[flight]["arrivalTime"] + self.check_dur[check]

    @staticmethod
    def _initial_hours_big_m(initial, threshold, duration):
        """Return a valid M for an inactive first-flight state link."""
        return max(initial, threshold) + duration

    @staticmethod
    def _route_hours_big_m(threshold, duration):
        """Return valid lower/upper M values for an inactive route arc."""
        lower = threshold + duration
        upper = max(0.0, threshold - duration)
        return lower, upper

    def _qualifying_checks(self, requirement):
        return self.CHECK_HIERARCHY[requirement]

    def _q(self, model, flight, aircraft, requirement):
        return sum(
            model.z[flight, aircraft, check]
            for check in self._qualifying_checks(requirement)
            if (flight, aircraft, check) in self.z_arcs
        )

    def build_model(self):
        """Build the complete event-based C1--C14 formulation."""
        model = ConcreteModel(name=self.FORMULATION_ID)
        self.model = model
        self._add_event_sets_and_variables(model)
        self._add_event_objective(model)
        self._add_event_routing(model)
        self._add_event_maintenance(model)
        self._add_event_hour_limits(model)
        self._add_event_calendar_limits(model)
        return model

    def _add_event_sets_and_variables(self, model):
        model.F = Set(initialize=self.flight_ids, ordered=True)
        model.P = Set(initialize=sorted(self.aircraft_ids), ordered=True)
        model.C = Set(initialize=self.CHECK_LIST, ordered=True)
        model.X = Set(dimen=2, initialize=sorted(self.x_arcs_set))
        model.E = Set(dimen=3, initialize=self.route_arcs)
        model.S = Set(dimen=2, initialize=sorted(self.source_arcs))
        model.Z = Set(dimen=3, initialize=sorted(self.z_arcs))
        model.MP = Set(dimen=2, initialize=self.maintenance_pairs)
        model.U = Set(
            dimen=3,
            initialize=(
                (flight, aircraft, check)
                for flight, aircraft in sorted(self.x_arcs_set)
                for check in self.HOUR_CHECKS
            ),
        )

        model.x = Var(model.X, domain=Binary, initialize=0)
        model.y = Var(model.E, domain=Binary, initialize=0)
        model.first = Var(model.S, domain=Binary, initialize=0)
        model.last = Var(model.X, domain=Binary, initialize=0)
        model.z = Var(model.Z, domain=Binary, initialize=0)
        model.u = Var(model.U, domain=NonNegativeReals, initialize=0)

        def hierarchy_rule(current_model, flight, aircraft, check):
            return self._q(current_model, flight, aircraft, check)

        model.q = Expression(model.MP, model.C, rule=hierarchy_rule)

    def _add_event_objective(self, model):
        def maintenance_weight(check):
            return max(1, math.ceil(self.check_dur[check] / self.DAY_SHIFT))

        model.obj = Objective(
            expr=(
                sum(
                    self._flight_cost(flight, aircraft)
                    * model.x[flight, aircraft]
                    for flight, aircraft in model.X
                )
                + sum(
                    100 * maintenance_weight(check)
                    * model.z[flight, aircraft, check]
                    for flight, aircraft, check in model.Z
                )
            ),
            sense=minimize,
        )

    def _add_event_routing(self, model):
        def coverage_rule(current_model, flight):
            return sum(
                current_model.x[flight, aircraft]
                for aircraft in self._x_aircrafts_for_flight(flight)
            ) == 1

        model.c1_coverage = Constraint(model.F, rule=coverage_rule)

        def predecessor_rule(current_model, flight, aircraft):
            source = (
                current_model.first[flight, aircraft]
                if (flight, aircraft) in self.source_arcs
                else 0
            )
            return source + sum(
                current_model.y[previous, flight, aircraft]
                for previous in self.predecessors[(flight, aircraft)]
            ) == current_model.x[flight, aircraft]

        model.c2_predecessor = Constraint(model.X, rule=predecessor_rule)

        def successor_rule(current_model, flight, aircraft):
            return current_model.last[flight, aircraft] + sum(
                current_model.y[flight, following, aircraft]
                for following in self.successors[(flight, aircraft)]
            ) == current_model.x[flight, aircraft]

        model.c3_successor = Constraint(model.X, rule=successor_rule)

        def one_route_rule(current_model, aircraft):
            return sum(
                current_model.first[flight, aircraft]
                for flight in self.flight_ids
                if (flight, aircraft) in self.source_arcs
            ) <= 1

        model.c4_one_route = Constraint(model.P, rule=one_route_rule)

        def route_balance_rule(current_model, aircraft):
            starts = sum(
                current_model.first[flight, aircraft]
                for flight in self.flight_ids
                if (flight, aircraft) in self.source_arcs
            )
            ends = sum(
                current_model.last[flight, aircraft]
                for flight in self._x_flights_for_aircraft(aircraft)
            )
            return starts == ends

        model.c4_route_balance = Constraint(model.P, rule=route_balance_rule)

    def _add_event_maintenance(self, model):
        model.c5_assignment = ConstraintList()
        for flight, aircraft, check in model.Z:
            model.c5_assignment.add(
                model.z[flight, aircraft, check] <= model.x[flight, aircraft]
            )

        def one_check_rule(current_model, flight, aircraft):
            return sum(
                current_model.z[flight, aircraft, check]
                for check in self.CHECK_LIST
                if (flight, aircraft, check) in self.z_arcs
            ) <= 1

        model.c6_one_check = Constraint(model.MP, rule=one_check_rule)

        model.c8_duration = ConstraintList()
        for first, second, aircraft in model.E:
            departure = self.flight_data[second]["departureTime"]
            for check in self.CHECK_LIST:
                z_key = (first, aircraft, check)
                if (
                    z_key in self.z_arcs
                    and departure < self._maintenance_end(first, check) + self.MIN_TURN
                ):
                    model.c8_duration.add(
                        model.y[first, second, aircraft]
                        + model.z[z_key] <= 1
                    )

        capacity_points = sorted({
            (self.flight_data[flight]["destination"],
             self.flight_data[flight]["arrivalTime"])
            for flight, _, _ in self.z_arcs
        })
        model.CAP = Set(dimen=2, initialize=capacity_points)

        def capacity_rule(current_model, airport, timestamp):
            active = [
                current_model.z[flight, aircraft, check]
                for flight, aircraft, check in self.z_arcs
                if self.flight_data[flight]["destination"] == airport
                and self.flight_data[flight]["arrivalTime"] <= timestamp
                < self._maintenance_end(flight, check)
            ]
            if not active:
                return Constraint.Feasible
            return sum(active) <= self.station_cap[airport]

        model.c9_capacity = Constraint(model.CAP, rule=capacity_rule)

    def _add_event_hour_limits(self, model):
        model.c11_hour_bounds = ConstraintList()
        for flight, aircraft, check in model.U:
            duration = self.flight_data[flight]["duration"]
            threshold = self.check_hrs[check] * 60.0
            model.c11_hour_bounds.add(
                model.u[flight, aircraft, check]
                >= duration * model.x[flight, aircraft]
            )
            model.c11_hour_bounds.add(
                model.u[flight, aircraft, check]
                <= threshold * model.x[flight, aircraft]
            )

        model.c12_hour_flow = ConstraintList()
        for first, second, aircraft in model.E:
            second_duration = self.flight_data[second]["duration"]
            for check in self.HOUR_CHECKS:
                threshold = self.check_hrs[check] * 60.0
                lower_big_m, upper_big_m = self._route_hours_big_m(
                    threshold, second_duration
                )
                reset = (
                    model.q[first, aircraft, check]
                    if (first, aircraft) in self.maintenance_pairs
                    else 0
                )
                model.c12_hour_flow.add(
                    model.u[second, aircraft, check]
                    >= model.u[first, aircraft, check] + second_duration
                    - lower_big_m * (1 - model.y[first, second, aircraft])
                    - threshold * reset
                )
                model.c12_hour_flow.add(
                    model.u[second, aircraft, check]
                    <= model.u[first, aircraft, check] + second_duration
                    + upper_big_m * (1 - model.y[first, second, aircraft])
                    + threshold * reset
                )
                model.c12_hour_flow.add(
                    model.u[second, aircraft, check]
                    <= second_duration
                    + threshold * (2 - model.y[first, second, aircraft] - reset)
                )

        model.c13_initial_hours = ConstraintList()
        for flight, aircraft in model.S:
            duration = self.flight_data[flight]["duration"]
            for check in self.HOUR_CHECKS:
                initial = self.init_check_hrs[check][aircraft] * 60.0
                threshold = self.check_hrs[check] * 60.0
                # Must relax the lower row even when the input history is
                # already overdue; use the larger of history and threshold.
                initial_big_m = self._initial_hours_big_m(
                    initial, threshold, duration
                )
                model.c13_initial_hours.add(
                    model.u[flight, aircraft, check]
                    >= initial + duration
                    - initial_big_m * (1 - model.first[flight, aircraft])
                )
                model.c13_initial_hours.add(
                    model.u[flight, aircraft, check]
                    <= initial + duration
                    + initial_big_m * (1 - model.first[flight, aircraft])
                )

    def _reachable(self, flight, aircraft):
        """Whether x[flight, aircraft] can possibly be 1 given routing: the
        flight must be a source arc for this aircraft, or have at least one
        predecessor arc into it for this aircraft (matches the domain
        implicitly enforced by ``c2_predecessor``). Cost-based x-arc
        eligibility alone (``self.z_arcs``) does not imply this -- a flight
        can be "affordable" for an aircraft that can never actually reach it."""
        return (
            (flight, aircraft) in self.source_arcs
            or bool(self.predecessors.get((flight, aircraft)))
        )

    def _add_event_calendar_limits(self, model):
        model.c14_initial_calendar = ConstraintList()
        model.c14_calendar_chain = ConstraintList()
        for aircraft in self.aircraft_ids:
            for requirement in self.CALENDAR_CHECKS:
                limit = self.check_days[requirement] * self.DAY_SHIFT
                elapsed = self.init_check_hrs[requirement][aircraft] * 60.0
                first_deadline = self.horizon_start + limit - elapsed
                if first_deadline <= self.horizon_end:
                    candidates = [
                        model.z[flight, aircraft, check]
                        for check in self._qualifying_checks(requirement)
                        for arrival, flight, _ in self.calendar_events[aircraft, check]
                        if arrival <= first_deadline
                    ]
                    if candidates:
                        model.c14_initial_calendar.add(sum(candidates) >= 1)
                    else:
                        # No reachable check can meet this aircraft's deadline:
                        # a genuine, aircraft-local infeasibility. Anchor on a
                        # real binary Var forced out of its domain (>=2) so
                        # Pyomo keeps this as a symbolic constraint instead of
                        # collapsing a plain ``0 >= 1`` literal to Python's
                        # ``False`` (which Pyomo's ConstraintList rejects).
                        anchor_key = next(iter(self.z_arcs))
                        model.c14_initial_calendar.add(model.z[anchor_key] >= 2)

                for selected_check in self._qualifying_checks(requirement):
                    events = self.calendar_events[aircraft, selected_check]
                    for start, flight, _ in events:
                        if start + limit > self.horizon_end:
                            continue
                        following = []
                        for next_check in self._qualifying_checks(requirement):
                            next_events = self.calendar_events[aircraft, next_check]
                            next_starts = self.calendar_event_times[aircraft, next_check]
                            first = bisect.bisect_right(next_starts, start)
                            last = bisect.bisect_right(next_starts, start + limit)
                            following.extend(
                                model.z[next_flight, aircraft, next_check]
                                for _, next_flight, _ in next_events[first:last]
                            )
                        model.c14_calendar_chain.add(
                            sum(following) >= model.z[flight, aircraft, selected_check]
                        )

    def print_report(self, out_path=None, summary=None):
        """Print a report with the same summary fields as the legacy model."""
        model = self.model
        lines = ["", "=== Event MILP Aircraft Assignment Report ==="]
        if summary:
            gap = (
                f"{summary['gap'] * 100:.4f}%"
                if summary.get("gap") is not None
                else "-"
            )
            cpu = (
                f"{summary['cpu']:.2f}s"
                if summary.get("cpu") is not None
                else "-"
            )
            lines.extend([
                f"  Status : {summary['status']}",
                f"  Vars   : {summary['n_vars']}   Constraints: {summary['n_cons']}",
                f"  Gap    : {gap}   CPU: {cpu}",
                f"  Obj    : {summary['obj']}",
            ])

        lines.append("\n--- Assignment ---")
        for flight, aircraft in model.X:
            if pyo_value(model.x[flight, aircraft]) > 0.5:
                lines.append(f"  Flight {flight:4d}  -> Aircraft {aircraft}")

        lines.append("\n--- Maintenance ---")
        for flight, aircraft, check in model.Z:
            if pyo_value(model.z[flight, aircraft, check]) > 0.5:
                start = self.flight_data[flight]["arrivalTime"]
                end = self._maintenance_end(flight, check)
                lines.append(
                    f"  Aircraft {aircraft} check {check} after flight {flight} "
                    f"[{start:.0f}, {end:.0f}]"
                )

        if summary and summary.get("obj") is not None:
            lines.append(f"\nTotal cost: {summary['obj']:.2f}")
        text = "\n".join(lines)
        print(text)
        if out_path:
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as output_file:
                output_file.write(text)


def run_event_milp(
    data_path,
    solver_name="cplex",
    time_limit=None,
    tee=False,
    out_path=None,
):
    """Build and solve the event MILP using the legacy summary contract."""
    scheduler = EventMILPScheduler(data_path)
    scheduler.build_model()
    summary = scheduler.solve(
        solver_name=solver_name,
        tee=tee,
        out_path=out_path,
        time_limit=time_limit,
        warm_start=False,
    )
    return scheduler, summary
