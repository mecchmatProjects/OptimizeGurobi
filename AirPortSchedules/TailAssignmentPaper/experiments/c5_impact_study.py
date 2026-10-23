"""experiments/c5_impact_study.py

Quantify the practical effect of the C5 non-overlap correction.

For each instance the pure flight-assignment problem (no maintenance) is
solved twice with the same solver: the legacy rows C1-C4 only, and the
corrected rows C1-C5.  The legacy incumbent is replayed to count (i) pairs of
flights on one aircraft whose occupation intervals [dep, arr + turn) intersect
and (ii) continuity breaks along each aircraft's chronological route.

Usage
-----
  python experiments/c5_impact_study.py --solver gurobi --time-limit 300 \
      --inputs data/five_method_longflight_e14_e21_compact/perf_p=*.json
"""

from __future__ import annotations

import argparse
import contextlib
import glob
import io
import json
import logging
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import model as tap_model  # noqa: E402
from pyomo.environ import value as pyo_value  # noqa: E402

LOGGER = logging.getLogger("c5_impact")
TURN = tap_model.MILP_Sheduler.MIN_TURN


def instance_profile(data: dict) -> dict:
    flights = data["Flights"]
    by_time = defaultdict(int)
    for _, origin, _, dep, _ in flights:
        by_time[(origin, dep)] += 1
    equal_pairs = sum(n * (n - 1) // 2 for n in by_time.values())
    conflicts = 0
    ordered = sorted(flights, key=lambda f: f[3])
    for a, fa in enumerate(ordered):
        for fb in ordered[a + 1:]:
            if fb[3] >= fa[4] + TURN:
                break
            conflicts += 1
    return {
        "F": len(flights),
        "P": len(data["Aircrafts"]),
        "H": int(max(f[4] for f in flights) // 1440) + 1,
        "equal_time_pairs": equal_pairs,
        "conflict_pairs_all_aircraft_independent": conflicts,
    }


def replay(data: dict, assignment: dict[int, int]) -> dict:
    """Count interval overlaps and continuity breaks for an assignment."""
    flights = {f[0]: f for f in data["Flights"]}
    init = {int(k): v for k, v in data["AIRCRAFT_INIT_POS"].items()}
    routes = defaultdict(list)
    for fid, aid in assignment.items():
        routes[aid].append(flights[fid])
    overlaps = breaks = bad_aircraft = 0
    for aid, route in routes.items():
        route.sort(key=lambda f: (f[3], f[0]))
        ov = br = 0
        for a, fa in enumerate(route):
            for fb in route[a + 1:]:
                if fb[3] >= fa[4] + TURN:
                    break
                ov += 1
        position = init[aid]
        for f in route:
            if f[1] != position:
                br += 1
            position = f[2]
        overlaps += ov
        breaks += br
        bad_aircraft += int(ov > 0 or br > 0)
    return {
        "replay_overlap_pairs": overlaps,
        "replay_continuity_breaks": breaks,
        "replay_violating_aircraft": bad_aircraft,
    }


def solve_variant(path: Path, solver: str, executable: str | None,
                  time_limit: int, overlap: bool) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    opt = tap_model.MILP_Sheduler(str(path))
    opt.build_model(use_maintenance=False, use_overlap=overlap, use_sanity=False)
    options = {"Threads": 1, "MIPGap": 0} if "gurobi" in solver else {"threads": 1}
    with contextlib.redirect_stdout(io.StringIO()):
        summary = opt.solve(solver_name=solver, time_limit=time_limit,
                            executable=executable, solver_options=options)
    row = {
        "formulation": "C1-C5" if overlap else "C1-C4",
        "status": summary["status"],
        "objective": summary["obj"],
        "gap_pct": None if summary["gap"] is None else 100 * summary["gap"],
        "cpu_s": summary["cpu"],
        "constraints": summary["n_cons"],
        "x_vars": sum(len(list(opt._x_aircrafts_for_flight(i))) for i in opt.model.F),
    }
    if summary["has_solution"]:
        assignment = {
            i: j for i in opt.model.F for j in opt._x_aircrafts_for_flight(i)
            if pyo_value(opt.model.x[i, j]) > 0.5
        }
        row.update(replay(data, assignment))
    return row


def flat_cost_variant(data: dict) -> dict:
    """Aircraft-neutral costs: the per-flight mean plus 3 per aircraft index.

    The shipped instances price the designated rotation aircraft about 500 units
    below every other tail, which removes any incentive to exploit a modelling
    gap.  The flat variant keeps every flight's cost scale and leaves only the
    mild preference for low-index aircraft present in the generator.
    """
    out = dict(data)
    out["Cost_Matrix"] = [
        [round(sum(row) / len(row)) + 3 * j for j in range(len(row))]
        for row in data["Cost_Matrix"]
    ]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--solver", default="gurobi")
    parser.add_argument("--executable", default=None)
    parser.add_argument("--time-limit", type=int, default=300)
    parser.add_argument("--output", default="results/tables/c5_impact_20261021.csv")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    files = sorted({Path(p) for pattern in args.inputs for p in glob.glob(pattern)})
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for path in tqdm(files, desc="instances"):
            data = json.loads(path.read_text(encoding="utf-8"))
            profile = instance_profile(data)
            flat_path = Path(tmp) / path.name
            flat_path.write_text(json.dumps(flat_cost_variant(data)), encoding="utf-8")
            for cost_variant, source in (("shipped", path), ("flat", flat_path)):
                for overlap in (False, True):
                    row = {"stem": path.stem, "cost_variant": cost_variant, **profile,
                           "solver": args.solver, "nodes_max": None}
                    row.update(solve_variant(source, args.solver, args.executable,
                                             args.time_limit, overlap))
                    row["vars"] = row["x_vars"]
                    rows.append(row)
                    LOGGER.info("%s %s %s status=%s obj=%s", path.stem, cost_variant,
                                row["formulation"], row["status"], row["objective"])
                    pd.DataFrame(rows).to_csv(args.output, index=False)


if __name__ == "__main__":
    main()
