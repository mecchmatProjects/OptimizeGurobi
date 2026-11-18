"""Validation helpers for externally generated TAP benchmark certificates."""

from collections import Counter, defaultdict
import math

from pyomo.core.base.constraint import Constraint
from pyomo.environ import value


DAY_MINUTES = 24 * 60
CHECKS = ("A", "B", "C", "D")
COUNTER_KEYS = {"A": "A", "B": "B", "C": "C_Days", "D": "D_Days"}


def validate_a_hour_exposure(instance, certificate, tolerance=1e-7):
    """Replay type-A flight minutes at arrivals and reset at check completion.

    The instance and certificate use minutes. This checks exposure only;
    validate route and maintenance timing separately.
    """
    threshold = float(instance["Maintenance_Thresholds"]["A"])
    initial = instance.get("Initial_Checks", {}).get("A", {})
    assignment = certificate["assignment"]
    activities = defaultdict(list)
    for flight in instance["Flights"]:
        aircraft = assignment[str(flight[0])]
        duration = float(flight[4]) - float(flight[3])
        if duration <= 0:
            raise ValueError(f"flight {flight[0]} must have positive duration")
        activities[aircraft].append((float(flight[4]), 0, flight[0], duration))
    for index, event in enumerate(certificate.get("maintenance_events", [])):
        if event["check"] == "A":
            if float(event["end"]) <= float(event["start"]):
                raise ValueError("maintenance must have positive duration")
            activities[event["tail"]].append((float(event["end"]), 1, index, 0.0))

    violations = []
    for aircraft in instance["Aircrafts"]:
        exposure = float(initial.get(str(aircraft), 0.0))
        if exposure > threshold + tolerance:
            violations.append({"aircraft": aircraft, "flight": None,
                               "exposure_minutes": exposure, "limit_minutes": threshold})
        for timestamp, kind, identifier, duration in sorted(activities[aircraft]):
            if kind == 1:
                exposure = 0.0
                continue
            exposure += duration
            if exposure > threshold + tolerance:
                violations.append({"aircraft": aircraft, "flight": identifier,
                                   "time": timestamp, "exposure_minutes": exposure,
                                   "limit_minutes": threshold})
    return violations


def validate_benchmark_certificate(
    instance,
    certificate,
    capacity_semantics="daily",
    post_maintenance_turn=0.0,
    strict_a_hour_limit=False,
):
    """Replay a complete no-ferry certificate without consulting model constraints.

    ``capacity_semantics`` is ``"daily"`` for the published quota convention or
    ``"simultaneous"`` for the Option A/B reserved-bay convention.
    ``post_maintenance_turn`` is the additional release-to-departure gap.
    Set ``strict_a_hour_limit=True`` for the corrected A-only policy, where an
    arrival may not cross the threshold and then be repaired by a later check.
    """
    errors = []
    representability_errors = []
    if capacity_semantics not in {"daily", "simultaneous"}:
        return {
            "status": "FAIL",
            "errors": [f"unsupported capacity semantics: {capacity_semantics}"],
            "milp_representable": False,
            "milp_representability_errors": [],
        }
    if post_maintenance_turn < 0:
        return {
            "status": "FAIL",
            "errors": ["post-maintenance turn must be nonnegative"],
            "milp_representable": False,
            "milp_representability_errors": [],
        }
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
        start = float(event.get("start", 0))
        end = float(event.get("end", 0))
        if start >= end:
            errors.append("maintenance event has non-positive duration")
            continue
        expected_duration = float(instance["Maintenance_Durations"][check])
        if not math.isclose(end - start, expected_duration, abs_tol=1e-6):
            errors.append(
                f"maintenance event for aircraft {tail} has duration {end - start}, "
                f"expected {expected_duration}"
            )
        routes[tail].append({
            "kind": "MAINT", "start": float(event["start"]),
            "end": float(event.get("release", event["end"])),
            "origin": event["station"], "destination": event["station"], "check": check,
            "completion": float(event["end"]),
        })

    if capacity_semantics == "daily":
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
                errors.append(f"maintenance daily capacity exceeded at {station} on day {day}")
    else:
        events_by_station = defaultdict(list)
        for event in maintenance:
            if event.get("station") in instance["Station_Capacity"]:
                events_by_station[event["station"]].append(event)
        for station, events in events_by_station.items():
            for instant in sorted({float(event["start"]) for event in events}):
                active = sum(
                    float(event["start"]) <= instant < float(event["end"])
                    for event in events
                )
                if active > instance["Station_Capacity"][station]:
                    errors.append(
                        f"maintenance simultaneous capacity exceeded at {station} at minute {instant}"
                    )
                    break

    for tail in tails:
        activities = sorted(routes[tail], key=lambda item: (item["start"], item["end"]))
        position = instance["AIRCRAFT_INIT_POS"].get(str(tail))
        previous = None
        for activity in activities:
            if activity["origin"] != position:
                errors.append(f"aircraft {tail} has a station-continuity break")
            if previous is not None:
                if previous["kind"] == activity["kind"] == "FLIGHT":
                    required_gap = min_turn
                elif previous["kind"] == "MAINT" and activity["kind"] == "FLIGHT":
                    required_gap = float(post_maintenance_turn)
                else:
                    required_gap = 0.0
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

    if strict_a_hour_limit:
        for violation in validate_a_hour_exposure(instance, certificate):
            errors.append(
                f"aircraft {violation['aircraft']} exceeds the A-hour limit at "
                f"flight {violation['flight']}: {violation['exposure_minutes']} > "
                f"{violation['limit_minutes']} minutes"
            )

    return {
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "milp_representable": not errors and not representability_errors,
        "milp_representability_errors": representability_errors,
    }


