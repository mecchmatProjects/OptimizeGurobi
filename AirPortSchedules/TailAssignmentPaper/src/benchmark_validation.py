"""Validation helpers for externally generated TAP benchmark certificates."""

from collections import Counter, defaultdict
import math

from pyomo.core.base.constraint import Constraint
from pyomo.environ import value


DAY_MINUTES = 24 * 60
CHECKS = ("A", "B", "C", "D")
COUNTER_KEYS = {"A": "A", "B": "B", "C": "C_Days", "D": "D_Days"}


def validate_benchmark_certificate(instance, certificate):
    """Validate a complete no-ferry certificate against the shared benchmark contract.

    The result distinguishes an externally feasible certificate from one whose
    maintenance events are representable by the current flight-triggered MILP.
    """
    errors = []
    representability_errors = []
    required = {
        "Aircrafts", "AIRCRAFT_INIT_POS", "Flights", "Cost_Matrix",
        "Maintenance_Thresholds", "Maintenance_Durations",
        "Station_Capacity", "Initial_Checks",
    }
    missing = sorted(required - set(instance))
    if missing:
        return {
            "status": "FAIL",
            "errors": [f"missing instance fields: {', '.join(missing)}"],
            "milp_representable": False,
            "milp_representability_errors": [],
        }

    flights = {flight[0]: flight for flight in instance["Flights"]}
    assignment = certificate.get("assignment", {})
    expected_ids = {str(flight_id) for flight_id in flights}
    if set(assignment) != expected_ids:
        errors.append("certificate must assign every flight exactly once")

    tails = set(instance["Aircrafts"])
    for flight_id, tail in assignment.items():
        if tail not in tails:
            errors.append(f"flight {flight_id} is assigned to unknown aircraft {tail}")

    min_turn = float(instance.get("Parameters", {}).get("Min_Turn_Minutes", 30))
    routes = defaultdict(list)
    for flight_id, tail in assignment.items():
        if flight_id in expected_ids and tail in tails:
            flight = flights[int(flight_id)]
            routes[tail].append({
                "kind": "FLIGHT", "start": float(flight[3]), "end": float(flight[4]),
                "origin": flight[1], "destination": flight[2], "flight_id": flight[0],
            })

    maintenance = certificate.get("maintenance_events", [])
    for event in maintenance:
        tail = event.get("tail")
        check = event.get("check")
        if tail not in tails or check not in CHECKS:
            errors.append("maintenance event has an unknown aircraft or check type")
            continue
        if event.get("station") not in instance["Station_Capacity"]:
            errors.append("maintenance event uses an unknown station")
            continue
        if float(event.get("start", 0)) >= float(event.get("end", 0)):
            errors.append("maintenance event has non-positive duration")
            continue
        routes[tail].append({
            "kind": "MAINT", "start": float(event["start"]), "end": float(event["end"]),
            "origin": event["station"], "destination": event["station"], "check": check,
        })

    occupancy = Counter()
    for event in maintenance:
        if event.get("station") not in instance["Station_Capacity"]:
            continue
        start_day = int(float(event["start"]) // DAY_MINUTES)
        end_day = int(math.ceil(float(event["end"]) / DAY_MINUTES))
        for day in range(start_day, end_day):
            occupancy[event["station"], day] += 1
    for (station, day), count in occupancy.items():
        if count > instance["Station_Capacity"][station]:
            errors.append(f"maintenance capacity exceeded at {station} on day {day}")

    for tail in tails:
        activities = sorted(routes[tail], key=lambda item: (item["start"], item["end"]))
        position = instance["AIRCRAFT_INIT_POS"].get(str(tail))
        previous = None
        for activity in activities:
            if activity["origin"] != position:
                errors.append(f"aircraft {tail} has a station-continuity break")
            if previous is not None:
                required_gap = min_turn if previous["kind"] == activity["kind"] == "FLIGHT" else 0
                if previous["end"] + required_gap > activity["start"]:
                    errors.append(f"aircraft {tail} has an overlapping activity")
            if activity["kind"] == "MAINT":
                day = int(activity["start"] // DAY_MINUTES)
                if previous is None or previous["kind"] != "FLIGHT":
                    representability_errors.append(
                        f"aircraft {tail} maintenance on day {day} has no preceding trigger flight"
                    )
            position = activity["destination"]
            previous = activity

    return {
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "milp_representable": not errors and not representability_errors,
        "milp_representability_errors": representability_errors,
    }


def verify_milp_certificate(milp_scheduler, certificate, tolerance=1e-7, **build_options):
    """Fix a certificate in a built MILP and verify every active constraint.

    The helper supports the current flight-triggered maintenance representation:
    each maintenance event must start after a same-day assigned flight that lands
    at its maintenance station. Events spanning more than one model day are
    rejected because the current ``y``/``mega`` variables have no independent
    maintenance-continuation state.
    """
    instance = milp_scheduler.data if hasattr(milp_scheduler, "data") else None
    if instance is None:
        raise ValueError("MILP scheduler must expose its loaded instance data")

    external = validate_benchmark_certificate(instance, certificate)
    errors = list(external["errors"])
    mapping_errors = list(external["milp_representability_errors"])
    if errors or mapping_errors:
        return {
            "status": "FAIL",
            "errors": errors + mapping_errors,
            "checked_constraints": 0,
        }

    model = milp_scheduler.build_model(**build_options)
    for variable in (model.x, model.z, model.y, model.mega, model.maintenance_start):
        for index in variable:
            variable[index].fix(0)

    assignment = certificate["assignment"]
    for flight_id, aircraft in assignment.items():
        index = (int(flight_id), aircraft)
        if index not in model.X:
            mapping_errors.append(f"assignment {index} is not an MILP arc")
        else:
            model.x[index].fix(1)

    events_by_aircraft_day = defaultdict(list)
    for event in certificate.get("maintenance_events", []):
        duration = float(event["end"]) - float(event["start"])
        if duration > DAY_MINUTES:
            mapping_errors.append("multi-day maintenance events are not representable")
            continue
        aircraft = event["tail"]
        day = int(float(event["start"]) // DAY_MINUTES) + 1
        check = event["check"]
        triggers = [
            flight for flight in instance["Flights"]
            if assignment.get(str(flight[0])) == aircraft
            and float(flight[4]) <= float(event["start"])
            and flight[2] == event["station"]
            and (flight[0], aircraft, day, check) in model.Z
        ]
        if not triggers:
            mapping_errors.append(
                f"maintenance event for aircraft {aircraft} on day {day} has no MILP trigger"
            )
            continue
        trigger = max(triggers, key=lambda flight: flight[4])
        model.z[trigger[0], aircraft, day, check].fix(1)
        events_by_aircraft_day[aircraft, day].append(check)

    for aircraft in model.P:
        for day in model.D:
            scheduled = events_by_aircraft_day[aircraft, day]
            for check in model.C:
                model.y[aircraft, day, check].fix(int(check in scheduled))
                covered = any(
                    scheduled_check in milp_scheduler.CHECK_HIERARCHY[check]
                    for scheduled_check in scheduled
                )
                model.mega[aircraft, day, check].fix(int(covered))
                previous_active = day > min(model.D) and check in events_by_aircraft_day[aircraft, day - 1]
                model.maintenance_start[aircraft, day, check].fix(
                    int(check in scheduled and not previous_active)
                )

    if mapping_errors:
        return {
            "status": "FAIL",
            "errors": mapping_errors,
            "checked_constraints": 0,
        }

    for constraint in model.component_data_objects(Constraint, active=True):
        body = value(constraint.body)
        if constraint.has_lb() and body < value(constraint.lower) - tolerance:
            errors.append(f"violated lower bound: {constraint.name}")
        if constraint.has_ub() and body > value(constraint.upper) + tolerance:
            errors.append(f"violated upper bound: {constraint.name}")

    return {
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "checked_constraints": sum(
            1 for _ in model.component_data_objects(Constraint, active=True)
        ),
    }