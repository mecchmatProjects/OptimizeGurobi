"""Create test JSON instances for heu180h.py.

The generator writes files named like:
    DataCplex_density=1_p=10_h=7_test_0.json

Usage examples:
    py -3 test_create.py 1 10 7 5
    py -3 test_create.py 0.5 20 15 3 --output-dir Inputs3
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import string
from typing import cast
from pathlib import Path


DAY_SHIFT = 24 * 60


def make_airports(count: int) -> list[str]:
    """Return airport codes A, B, ..., Z, AA, AB, ..."""
    airports: list[str] = []
    letters = string.ascii_uppercase
    width = 1
    while len(airports) < count:
        if width == 1:
            airports.extend(list(letters))
        else:
            for prefix in letters:
                for suffix in letters:
                    airports.append(prefix + suffix)
                    if len(airports) >= count:
                        break
                if len(airports) >= count:
                    break
        width += 1
    return airports[:count]


def stable_seed(density: float, p: int, h: int, index: int) -> int:
    """Create a deterministic seed from the generation parameters."""
    density_key = int(round(density * 1000))
    return density_key * 1_000_000 + p * 10_000 + h * 100 + index


def build_instance(
    density: float,
    p: int,
    h: int,
    index: int,
    airport_override: int | None = None,
    flights_override: int | None = None,
) -> dict:
    rng = random.Random(stable_seed(density, p, h, index))

    airport_count = airport_override if airport_override is not None else max(4, min(12, p // 2 + 4))
    airports = make_airports(airport_count)

    flights_target = flights_override if flights_override is not None else max(p * 2, int(round(density * p * h)))
    flights: list[list[object]] = []

    for fid in range(1, flights_target + 1):
        day = rng.randrange(max(1, h))
        dep = day * DAY_SHIFT + rng.randint(6 * 60, 20 * 60)
        duration = rng.randint(60, 180)
        arr = dep + duration

        origin = rng.choice(airports)
        destinations = [ap for ap in airports if ap != origin]
        dest = rng.choice(destinations)

        flights.append([fid, origin, dest, float(dep), float(arr)])

    flights.sort(key=lambda row: (row[3], row[0]))
    for new_id, flight in enumerate(flights, start=1):
        flight[0] = new_id

    aircrafts = list(range(p))
    init_pos = {str(aid): rng.choice(airports) for aid in aircrafts}

    # A/B are in minutes; C/D are in days.
    # Keep C/D comfortably beyond the horizon so the generated tests remain
    # easy to solve while still matching the solver's expected schema.
    thresholds = {
        "A": 900,
        "B": 1800,
        "C": max(h + 2, 10),
        "D": max(h + 5, 14),
    }

    durations = {
        "A": 90,
        "B": 180,
        "C": 1440,
        "D": 2880,
    }

    station_capacity = {airport: 1 for airport in airports}

    initial_checks = {
        "A": {str(aid): 0 for aid in aircrafts},
        "B": {str(aid): 0 for aid in aircrafts},
        "C_Days": {str(aid): 0 for aid in aircrafts},
        "D_Days": {str(aid): 0 for aid in aircrafts},
    }

    cost_matrix = []
    for flight in flights:
        _, origin, dest, dep, arr = flight
        origin_index = airports.index(cast(str, origin))
        dest_index = airports.index(cast(str, dest))
        duration = int(cast(float, arr) - cast(float, dep))
        row = []
        for aid in aircrafts:
            row.append(
                100 + 5 * duration + 8 * abs(origin_index - dest_index) + 3 * aid + rng.randint(0, 25)
            )
        cost_matrix.append(row)

    return {
        "Aircrafts": aircrafts,
        "AIRCRAFT_INIT_POS": init_pos,
        "Flights": flights,
        "Maintenance_Thresholds": thresholds,
        "Maintenance_Durations": durations,
        "Station_Capacity": station_capacity,
        "Initial_Checks": initial_checks,
        "Cost_Matrix": cost_matrix,
    }


def output_name(density: float, p: int, h: int, index: int) -> str:
    density_text = f"{density:g}"
    return f"DataCplex_density={density_text}_p={p}_h={h}_test_{index}.json"


class LocalScheduler:
    """Dependency-free copy of the greedy objective used by heu180h.py."""

    def __init__(self, data: dict):
        self.data = data
        self.flights = {
            int(fl[0]): {
                "fid": int(fl[0]),
                "orig": str(fl[1]),
                "dest": str(fl[2]),
                "dep": float(fl[3]),
                "arr": float(fl[4]),
                "dur": float(fl[4]) - float(fl[3]),
            }
            for fl in self.data["Flights"]
        }
        self.aircrafts = list(self.data["Aircrafts"])
        self.init_pos = self.data["AIRCRAFT_INIT_POS"]
        self.init_checks = self.data["Initial_Checks"]
        self.thresh_ab = {
            "A": float(self.data["Maintenance_Thresholds"]["A"]),
            "B": float(self.data["Maintenance_Thresholds"]["B"]),
        }
        self.thresh_cd = {
            "C": float(self.data["Maintenance_Thresholds"]["C"]),
            "D": float(self.data["Maintenance_Thresholds"]["D"]),
        }
        self.durations = {k: float(v) for k, v in self.data["Maintenance_Durations"].items()}
        self.station_cap = self.data["Station_Capacity"]
        self.cost_matrix = self.data["Cost_Matrix"]
        self.ferry_time = 60
        self.ferry_cost = 6000

    def _init_counters(self, aid: int) -> tuple[float, float, float, float]:
        sid = str(aid)
        ic = self.init_checks
        a = float(ic.get("A", {}).get(sid, 0))
        b = float(ic.get("B", {}).get(sid, 0))
        c = float(ic.get("C_Days", ic.get("C", {})).get(sid, 0))
        d = float(ic.get("D_Days", ic.get("D", {})).get(sid, 0))
        return a, b, c, d

    @staticmethod
    def _reset_counters(needed: str, a: float, b: float, c_days: float, t_now_min: float):
        t_days = t_now_min / 1440.0
        if needed == "D":
            return 0.0, 0.0, -t_days, -t_days
        if needed == "C":
            return 0.0, 0.0, -t_days, None
        if needed == "B":
            return 0.0, 0.0, None, None
        return 0.0, None, None, None

    def get_timeline(self, aid: int, fids: list[int]):
        curr_apt = self.init_pos[str(aid)]
        curr_time = 0.0
        a, b, c_off, d_off = self._init_counters(aid)
        events = []
        total_cost = 0.0

        for fid in fids:
            fl = self.flights[fid]

            if curr_apt != fl["orig"]:
                if curr_time + self.ferry_time > fl["dep"]:
                    return None
                events.append({"kind": "FERRY", "start": curr_time, "end": curr_time + self.ferry_time})
                curr_time += self.ferry_time
                curr_apt = fl["orig"]
                total_cost += self.ferry_cost

            days_now = curr_time / 1440.0
            needed = None
            if d_off + days_now >= self.thresh_cd["D"]:
                needed = "D"
            elif c_off + days_now >= self.thresh_cd["C"]:
                needed = "C"
            elif b + fl["dur"] >= self.thresh_ab["B"]:
                needed = "B"
            elif a + fl["dur"] >= self.thresh_ab["A"]:
                needed = "A"

            if needed:
                m_dur = self.durations[needed]
                if curr_time + m_dur > fl["dep"]:
                    return None
                if int(self.station_cap.get(fl["orig"], 0)) == 0:
                    return None
                events.append({"kind": "MAINT", "check": needed, "start": curr_time, "end": curr_time + m_dur})
                curr_time += m_dur
                na, nb, nc, nd = self._reset_counters(needed, a, b, c_off, curr_time)
                if na is not None:
                    a = na
                if nb is not None:
                    b = nb
                if nc is not None:
                    c_off = nc
                if nd is not None:
                    d_off = nd

            if curr_time > fl["dep"]:
                return None

            events.append({"kind": "FLIGHT", "fid": fid, "start": fl["dep"], "end": fl["arr"]})
            curr_time = fl["arr"]
            curr_apt = fl["dest"]
            a += fl["dur"]
            b += fl["dur"]
            total_cost += self.cost_matrix[fid - 1][aid]

        return {"events": events, "cost": total_cost}

    def optimize(self):
        ac_fids = {aid: [] for aid in self.aircrafts}
        assigned = set()
        sorted_fids = sorted(self.flights.keys(), key=lambda x: self.flights[x]["dep"])

        for fid in sorted_fids:
            best_opt = None
            for aid in self.aircrafts:
                res = self.get_timeline(aid, ac_fids[aid] + [fid])
                if res and (best_opt is None or res["cost"] < best_opt[0]):
                    best_opt = (res["cost"], aid)
            if best_opt:
                ac_fids[best_opt[1]].append(fid)
                assigned.add(fid)

        for _ in range(5):
            still_unassigned = [fid for fid in self.flights if fid not in assigned]
            for fid in still_unassigned:
                best_ins = None
                for aid in self.aircrafts:
                    for i in range(len(ac_fids[aid]) + 1):
                        trial = ac_fids[aid][:i] + [fid] + ac_fids[aid][i:]
                        res = self.get_timeline(aid, trial)
                        if res and (best_ins is None or res["cost"] < best_ins[2]):
                            best_ins = (aid, i, res["cost"])
                if best_ins:
                    aid, idx, _ = best_ins
                    ac_fids[aid].insert(idx, fid)
                    assigned.add(fid)

        return ac_fids, [fid for fid in self.flights if fid not in assigned]


def evaluate_objective(data_path: Path) -> dict[str, object]:
    """Evaluate the generated file with the same greedy objective as heu180h.py."""
    with data_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    scheduler = LocalScheduler(data)
    final_ac_fids, unassigned = scheduler.optimize()
    objective = 0.0
    for aid in scheduler.aircrafts:
        timeline = scheduler.get_timeline(aid, final_ac_fids[aid])
        if timeline:
            objective += timeline["cost"]

    assigned = sum(len(final_ac_fids[aid]) for aid in scheduler.aircrafts)
    return {
        "status": "ok",
        "objective": round(objective, 2),
        "assigned": assigned,
        "unassigned": len(unassigned),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate heu180h.py test JSON files.")
    parser.add_argument("density", nargs="?", type=float, default=1.0, help="Flight density used in the file name")
    parser.add_argument("p", nargs="?", type=int, default=10, help="Number of aircraft (legacy positional)")
    parser.add_argument("h", nargs="?", type=int, default=7, help="Planning horizon in days")
    parser.add_argument("count", nargs="?", type=int, default=1, help="Number of test files to create")
    parser.add_argument("--planes", type=int, default=None, help="Override number of aircraft in test files")
    parser.add_argument("--airports", type=int, default=None, help="Override number of airports in test files")
    parser.add_argument("--flights", type=int, default=None, help="Override number of flights in test files")
    parser.add_argument("--output-dir", default="Inputs", help="Directory that will receive the JSON files")
    parser.add_argument("--summary-file", default=None, help="CSV file that stores objective values for the generated files")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    planes = args.planes if args.planes is not None else args.p

    if args.density <= 0:
        raise SystemExit("density must be positive")
    if planes <= 0:
        raise SystemExit("p must be positive")
    if args.h <= 0:
        raise SystemExit("h must be positive")
    if args.count <= 0:
        raise SystemExit("count must be positive")
    if args.airports is not None and args.airports <= 1:
        raise SystemExit("airports must be >= 2")
    if args.flights is not None and args.flights <= 0:
        raise SystemExit("flights must be positive")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, object]] = []

    for index in range(args.count):
        data = build_instance(
            args.density,
            planes,
            args.h,
            index,
            airport_override=args.airports,
            flights_override=args.flights,
        )
        path = output_dir / output_name(args.density, planes, args.h, index)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=4)
        metrics = evaluate_objective(path)
        summary_rows.append({
            "file": path.name,
            "density": args.density,
            "p": planes,
            "h": args.h,
            "airports": args.airports if args.airports is not None else len(data["Station_Capacity"]),
            "flights": args.flights if args.flights is not None else len(data["Flights"]),
            "objective": metrics["objective"],
            "assigned": metrics["assigned"],
            "unassigned": metrics["unassigned"],
            "status": metrics["status"],
        })
        print(f"Wrote {path} | objective={metrics['objective']} | status={metrics['status']}")

    summary_file = Path(args.summary_file) if args.summary_file else output_dir / "test_create_summary.csv"
    with summary_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["file", "density", "p", "h", "airports", "flights", "objective", "assigned", "unassigned", "status"],
        )
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"Summary written to {summary_file}")


if __name__ == "__main__":
    main()