def extract_milp_certificate(scheduler):
    """Extract a solver-independent schedule certificate from a solved model."""
    model = scheduler.model
    if model is None:
        raise ValueError("cannot extract a certificate from an unbuilt/unsupported model")
    assignment = {}
    for flight, aircraft in model.X:
        if value(model.x[flight, aircraft]) > 0.5:
            assignment[str(flight)] = aircraft

    events = []
    option_events = getattr(scheduler, "option_a_events", {})
    for index in model.Z:
        if value(model.z[index]) <= 0.5:
            continue
        if len(index) == 4:
            flight, aircraft, model_day, check = index
        elif len(index) == 3:
            flight, aircraft, check = index
            model_day = scheduler.flight_data[flight]["day_arrival"]
        else:
            raise ValueError(f"unsupported maintenance trigger index: {index}")
        timing = option_events.get(index)
        if timing is None:
            start = scheduler.flight_data[flight]["arrivalTime"]
            completion = start + scheduler.check_dur[check]
            release = completion
        else:
            start = timing["start"]
            completion = timing["completion"]
            release = timing["release"]
        events.append({
            "tail": aircraft,
            "check": check,
            "station": scheduler.flight_data[flight]["destination"],
            "start": float(start),
            "end": float(completion),
            "release": float(release),
            "trigger_flight": flight,
            "model_day": model_day,
        })

    return {"assignment": assignment, "maintenance_events": events}


