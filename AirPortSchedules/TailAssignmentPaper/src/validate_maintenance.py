"""Independent post-hoc replay of A/B maintenance-threshold compliance.

The replay uses the solved assignment and maintenance decisions, not the
model's cumulative-hour state or C13/C13b expressions. Day-indexed models reset
after all flights on a selected maintenance day; ordered-event models reset
after the selected trigger flight and are additionally checked against their
event completion, blocking, and station-capacity decisions. This makes the
replay independent of the hour-state rows (including the endpoint-split flaw
proved in
``paper/sections/04_maintenance_model.tex``, Lemma ``lem:c13_split_limit``,
and numerically confirmed in ``experiments/c13_loophole_validation.py``). If a
solver reports an optimal schedule whose flown hours exceed a check threshold,
the replay reports the excess.

Only the A/B (flight-hour) check types are validated here, since those are
exactly the types governed by C13/C13b. C/D (calendar-day) checks are
governed by a different constraint family (C12/C12b); see
``experiments/hierarchy_effectiveness.py`` for the day-gap analogue that
covers C/D as well.

Usage
-----
    python src/validate_maintenance.py --data data/instances/FILE.json \\
        [--solver cplexamp --executable "F:/Progs/IBM.ILOG.CPLEX.for.AMPL.v12.6-EAT/CPLEXamp.exe"] \\
        [--no-check-hierarchy] [--disable-checks B C D] \\
        [--csv results/tables/validation_report.csv]

Can also be used as a library::

    from src.validate_maintenance import validate_solved_model
    violations = validate_solved_model(opt)
"""
import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pyomo.environ import value as pyo_value

from src.model import run_milp


def _solved_flight_sequence(opt):
    """Return {aircraft_id: [(departure_time, flight_id, duration), ...]}.

    Only includes flights whose x[i, j] == 1 in the current (solved) model.
    """
    m = opt.model
    seq = defaultdict(list)
    for i in m.F:
        for j in opt._x_aircrafts_for_flight(i):
            if pyo_value(m.x[i, j]) > 0.5:
                fd = opt.flight_data[i]
                seq[j].append((fd['departureTime'], i, fd['duration']))
    for flights in seq.values():
        flights.sort()
    return seq


def _check_event_days(opt, aircraft, check):
    """Return the first day of each contiguous y[j,d,check]==1 run.

    A multi-day check keeps y=1 for every day it spans; only the first day
    of each run is a genuine "check performed" event (subsequent days are
    just the check's continuation, not a new reset point).
    """
    m = opt.model
    days_true = sorted(d for d in m.D if pyo_value(m.y[aircraft, d, check]) > 0.5)
    events = []
    prev = None
    for d in days_true:
        if prev is None or d != prev + 1:
            events.append(d)
        prev = d
    return events


def _selected_trigger_flights(opt, aircraft, check):
    """Extract selected reset flights from legacy or ordered-event z indices."""
    model = opt.model
    trigger_flights = set()
    for index in model.Z:
        if len(index) == 3:
            flight, candidate_aircraft, candidate_check = index
        elif len(index) == 4:
            flight, candidate_aircraft, _day, candidate_check = index
        else:
            raise ValueError(f"Unsupported maintenance trigger index: {index!r}")

        if (
            candidate_aircraft == aircraft
            and candidate_check == check
            and pyo_value(model.z[index]) > 0.5
        ):
            trigger_flights.add(flight)
    return trigger_flights


