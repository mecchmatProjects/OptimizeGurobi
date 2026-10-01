from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random

from generate_instances import DAY_SHIFT, LocalScheduler, output_name, stable_seed


def _active_families(families: str) -> list[str]:
    mapping = {
        "A": ["A"],
        "AB": ["A", "B"],
        "ABCD": ["A", "B", "C", "D"],
    }
    return mapping[families]


def _build_thresholds(horizon_days: int, families: str) -> tuple[dict[str, int], dict[str, int]]:
    thresholds = {
        "A": 270,
        "B": 540,
        "C": 8 if families == "ABCD" else max(horizon_days + 3, 30),
        "D": 10 if families == "ABCD" else max(horizon_days + 7, 45),
    }
    durations = {
        "A": 60,
        "B": 120,
        "C": 240,
        "D": 360,
    }
    return thresholds, durations


def build_feasible_instance(
    density: float,
    p: int,
    h: int,
    index: int,
    flights_per_aircraft: int | None = None,
    maintenance_families: str = "A",
) -> dict:
    rng = random.Random(stable_seed(density, p, h, index))

    maintenance_airport = "MRO"
    spoke_airports = [f"S{aid}" for aid in range(p)]
    airports = [maintenance_airport, *spoke_airports]
    thresholds, durations = _build_thresholds(h, maintenance_families)
    active_families = _active_families(maintenance_families)
    max_active_maint_dur = max(durations[family] for family in active_families)

    aircrafts = list(range(p))
    init_pos = {str(aid): spoke_airports[aid] for aid in aircrafts}
    station_capacity = {maintenance_airport: p, **{spoke: 0 for spoke in spoke_airports}}

    initial_checks = {
        "A": {str(aid): 0 for aid in aircrafts},
        "B": {str(aid): 0 for aid in aircrafts},
        "C_Days": {str(aid): 0 for aid in aircrafts},
        "D_Days": {str(aid): 0 for aid in aircrafts},
    }

    rotations = flights_per_aircraft
    if rotations is None:
        rotations = max(2, int(round(density * max(2, h))))
        if maintenance_families == "AB":
            rotations = min(rotations, 2)
        elif maintenance_families == "ABCD":
            rotations = 1
    elif maintenance_families == "ABCD":
        rotations = min(rotations, 1)

    flights: list[list[object]] = []
    rotations_by_aircraft: dict[int, list[int]] = {aid: [] for aid in aircrafts}
    primary_family_by_aircraft: dict[int, str] = {}
    fid = 1
    for aid in aircrafts:
        spoke = spoke_airports[aid]
        primary_family = active_families[aid % len(active_families)]
        primary_family_by_aircraft[aid] = primary_family
        current_day = aid % max(1, h)
        if primary_family in {"C", "D"}:
            current_day = max(1, current_day)
        # Day spacing keeps per-aircraft rotations non-overlapping and leaves
        # explicit maintenance slack at the maintenance airport.
        for rot in range(rotations):
            outbound_dep = current_day * DAY_SHIFT + 6 * 60 + (aid % 4) * 15
            outbound_dur = 90
            outbound_arr = outbound_dep + outbound_dur
            out_orig = spoke
            out_dest = maintenance_airport
            flights.append([fid, out_orig, out_dest, float(outbound_dep), float(outbound_arr)])
            rotations_by_aircraft[aid].append(fid)
            fid += 1

            if rot == 0:
                # Force the first designated check family to trigger at the
                # maintenance airport before the first return flight.
                if primary_family == "A":
                    initial_checks["A"][str(aid)] = max(0, thresholds["A"] - (outbound_dur + 45))
                elif primary_family == "B":
                    initial_checks["B"][str(aid)] = max(0, thresholds["B"] - (outbound_dur + 45))
                elif primary_family == "C":
                    initial_checks["C_Days"][str(aid)] = max(0.0, thresholds["C"] - (current_day + 0.25))
                elif primary_family == "D":
                    initial_checks["D_Days"][str(aid)] = max(0.0, thresholds["D"] - (current_day + 0.25))

            maint_buffer = max_active_maint_dur + 60
            return_dep = outbound_arr + maint_buffer
            return_dur = 90
            return_arr = return_dep + return_dur
            ret_orig = maintenance_airport
            ret_dest = spoke
            flights.append([fid, ret_orig, ret_dest, float(return_dep), float(return_arr)])
            rotations_by_aircraft[aid].append(fid)
            fid += 1

            # Advance to ensure day-based checks remain feasible while still
            # allowing them to trigger on longer horizons.
            current_day += 2 if rot % 2 == 0 else 1
            if current_day >= h:
                break

    flights.sort(key=lambda row: (row[3], row[0]))
    old_to_new: dict[int, int] = {}
    for new_id, flight in enumerate(flights, start=1):
        old_to_new[int(flight[0])] = new_id
        flight[0] = new_id
    rotations_by_aircraft = {
        aid: [old_to_new[fid] for fid in rotation]
        for aid, rotation in rotations_by_aircraft.items()
    }

    cost_matrix: list[list[float]] = []
    for flight in flights:
        origin = str(flight[1])
        dest = str(flight[2])
        duration = int(float(flight[4]) - float(flight[3]))
        row: list[float] = []
        for aid in aircrafts:
            preferred_spoke = spoke_airports[aid]
            penalty = 0 if origin == preferred_spoke or dest == preferred_spoke else 500
            row.append(float(100 + 4 * duration + penalty + rng.randint(0, 10)))
        cost_matrix.append(row)

    data = {
        "Aircrafts": aircrafts,
        "AIRCRAFT_INIT_POS": init_pos,
        "Flights": flights,
        "Maintenance_Thresholds": thresholds,
        "Maintenance_Durations": durations,
        "Station_Capacity": station_capacity,
        "Initial_Checks": initial_checks,
        "Cost_Matrix": cost_matrix,
    }

    scheduler = LocalScheduler(data)
    for aid, rotation in rotations_by_aircraft.items():
        timeline = scheduler.get_timeline(aid, rotation)
        if timeline is None:
            raise RuntimeError(
                f"Constructed rotation for aircraft {aid} is not maintenance-feasible"
            )
    data["_SeededRotation"] = {str(aid): rotation for aid, rotation in rotations_by_aircraft.items()}
    data["_PrimaryFamily"] = {str(aid): family for aid, family in primary_family_by_aircraft.items()}
    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate maintenance-feasible TAP instances from seeded aircraft rotations."
    )
    parser.add_argument("density", nargs="?", type=float, default=0.5)
    parser.add_argument("p", nargs="?", type=int, default=6)
    parser.add_argument("h", nargs="?", type=int, default=7)
    parser.add_argument("count", nargs="?", type=int, default=1)
    parser.add_argument("--flights-per-aircraft", type=int, default=None)
    parser.add_argument(
        "--maintenance-families",
        choices=["A", "AB", "ABCD"],
        default="A",
        help="Maintenance families intentionally triggered by the seeded rotations.",
    )
    parser.add_argument("--output-dir", default="data/feasible_instances")
    parser.add_argument("--summary-file", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.density <= 0:
        raise SystemExit("density must be positive")
    if args.p <= 0:
        raise SystemExit("p must be positive")
    if args.h <= 0:
        raise SystemExit("h must be positive")
    if args.count <= 0:
        raise SystemExit("count must be positive")
    if args.flights_per_aircraft is not None and args.flights_per_aircraft <= 0:
        raise SystemExit("flights-per-aircraft must be positive")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, object]] = []

    for index in range(args.count):
        data = build_feasible_instance(
            args.density,
            args.p,
            args.h,
            index,
            flights_per_aircraft=args.flights_per_aircraft,
            maintenance_families=args.maintenance_families,
        )
        path = output_dir / output_name(args.density, args.p, args.h, index)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=4)

        scheduler = LocalScheduler(data)
        seeded_rotation = {int(aid): flights for aid, flights in data["_SeededRotation"].items()}
        assigned = sum(len(flights) for flights in seeded_rotation.values())
        unassigned = max(0, len(data["Flights"]) - assigned)
        objective = 0.0
        for aid in scheduler.aircrafts:
            timeline = scheduler.get_timeline(aid, seeded_rotation[aid])
            if timeline:
                objective += float(timeline["cost"])

        summary_rows.append({
            "file": path.name,
            "density": args.density,
            "p": args.p,
            "h": args.h,
            "flights": len(data["Flights"]),
            "assigned": assigned,
            "unassigned": unassigned,
            "objective": round(objective, 2),
            "maintenance_families": args.maintenance_families,
            "status": "ok" if not unassigned else "partial",
        })
        print(f"Wrote {path} | flights={len(data['Flights'])} | assigned={assigned} | unassigned={unassigned}")

    summary_file = Path(args.summary_file) if args.summary_file else output_dir / "feasible_summary.csv"
    with summary_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["file", "density", "p", "h", "flights", "assigned", "unassigned", "objective", "maintenance_families", "status"],
        )
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"Summary written to {summary_file}")


if __name__ == "__main__":
    main()