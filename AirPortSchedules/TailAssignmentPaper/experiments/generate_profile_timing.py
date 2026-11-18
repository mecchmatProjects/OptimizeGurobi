"""Generate a reproducible certified input family for A-only profile timing."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.benchmark_validation import certify_option_b_input, validate_benchmark_certificate
from src.generate_instances import stable_seed

DAY = 1440


def build_instance(aircraft_count: int, horizon_days: int, replicate: int) -> tuple[dict, dict]:
    if aircraft_count < 1 or horizon_days < 3 or replicate < 0:
        raise ValueError("require aircraft_count >= 1, horizon_days >= 3, replicate >= 0")
    rng = random.Random(stable_seed(0.75, aircraft_count, horizon_days, replicate))
    aircraft = list(range(aircraft_count))
    mro = "MRO"
    spokes = {tail: f"S{tail}" for tail in aircraft}
    flights_with_owner = []
    next_id = 1

    for day in range(1, horizon_days):
        for tail in aircraft:
            offset = rng.randint(0, 12)
            outbound_departure = (day - 1) * DAY + 20 * 60 + offset
            outbound_arrival = outbound_departure + 60
            flights_with_owner.append((
                [next_id, spokes[tail], mro, float(outbound_departure), float(outbound_arrival)],
                tail,
            ))
            next_id += 1

            return_departure = day * DAY + 7 * 60 + offset
            return_arrival = return_departure + 60
            flights_with_owner.append((
                [next_id, mro, spokes[tail], float(return_departure), float(return_arrival)],
                tail,
            ))
            next_id += 1

    flights_with_owner.sort(key=lambda item: (item[0][3], item[0][0]))
    flights = [flight for flight, _owner in flights_with_owner]
    owners = {flight[0]: owner for flight, owner in flights_with_owner}
    costs = []
    for flight, owner in flights_with_owner:
        costs.append([
            float(100 + rng.randint(0, 20)) if tail == owner
            else float(500 + rng.randint(0, 50))
            for tail in aircraft
        ])

    windows = {
        str(day): [(day - 1) * DAY + 22 * 60, (day - 1) * DAY + 23 * 60]
        for day in range(1, horizon_days + 1)
    }
    protected = {
        str(day): [(day - 1) * DAY + 22 * 60, (day - 1) * DAY + 22 * 60 + 40]
        for day in range(1, horizon_days + 1)
    }
    instance = {
        "Aircrafts": aircraft,
        "AIRCRAFT_INIT_POS": {str(tail): spokes[tail] for tail in aircraft},
        "Flights": flights,
        "Cost_Matrix": costs,
        "Maintenance_Thresholds": {"A": 180, "B": 999999, "C": 9999, "D": 9999},
        "Maintenance_Durations": {"A": 30, "B": 30, "C": 30, "D": 30},
        "Station_Capacity": {mro: aircraft_count, **{spokes[tail]: 0 for tail in aircraft}},
        "Initial_Checks": {
            "A": {str(tail): 0 for tail in aircraft},
            "B": {str(tail): 0 for tail in aircraft},
            "C_Days": {str(tail): 0 for tail in aircraft},
            "D_Days": {str(tail): 0 for tail in aircraft},
        },
        "Maintenance_Families": ["A"],
        "Maintenance_Buffers": {
            "A": {str(tail): {"preparation": 0, "release": 5} for tail in aircraft}
        },
        "Maintenance_Service_Windows": {
            mro: {day: list(window) for day, window in windows.items()}
        },
        "Protected_Maintenance_Periods": {
            day: list(window) for day, window in protected.items()
        },
        "Terminal_Release_Minutes": {
            str(tail): horizon_days * DAY for tail in aircraft
        },
        "Parameters": {
            "Min_Turn_Minutes": 30,
            "Target_Horizon_Days": horizon_days,
            "A_Calendar_Initial_Days": 0,
        },
    }

    assignments = {str(flight): owners[flight] for flight in owners}
    events = []
    for flight in flights:
        if flight[2] != mro:
            continue
        tail = owners[flight[0]]
        day = int(flight[4] // DAY) + 1
        start = (day - 1) * DAY + 22 * 60
        events.append({
            "tail": tail,
            "check": "A",
            "station": mro,
            "start": start,
            "end": start + 30,
            "release": start + 35,
            "trigger_flight": flight[0],
            "model_day": day,
        })
    certificate = {"assignment": assignments, "maintenance_events": events}
    option_b = certify_option_b_input(instance)
    if option_b["status"] != "SUPPORTED":
        raise ValueError(f"generated instance is not Option-B certified: {option_b['errors']}")
    replay = validate_benchmark_certificate(
        instance,
        certificate,
        capacity_semantics="simultaneous",
        strict_a_hour_limit=True,
    )
    if replay["status"] != "PASS" or not replay["milp_representable"]:
        raise ValueError(f"generated certificate failed independent replay: {replay}")
    return instance, certificate


def generate_family(output_dir: Path, fleet_sizes, horizons, replicates: int) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for fleet in fleet_sizes:
        for horizon in horizons:
            for replicate in range(replicates):
                instance, _certificate = build_instance(fleet, horizon, replicate)
                path = output_dir / f"profile_p={fleet}_h={horizon}_r={replicate}.json"
                path.write_text(json.dumps(instance, indent=2) + "\n", encoding="utf-8")
                count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "validation" / "profile_timing_20261118")
    parser.add_argument("--fleet-sizes", nargs="+", type=int, default=[3, 5])
    parser.add_argument("--horizons", nargs="+", type=int, default=[4, 5])
    parser.add_argument("--replicates", type=int, default=10)
    args = parser.parse_args()
    count = generate_family(args.output_dir, args.fleet_sizes, args.horizons, args.replicates)
    print(f"Generated {count} independently certified Option-A/B timing instances in {args.output_dir}")


if __name__ == "__main__":
    main()
