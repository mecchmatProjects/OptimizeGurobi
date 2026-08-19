"""Validate MILP assignments with the heuristic timeline semantics."""
import argparse
import json
import sys
from pathlib import Path

from pyomo.environ import value

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model import MILP_Sheduler, Scheduler


def extract_routes(optimizer):
    routes = {aid: [] for aid in optimizer.aircraft_ids}
    model = optimizer.model
    for aid in optimizer.aircraft_ids:
        assigned = [
            fid for fid in optimizer.flight_ids
            if optimizer._x_has_arc(fid, aid)
            and value(model.x[fid, aid]) > 0.5
        ]
        routes[aid] = sorted(
            assigned,
            key=lambda fid: optimizer.flight_data[fid]["departureTime"],
        )
    return routes


def validate(data_path, solver_name="highs", time_limit=120, allow_ferry=True):
    optimizer = MILP_Sheduler(str(data_path))
    optimizer.build_model(allow_ferry=allow_ferry, use_maintenance=True)
    summary = optimizer.solve(
        solver_name=solver_name,
        time_limit=time_limit,
        warm_start=False,
    )
    if summary.get("status") != "optimal":
        return {
            "status": "not_certified",
            "solver_status": summary.get("status"),
            "route_valid": None,
            "mismatches": [],
        }

    scheduler = Scheduler(str(data_path), allow_ferry=allow_ferry)
    routes = extract_routes(optimizer)
    mismatches = []
    for aid, route in routes.items():
        timeline = scheduler.get_timeline(aid, route)
        if timeline is None:
            mismatches.append({
                "aircraft": aid,
                "route": route,
                "reason": "timeline_infeasible",
            })

    assigned = sum(len(route) for route in routes.values())
    total_flights = len(scheduler.flights)
    return {
        "status": "validated" if not mismatches else "semantic_mismatch",
        "solver_status": summary.get("status"),
        "route_valid": not mismatches,
        "assigned": assigned,
        "flights": total_flights,
        "coverage_pct": 100.0 * assigned / total_flights if total_flights else 0.0,
        "mismatches": mismatches,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="JSON instance path")
    parser.add_argument("--solver", default="highs")
    parser.add_argument("--time-limit", type=int, default=120)
    parser.add_argument("--no-ferry", dest="allow_ferry", action="store_false")
    args = parser.parse_args()

    result = validate(
        Path(args.data),
        solver_name=args.solver,
        time_limit=args.time_limit,
        allow_ferry=args.allow_ferry,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"validated", "not_certified"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
