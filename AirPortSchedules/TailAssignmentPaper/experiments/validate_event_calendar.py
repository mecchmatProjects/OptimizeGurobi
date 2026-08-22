"""Independently replay C/D calendar-check events from solved event models."""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import sys
from pathlib import Path

from pyomo.environ import value

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.compact_a_event_model import OrderedABCDEventMILPScheduler
from src.event_model import EventMILPScheduler


def selected_events(scheduler, aircraft, requirement):
    events = []
    for flight, candidate_aircraft, check in scheduler.model.Z:
        if candidate_aircraft != aircraft:
            continue
        if check not in scheduler.CHECK_HIERARCHY[requirement]:
            continue
        if value(scheduler.model.z[flight, aircraft, check]) > 0.5:
            events.append((scheduler.flight_data[flight]["arrivalTime"], flight, check))
    return sorted(events)


def replay_calendar(scheduler):
    horizon_end = max(
        scheduler.DAY_SHIFT,
        __import__("math").ceil(
            max(scheduler.flight_data[flight]["arrivalTime"] for flight in scheduler.flight_ids)
            / scheduler.DAY_SHIFT
        )
        * scheduler.DAY_SHIFT,
    )
    violations = []
    for aircraft in scheduler.aircraft_ids:
        for requirement in ("C", "D"):
            limit = scheduler.check_days[requirement] * scheduler.DAY_SHIFT
            initial_elapsed = scheduler.init_check_hrs[requirement][aircraft] * 60.0
            events = selected_events(scheduler, aircraft, requirement)
            first_deadline = limit - initial_elapsed
            if first_deadline <= horizon_end and not any(
                timestamp <= first_deadline for timestamp, _, _ in events
            ):
                violations.append((aircraft, requirement, "first_deadline", first_deadline))
            for previous, current in zip(events, events[1:]):
                gap = current[0] - previous[0]
                if gap > limit + 1e-6:
                    violations.append((aircraft, requirement, "event_gap", gap))
            if events and events[-1][0] + limit <= horizon_end:
                violations.append((aircraft, requirement, "horizon_tail", events[-1][0] + limit))
    return violations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs="+", required=True)
    parser.add_argument("--solver", default="cplexamp")
    parser.add_argument("--executable", required=True)
    parser.add_argument("--time-limit", type=int, default=60)
    parser.add_argument("--output", default="results/tables/event_calendar_validation.csv")
    args = parser.parse_args()

    rows = []
    for path_text in args.input:
        path = Path(path_text)
        for label, formulation in (
            ("ordered_abcd", OrderedABCDEventMILPScheduler),
            ("event_exact", EventMILPScheduler),
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                scheduler = formulation(str(path))
                scheduler.build_model()
                summary = scheduler.solve(
                    solver_name=args.solver,
                    executable=args.executable,
                    time_limit=args.time_limit,
                    warm_start=False,
                )
            violations = replay_calendar(scheduler) if summary["status"] == "optimal" else []
            rows.append({
                "instance": path.name,
                "formulation": label,
                "status": summary["status"],
                "objective": summary.get("obj"),
                "n_calendar_violations": len(violations),
                "violations": "; ".join(map(str, violations)),
            })

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {output}")
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
