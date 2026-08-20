"""Diagnose disconnected aircraft routes in the legacy flow formulation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pyomo.environ import value

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--solver", default="cplexamp")
    parser.add_argument("--executable", required=True)
    parser.add_argument("--time-limit", type=int, default=60)
    args = parser.parse_args()

    from src.model import LegacyEndpointSplitMILPScheduler

    scheduler = LegacyEndpointSplitMILPScheduler(args.data)
    scheduler.build_model(allow_ferry=True)
    summary = scheduler.solve(
        solver_name=args.solver,
        executable=args.executable,
        time_limit=args.time_limit,
        warm_start=False,
    )
    print(f"status={summary['status']} objective={summary.get('obj')}")

    model = scheduler.model
    for aircraft in scheduler.aircraft_ids:
        assigned = [
            flight
            for flight in scheduler.flight_ids
            if value(model.x[flight, aircraft]) > 0.5
        ]
        assigned.sort(key=lambda flight: scheduler.flight_data[flight]["departureTime"])
        current_airport = scheduler.aircraft_init[aircraft]
        current_time = 0.0
        disconnected = []
        for flight in assigned:
            data = scheduler.flight_data[flight]
            if (
                data["origin"] != current_airport
                or data["departureTime"] < current_time + scheduler.MIN_TURN
            ):
                disconnected.append(flight)
            current_airport = data["destination"]
            current_time = data["arrivalTime"]
        if disconnected:
            print(
                f"aircraft={aircraft} assigned={assigned} "
                f"disconnected={disconnected}"
            )


if __name__ == "__main__":
    main()