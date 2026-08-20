"""Compare assignments and maintenance decisions from both exact models."""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

from pyomo.environ import value

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def solve_quietly(scheduler, solver_name, executable, time_limit):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        summary = scheduler.solve(
            solver_name=solver_name,
            executable=executable,
            time_limit=time_limit,
            warm_start=False,
        )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--solver", default="cplexamp")
    parser.add_argument("--executable", required=True)
    parser.add_argument("--time-limit", type=int, default=60)
    args = parser.parse_args()

    from src.event_model import EventMILPScheduler
    from src.model import LegacyEndpointSplitMILPScheduler

    legacy = LegacyEndpointSplitMILPScheduler(args.data)
    legacy.build_model(allow_ferry=True)
    legacy_summary = solve_quietly(
        legacy, args.solver, args.executable, args.time_limit
    )

    event = EventMILPScheduler(args.data)
    event.build_model()
    event_summary = solve_quietly(
        event, args.solver, args.executable, args.time_limit
    )

    print(f"legacy={legacy_summary['status']} objective={legacy_summary.get('obj')}")
    print(f"event={event_summary['status']} objective={event_summary.get('obj')}")

    for aircraft in legacy.aircraft_ids:
        legacy_flights = [
            flight
            for flight in legacy.flight_ids
            if value(legacy.model.x[flight, aircraft]) > 0.5
        ]
        event_flights = [
            flight
            for flight in event.flight_ids
            if value(event.model.x[flight, aircraft]) > 0.5
        ]
        legacy_flights.sort(key=lambda flight: legacy.flight_data[flight]["departureTime"])
        event_flights.sort(key=lambda flight: event.flight_data[flight]["departureTime"])
        if legacy_flights != event_flights:
            print(
                f"aircraft={aircraft} legacy_flights={legacy_flights} "
                f"event_flights={event_flights}"
            )

    legacy_checks = [
        str(key)
        for key, variable in legacy.model.z.items()
        if value(variable) > 0.5
    ]
    event_checks = [
        str(key)
        for key, variable in event.model.z.items()
        if value(variable) > 0.5
    ]
    print(f"legacy_checks={legacy_checks}")
    print(f"event_checks={event_checks}")


if __name__ == "__main__":
    main()