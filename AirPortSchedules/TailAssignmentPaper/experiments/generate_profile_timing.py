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

from src.benchmark_validation import (
    certify_option_a_input,
    certify_option_b_input,
    validate_benchmark_certificate,
)
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


def build_heterogeneous_instance(
    aircraft_count: int, horizon_days: int, replicate: int
) -> tuple[dict, dict]:
    if aircraft_count < 4 or horizon_days < 3 or replicate < 0:
        raise ValueError("require aircraft_count >= 4, horizon_days >= 3, replicate >= 0")

    rng = random.Random(stable_seed(0.80, aircraft_count, horizon_days, replicate))
    aircraft = list(range(aircraft_count))
    hub_count = min(4, max(2, aircraft_count // 5))
    spoke_count = min(8, max(3, aircraft_count // 2))
    hubs = [f"MRO{index}" for index in range(hub_count)]
    spokes = [f"S{index}" for index in range(spoke_count)]
    hub_for_tail = {tail: hubs[tail % hub_count] for tail in aircraft}
    spoke_for_tail = {tail: spokes[tail % spoke_count] for tail in aircraft}
    flights_with_owner = []
    next_id = 1

    for day in range(1, horizon_days):
        for tail in aircraft:
            outbound_offset = rng.randint(0, 35)
            outbound_duration = 50 + 10 * ((tail + day + replicate) % 5)
            outbound_departure = (day - 1) * DAY + 18 * 60 + outbound_offset
            outbound_arrival = outbound_departure + outbound_duration
            flights_with_owner.append((
                [next_id, spoke_for_tail[tail], hub_for_tail[tail],
                 float(outbound_departure), float(outbound_arrival)],
                tail,
            ))
            next_id += 1

            return_offset = rng.randint(0, 25)
            return_duration = 55 + 10 * ((2 * tail + day + replicate) % 5)
            return_departure = day * DAY + 6 * 60 + return_offset
            return_arrival = return_departure + return_duration
            flights_with_owner.append((
                [next_id, hub_for_tail[tail], spoke_for_tail[tail],
                 float(return_departure), float(return_arrival)],
                tail,
            ))
            next_id += 1

    flights_with_owner.sort(key=lambda item: (item[0][3], item[0][0]))
    flights = [flight for flight, _owner in flights_with_owner]
    owners = {flight[0]: owner for flight, owner in flights_with_owner}
    costs = []
    for flight, owner in flights_with_owner:
        costs.append([
            float(100 + rng.randint(0, 30)) if tail == owner
            else float(500 + 25 * (abs(int(flight[1][-1]) - int(hub_for_tail[tail][-1])) % 4) + rng.randint(0, 35))
            for tail in aircraft
        ])

    periods = {
        str(day): [(day - 1) * DAY + 20 * 60 + 30, (day - 1) * DAY + 22 * 60]
        for day in range(1, horizon_days + 1)
    }
    capacity = {hub: sum(hub_for_tail[tail] == hub for tail in aircraft) for hub in hubs}
    capacity.update({spoke: 0 for spoke in spokes})
    instance = {
        "Aircrafts": aircraft,
        "AIRCRAFT_INIT_POS": {str(tail): spoke_for_tail[tail] for tail in aircraft},
        "Flights": flights,
        "Cost_Matrix": costs,
        "Maintenance_Thresholds": {"A": 220, "B": 999999, "C": 9999, "D": 9999},
        "Maintenance_Durations": {"A": 30, "B": 30, "C": 30, "D": 30},
        "Station_Capacity": capacity,
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
            hub: {day: list(window) for day, window in periods.items()} for hub in hubs
        },
        "Protected_Maintenance_Periods": {
            day: list(window) for day, window in periods.items()
        },
        "Terminal_Release_Minutes": {
            str(tail): horizon_days * DAY for tail in aircraft
        },
        "Parameters": {
            "Min_Turn_Minutes": 30,
            "Target_Horizon_Days": horizon_days,
            "A_Calendar_Initial_Days": 0,
            "Topology": "shared_spokes_multi_hub",
            "Protected_Overnight_Maintenance": True,
        },
    }

    events = []
    for flight in flights:
        if flight[2] not in hubs:
            continue
        tail = owners[flight[0]]
        day = int(flight[4] // DAY) + 1
        start = periods[str(day)][0]
        events.append({
            "tail": tail,
            "check": "A",
            "station": flight[2],
            "start": start,
            "end": start + 30,
            "release": start + 35,
            "trigger_flight": flight[0],
            "model_day": day,
        })
    certificate = {
        "assignment": {str(flight): owners[flight] for flight in owners},
        "maintenance_events": events,
    }
    option_b = certify_option_b_input(instance)
    if option_b["status"] != "SUPPORTED":
        raise ValueError(f"generated heterogeneous instance is not Option-B certified: {option_b['errors']}")
    replay = validate_benchmark_certificate(
        instance,
        certificate,
        capacity_semantics="simultaneous",
        strict_a_hour_limit=True,
    )
    if replay["status"] != "PASS" or not replay["milp_representable"]:
        raise ValueError(f"generated heterogeneous certificate failed replay: {replay}")
    return instance, certificate


def build_option_a_overnight_instance(
    aircraft_count: int, horizon_days: int, replicate: int
) -> tuple[dict, dict]:
    if aircraft_count < 2 or horizon_days < 3 or replicate < 0:
        raise ValueError("require aircraft_count >= 2, horizon_days >= 3, replicate >= 0")

    rng = random.Random(stable_seed(0.85, aircraft_count, horizon_days, replicate))
    aircraft = list(range(aircraft_count))
    hubs = [f"MRO{index}" for index in range(min(2, aircraft_count))]
    spokes = [f"S{index}" for index in range(min(6, aircraft_count))]
    hub_for_tail = {tail: hubs[tail % len(hubs)] for tail in aircraft}
    spoke_for_tail = {tail: spokes[tail % len(spokes)] for tail in aircraft}
    flights_with_owner = []
    next_id = 1

    for night in range(horizon_days - 1):
        for tail in aircraft:
            departure = night * DAY + 23 * 60 + 25 + rng.randint(0, 15)
            duration = 55 + 5 * ((tail + night + replicate) % 4)
            arrival = departure + duration
            flights_with_owner.append((
                [next_id, spoke_for_tail[tail], hub_for_tail[tail],
                 float(departure), float(arrival)],
                tail,
            ))
            next_id += 1

            return_departure = (night + 1) * DAY + 7 * 60 + rng.randint(0, 25)
            return_arrival = return_departure + 55 + 5 * ((tail + night) % 4)
            flights_with_owner.append((
                [next_id, hub_for_tail[tail], spoke_for_tail[tail],
                 float(return_departure), float(return_arrival)],
                tail,
            ))
            next_id += 1

    flights_with_owner.sort(key=lambda item: (item[0][3], item[0][0]))
    flights = [flight for flight, _owner in flights_with_owner]
    owners = {flight[0]: owner for flight, owner in flights_with_owner}
    costs = []
    for flight, owner in flights_with_owner:
        costs.append([
            float(100 + rng.randint(0, 25)) if tail == owner
            else float(550 + rng.randint(0, 60))
            for tail in aircraft
        ])

    windows = {
        str(day): [(day - 1) * DAY + 45, (day - 1) * DAY + 120]
        for day in range(1, horizon_days + 1)
    }
    capacity = {hub: sum(hub_for_tail[tail] == hub for tail in aircraft) for hub in hubs}
    capacity.update({spoke: 0 for spoke in spokes})
    instance = {
        "Aircrafts": aircraft,
        "AIRCRAFT_INIT_POS": {str(tail): spoke_for_tail[tail] for tail in aircraft},
        "Flights": flights,
        "Cost_Matrix": costs,
        "Maintenance_Thresholds": {"A": 220, "B": 999999, "C": 9999, "D": 9999},
        "Maintenance_Durations": {"A": 30, "B": 30, "C": 30, "D": 30},
        "Station_Capacity": capacity,
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
            hub: {day: list(window) for day, window in windows.items()} for hub in hubs
        },
        "Terminal_Release_Minutes": {
            str(tail): horizon_days * DAY for tail in aircraft
        },
        "Parameters": {
            "Min_Turn_Minutes": 30,
            "Target_Horizon_Days": horizon_days,
            "A_Calendar_Initial_Days": 0,
            "Topology": "shared_spokes_multi_hub",
            "Cross_Midnight_Flights": True,
            "Overnight_Maintenance_Policy": "option_a_only",
        },
    }

    events = []
    for flight in flights:
        if flight[2] not in hubs:
            continue
        tail = owners[flight[0]]
        day = int(flight[4] // DAY) + 1
        lower, _upper = windows[str(day)]
        start = max(float(flight[4]), float(lower))
        events.append({
            "tail": tail,
            "check": "A",
            "station": flight[2],
            "start": start,
            "end": start + 30,
            "release": start + 35,
            "trigger_flight": flight[0],
            "model_day": day,
        })
    certificate = {
        "assignment": {str(flight): owners[flight] for flight in owners},
        "maintenance_events": events,
    }
    option_a = certify_option_a_input(instance)
    if option_a["status"] != "SUPPORTED":
        raise ValueError(f"generated overnight instance is not Option-A certified: {option_a['errors']}")
    if certify_option_b_input(instance)["status"] != "UNSUPPORTED":
        raise ValueError("overnight crossing instance unexpectedly passed Option-B certification")
    replay = validate_benchmark_certificate(
        instance,
        certificate,
        capacity_semantics="simultaneous",
        strict_a_hour_limit=True,
    )
    if replay["status"] != "PASS" or not replay["milp_representable"]:
        raise ValueError(f"generated overnight certificate failed replay: {replay}")
    return instance, certificate


def generate_family(
    output_dir: Path, fleet_sizes, horizons, replicates: int, family: str = "regular"
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    builders = {
        "regular": build_instance,
        "heterogeneous": build_heterogeneous_instance,
        "option_a_overnight": build_option_a_overnight_instance,
    }
    builder = builders[family]
    count = 0
    for fleet in fleet_sizes:
        for horizon in horizons:
            for replicate in range(replicates):
                instance, _certificate = builder(fleet, horizon, replicate)
                path = output_dir / f"profile_{family}_p={fleet}_h={horizon}_r={replicate}.json"
                path.write_text(json.dumps(instance, indent=2) + "\n", encoding="utf-8")
                count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "validation" / "profile_timing_20261118")
    parser.add_argument("--fleet-sizes", nargs="+", type=int, default=[3, 5])
    parser.add_argument("--horizons", nargs="+", type=int, default=[4, 5])
    parser.add_argument("--replicates", type=int, default=10)
    parser.add_argument(
        "--family",
        choices=("regular", "heterogeneous", "option_a_overnight"),
        default="regular",
    )
    args = parser.parse_args()
    count = generate_family(
        args.output_dir, args.fleet_sizes, args.horizons, args.replicates, args.family
    )
    print(f"Generated {count} independently certified Option-A/B timing instances in {args.output_dir}")


if __name__ == "__main__":
    main()