def _validate_ordered_event_windows(opt, tol):
    """Validate selected ordered events against timing, capacity, and blocking."""
    model = opt.model
    selected_indices = [
        index for index in model.Z if pyo_value(model.z[index]) > 0.5
    ]
    if not selected_indices or len(next(iter(model.Z))) != 3:
        return []

    flexible = hasattr(model, "s")
    violations = []
    events = []
    for index in selected_indices:
        flight, aircraft, check = index
        arrival = opt.flight_data[flight]["arrivalTime"]
        duration = float(opt.check_dur[check])
        offset = pyo_value(model.s[index]) if flexible else 0.0
        offset = float(offset)
        if flexible:
            max_offset = duration + float(opt.MAX_MAINT_DEFER)
            grid = float(opt.MAINTENANCE_TIME_GRID)
            if offset < duration - tol or offset > max_offset + tol:
                violations.append({
                    "type": "maintenance_timing",
                    "aircraft": aircraft,
                    "flight": flight,
                    "offset_min": offset,
                    "minimum_offset_min": duration,
                    "maximum_offset_min": max_offset,
                })
            if abs(offset / grid - round(offset / grid)) > tol:
                violations.append({
                    "type": "maintenance_grid",
                    "aircraft": aircraft,
                    "flight": flight,
                    "offset_min": offset,
                    "grid_min": grid,
                })

        if (flight, aircraft) not in model.X or pyo_value(model.x[flight, aircraft]) <= 0.5:
            violations.append({
                "type": "maintenance_unassigned_trigger",
                "aircraft": aircraft,
                "flight": flight,
            })

        completion = arrival + offset if flexible else arrival + duration
        start = completion - duration
        events.append({
            "flight": flight,
            "aircraft": aircraft,
            "check": check,
            "airport": opt.flight_data[flight]["destination"],
            "arrival": arrival,
            "start": start,
            "completion": completion,
        })

        turn = float(opt.MIN_TURN)
        for following in model.F:
            if (following, aircraft) not in model.X:
                continue
            if pyo_value(model.x[following, aircraft]) <= 0.5:
                continue
            departure = opt.flight_data[following]["departureTime"]
            if departure >= arrival - tol and departure < completion + turn - tol:
                violations.append({
                    "type": "flight_during_maintenance",
                    "aircraft": aircraft,
                    "trigger_flight": flight,
                    "following_flight": following,
                    "departure_min": departure,
                    "available_min": completion + turn,
                })

    for airport in opt.maint_airports:
        airport_events = [event for event in events if event["airport"] == airport]
        capacity = int(opt.station_cap.get(airport, 0))
        for instant in sorted({event["start"] for event in airport_events}):
            active = [
                event for event in airport_events
                if event["start"] <= instant + tol
                and instant < event["completion"] - tol
            ]
            if len(active) > capacity:
                violations.append({
                    "type": "maintenance_capacity",
                    "airport": airport,
                    "time_min": instant,
                    "active_events": [
                        (event["flight"], event["aircraft"], event["check"])
                        for event in active
                    ],
                    "capacity": capacity,
                })
    return violations


def validate_solved_model(opt, tol=1e-6):
    """Independently verify A/B flight-hour thresholds on a solved model.

    Returns a list of violation dicts (empty list means compliant).
    """
    m = opt.model
    seq_by_ac = _solved_flight_sequence(opt)
    violations = []

    for j in m.P:
        flights = seq_by_ac.get(j, [])
        for c in opt.CHECK_LIST:
            if opt.check_days[c] is not None:
                continue  # C/D calendar-day type: out of scope here
            threshold_min = opt.check_hrs[c] * 60.0
            accumulated = opt.init_check_hrs[c].get(j, 0.0) * 60.0
            index_dimension = len(next(iter(m.Z))) if len(m.Z) else None
            if index_dimension == 4:
                flights_by_day = defaultdict(list)
                for departure, flight, duration in flights:
                    day = opt.flight_data[flight]['day_departure']
                    flights_by_day[day].append((departure, flight, duration))
                check_days = {
                    day for day in m.D
                    if pyo_value(m.y[j, day, c]) > 0.5
                }
                replay_days = sorted(set(flights_by_day) | check_days)
                for day in replay_days:
                    for _, flight, duration in flights_by_day.get(day, ()):
                        accumulated += duration
                        if accumulated > threshold_min + tol:
                            violations.append({
                                'aircraft': j,
                                'check': c,
                                'window_start_day': None,
                                'window_end_day': day,
                                'accumulated_min': accumulated,
                                'threshold_min': threshold_min,
                                'excess_min': accumulated - threshold_min,
                            })
                    if day in check_days:
                        accumulated = 0.0
            else:
                trigger_flights = _selected_trigger_flights(opt, j, c)
                for _, flight, duration in flights:
                    accumulated += duration
                    if accumulated > threshold_min + tol:
                        violations.append({
                            'aircraft': j,
                            'check': c,
                            'window_start_day': None,
                            'window_end_day': opt.flight_data[flight]['day_arrival'],
                            'accumulated_min': accumulated,
                            'threshold_min': threshold_min,
                            'excess_min': accumulated - threshold_min,
                        })
                    if flight in trigger_flights:
                        accumulated = 0.0
    violations.extend(_validate_ordered_event_windows(opt, tol))
    return violations