def certify_option_a_input(instance):
    """Validate the data required by constrained overnight Option A."""
    errors = []
    duration = float(instance.get("Maintenance_Durations", {}).get("A", 0.0))
    if duration <= 0:
        errors.append("Option A requires a positive A-check duration")

    windows = instance.get("Maintenance_Service_Windows")
    buffers = instance.get("Maintenance_Buffers", {}).get("A")
    if not isinstance(windows, dict):
        errors.append("Option A requires Maintenance_Service_Windows")
        windows = {}
    if not isinstance(buffers, dict):
        errors.append("Option A requires Maintenance_Buffers.A")
        buffers = {}

    for aircraft in instance.get("Aircrafts", []):
        value = buffers.get(str(aircraft))
        if not isinstance(value, dict):
            errors.append(f"missing A preparation/release buffers for aircraft {aircraft}")
            continue
        for name in ("preparation", "release"):
            buffer = float(value.get(name, -1.0))
            if buffer < 0:
                errors.append(f"invalid {name} buffer for aircraft {aircraft}")

    station_capacity = instance.get("Station_Capacity", {})
    for flight in instance.get("Flights", []):
        station = flight[2]
        if station_capacity.get(station, 0) <= 0:
            continue
        day = int(float(flight[4]) // DAY_MINUTES) + 1
        station_windows = windows.get(station, {})
        window = station_windows.get(str(day))
        if not isinstance(window, (list, tuple)) or len(window) != 2:
            errors.append(f"missing service window for station {station} on day {day}")
            continue
        lower, upper = map(float, window)
        if lower > upper:
            errors.append(f"invalid service window for station {station} on day {day}")

    terminal = instance.get("Terminal_Release_Minutes", {})
    for aircraft, deadline in terminal.items():
        if float(deadline) < 0:
            errors.append(f"negative terminal release deadline for aircraft {aircraft}")

    return {
        "status": "SUPPORTED" if not errors else "UNSUPPORTED",
        "errors": errors,
        "policy": "option_a",
    }


def certify_option_b_input(instance):
    """Certify the restrictive protected-night assumptions for Option B."""
    errors = []
    option_a = certify_option_a_input(instance)
    errors.extend(option_a["errors"])
    periods = instance.get("Protected_Maintenance_Periods")
    if not isinstance(periods, dict):
        errors.append("Option B requires Protected_Maintenance_Periods")
        periods = {}

    duration = float(instance.get("Maintenance_Durations", {}).get("A", 0.0))
    buffers = instance.get("Maintenance_Buffers", {}).get("A", {})
    windows = instance.get("Maintenance_Service_Windows", {})
    flights = instance.get("Flights", [])
    aircraft_ids = instance.get("Aircrafts", [])
    costs = instance.get("Cost_Matrix", [])
    aircraft_index = {aircraft: index for index, aircraft in enumerate(aircraft_ids)}
    flight_index = {flight[0]: index for index, flight in enumerate(flights)}

    for flight in flights:
        departure_day = int(float(flight[3]) // DAY_MINUTES) + 1
        arrival_day = int(float(flight[4]) // DAY_MINUTES) + 1
        if departure_day != arrival_day:
            errors.append(f"flight {flight[0]} crosses a day boundary")

    by_day = defaultdict(list)
    for flight in flights:
        day = int(float(flight[3]) // DAY_MINUTES) + 1
        by_day[day].append(flight)

    for day, daily_flights in by_day.items():
        period = periods.get(str(day))
        if not isinstance(period, (list, tuple)) or len(period) != 2:
            errors.append(f"missing protected period for day {day}")
            continue
        lower, upper = map(float, period)
        if lower >= upper:
            errors.append(f"invalid protected period for day {day}")
            continue

        for flight in daily_flights:
            row = costs[flight_index[flight[0]]]
            for aircraft in aircraft_ids:
                if float(row[aircraft_index[aircraft]]) >= 9999:
                    continue
                preparation = float(buffers.get(str(aircraft), {}).get("preparation", -1.0))
                if preparation < 0 or float(flight[4]) > lower - preparation:
                    errors.append(
                        f"day {day} flight {flight[0]} is not finished before the protected period for aircraft {aircraft}"
                    )

        if day > 1 and str(day - 1) in periods:
            previous_upper = float(periods[str(day - 1)][1])
            for flight in daily_flights:
                if float(flight[3]) < previous_upper:
                    errors.append(
                        f"day {day} flight {flight[0]} departs before previous protected period ends"
                    )

        for aircraft in aircraft_ids:
            release = float(buffers.get(str(aircraft), {}).get("release", -1.0))
            if release < 0 or duration + release > upper - lower:
                errors.append(
                    f"protected period on day {day} is too short for aircraft {aircraft}"
                )

        for station, capacity in instance.get("Station_Capacity", {}).items():
            if capacity <= 0:
                continue
            station_window = windows.get(station, {}).get(str(day))
            if not isinstance(station_window, (list, tuple)) or len(station_window) != 2:
                errors.append(f"station {station} lacks a service window on day {day}")
                continue
            if float(station_window[0]) > lower or float(station_window[1]) < upper:
                errors.append(
                    f"station {station} service window does not contain the protected period on day {day}"
                )

    terminal = instance.get("Terminal_Release_Minutes", {})
    if periods:
        final_upper = max(float(window[1]) for window in periods.values())
        for aircraft in aircraft_ids:
            deadline = terminal.get(str(aircraft))
            if deadline is None or float(deadline) < final_upper:
                errors.append(
                    f"aircraft {aircraft} lacks a terminal release deadline covering the final protected period"
                )

    errors = list(dict.fromkeys(errors))
    return {
        "status": "SUPPORTED" if not errors else "UNSUPPORTED",
        "errors": errors,
        "policy": "option_b",
    }


def verify_milp_certificate(milp_scheduler, certificate, tolerance=1e-7, **build_options):
    """Fix a certificate in a built MILP and verify every active constraint.

    Each maintenance event must start after a same-day assigned flight that
    lands at its maintenance station. Both aircraft-indexed and global trigger
    formulations are supported. Events spanning more than one model day are
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
            and (
                (flight[0], day, check) in model.Z
                if milp_scheduler.use_global_maint_trigger
                else (flight[0], aircraft, day, check) in model.Z
            )
        ]
        if not triggers:
            mapping_errors.append(
                f"maintenance event for aircraft {aircraft} on day {day} has no MILP trigger"
            )
            continue
        trigger = max(triggers, key=lambda flight: flight[4])
        if milp_scheduler.use_global_maint_trigger:
            model.z[trigger[0], day, check].fix(1)
            model.w[trigger[0], aircraft, day, check].fix(1)
        else:
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