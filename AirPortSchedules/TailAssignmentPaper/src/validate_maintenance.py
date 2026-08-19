"""Independent, post-hoc verification of maintenance-threshold compliance.

Ported and adapted from the ``thesis_version`` branch (stripped of the
``use_paper_c13`` toggle, which no longer exists: ``src/model.py`` now builds
only the endpoint-split C13). Recomputes cumulative flight-hour accumulation
directly from a SOLVED ``MILP_Sheduler``'s raw ``x``/``y`` decision variables
via a plain sequential walk over each aircraft's assigned flights -- NOT via
the ``mega`` hierarchy variable and NOT by re-checking any of the model's own
big-M constraint expressions (C13/C13b). This makes it independent of bugs in
those constraints (see the endpoint-split flaw proved in
``paper/sections/04_maintenance_model.tex``, Lemma ``lem:c13_split_limit``,
and numerically confirmed in ``experiments/c13_loophole_validation.py``): if
the MILP reports 'optimal' but the *actual* flown schedule exceeds a check's
flight-hour threshold between two real maintenance events, this script flags
it.

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
    """Return {aircraft_id: [(day_departure, duration_minutes), ...]}.

    Only includes flights whose x[i, j] == 1 in the current (solved) model.
    """
    m = opt.model
    seq = defaultdict(list)
    for i in m.F:
        for j in opt._x_aircrafts_for_flight(i):
            if pyo_value(m.x[i, j]) > 0.5:
                fd = opt.flight_data[i]
                seq[j].append((fd['day_departure'], fd['duration']))
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


def validate_solved_model(opt, tol=1e-6):
    """Independently verify A/B flight-hour thresholds on a solved MILP_Sheduler.

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
            prior_min = opt.init_check_hrs[c].get(j, 0.0) * 60.0
            event_days = _check_event_days(opt, j, c)
            boundaries = [None] + event_days + [None]
            for k in range(len(boundaries) - 1):
                lo, hi = boundaries[k], boundaries[k + 1]
                window_min = sum(
                    dur for (dep_day, dur) in flights
                    if (lo is None or dep_day > lo) and (hi is None or dep_day <= hi)
                )
                cap = threshold_min - (prior_min if lo is None else 0.0)
                if window_min > cap + tol:
                    violations.append({
                        'aircraft': j,
                        'check': c,
                        'window_start_day': lo,
                        'window_end_day': hi,
                        'accumulated_min': window_min,
                        'threshold_min': cap,
                        'excess_min': window_min - cap,
                    })
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