def print_violations(violations, label=None):
    header = f"\n=== Maintenance validation{f' -- {label}' if label else ''} ==="
    print(header)
    if not violations:
        print("  PASS: 0 violations (all A/B flight-hour windows within threshold)")
        return
    print(f"  FAIL: {len(violations)} violation(s) found")
    for v in violations:
        lo = v['window_start_day'] if v['window_start_day'] is not None else 'horizon-start'
        hi = v['window_end_day'] if v['window_end_day'] is not None else 'horizon-end'
        print(f"    aircraft {v['aircraft']}  check {v['check']}  window ({lo}, {hi}]  "
              f"flew {v['accumulated_min']:.1f} min > cap {v['threshold_min']:.1f} min  "
              f"(excess {v['excess_min']:.1f} min)")


def _main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data', required=True, help='JSON instance file to solve and validate')
    parser.add_argument('--solver', default='cplex', help='Pyomo solver name')
    parser.add_argument('--executable', default=None,
                         help='Explicit path to the solver binary (bypasses PATH lookup)')
    parser.add_argument('--time-limit', type=int, default=300)
    parser.add_argument('--no-check-hierarchy', dest='use_check_hierarchy',
                        action='store_false')
    parser.add_argument('--no-existing-hrs', dest='use_existing_hrs',
                        action='store_false',
                        help='Disable C13b (existing/prior-hours window) to isolate C13.')
    parser.add_argument('--disable-checks', nargs='+', default=None, metavar='CHECK')
    parser.add_argument('--csv', default=None, help='Append a result row to this CSV file')
    parser.set_defaults(use_check_hierarchy=True, use_existing_hrs=True)
    args = parser.parse_args()

    enabled_checks = None
    if args.disable_checks:
        enabled_checks = [c for c in ['A', 'B', 'C', 'D'] if c not in args.disable_checks]

    opt, summary = run_milp(
        data_path=args.data, solver=args.solver, tee=False,
        time_limit=args.time_limit, show_gantt=False,
        use_check_hierarchy=args.use_check_hierarchy,
        use_existing_hrs=args.use_existing_hrs,
        enabled_checks=enabled_checks,
        warm_start=False,
        executable=args.executable,
    )

    status = summary.get('status') if isinstance(summary, dict) else str(summary)
    label = f"{args.data}  status={status}"

    if status != 'optimal':
        print(f"\n=== Maintenance validation -- {label} ===")
        print(f"  SKIPPED: solver status is '{status}', no solved schedule to validate.")
        violations = []
    else:
        violations = validate_solved_model(opt)
        print_violations(violations, label=label)

    if args.csv:
        write_header = False
        try:
            with open(args.csv, 'r', encoding='utf-8'):
                pass
        except FileNotFoundError:
            write_header = True
        with open(args.csv, 'a', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(['data', 'solver_status', 'n_violations',
                            'aircraft', 'check', 'window_start_day', 'window_end_day',
                            'accumulated_min', 'threshold_min', 'excess_min'])
            if violations:
                for v in violations:
                    w.writerow([args.data, status, len(violations),
                                v['aircraft'], v['check'], v['window_start_day'],
                                v['window_end_day'], v['accumulated_min'],
                                v['threshold_min'], v['excess_min']])
            else:
                w.writerow([args.data, status, 0, '', '', '', '', '', '', ''])


if __name__ == '__main__':
    _main()
