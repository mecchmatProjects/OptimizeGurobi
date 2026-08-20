"""Compare the legacy endpoint-split MILP with the exact-state event MILP.

Examples
--------
Build both formulations on the quick Khaled-grid subset without solving::

    python experiments/compare_formulations.py --quick --build-only

Solve one instance with the same solver and time limit::

    python experiments/compare_formulations.py \
        --instances data/instances/DataCplex_density=1_p=10_h=7_test_0.json \
        --solver cplex --time-limit 300

Run all matching instances::

    python experiments/compare_formulations.py --full --solver cplex
"""

import argparse
import csv
import math
import re
import sys
import time
from pathlib import Path

from pyomo.common.errors import ApplicationError
from pyomo.environ import Constraint, Var
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_COLUMNS = [
    "stem",
    "P",
    "H",
    "F",
    "vars",
    "constraints",
    "nodes_max",
    "gap_pct",
    "cpu_s",
    "objective",
]
EXTRA_COLUMNS = [
    "formulation",
    "routing_scope",
    "status",
    "build_s",
    "wall_s",
    "solver",
    "time_limit_s",
    "error",
]

FORMULATIONS = ("legacy_endpoint_split", "event_exact_state")
ROUTING_SCOPES = {
    "legacy_endpoint_split": "legacy_day_indexed_routing",
    "event_exact_state": "connected_event_arcs_no_ferry",
}


def finite_number(value):
    """Return a finite float, or ``None`` for absent/non-finite metrics."""
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def instance_metadata(path):
    """Return the common instance dimensions used in experiment CSV files."""
    import json

    with open(path, encoding="utf-8") as input_file:
        data = json.load(input_file)
    flights = data["Flights"]
    horizon = math.ceil(max(float(flight[4]) for flight in flights) / 1440.0)
    return {
        "stem": Path(path).stem,
        "P": len(data["Aircrafts"]),
        "H": horizon,
        "F": len(flights),
    }


def model_size(model):
    """Count active scalar Pyomo variables and constraints."""
    variables = len(list(model.component_data_objects(Var, active=True)))
    constraints = len(
        list(model.component_data_objects(Constraint, active=True))
    )
    return variables, constraints


def build_scheduler(formulation, instance_path, strict_legacy_state=False):
    """Construct one formulation and return its scheduler and build time."""
    from src.event_model import EventMILPScheduler
    from src.model import LegacyEndpointSplitMILPScheduler

    started = time.perf_counter()
    if formulation == "legacy_endpoint_split":
        scheduler = LegacyEndpointSplitMILPScheduler(str(instance_path))
        scheduler.build_model(use_strict_hour_state=strict_legacy_state)
    elif formulation == "event_exact_state":
        scheduler = EventMILPScheduler(str(instance_path))
        scheduler.build_model()
    else:
        raise ValueError(f"Unknown formulation: {formulation}")
    if scheduler.FORMULATION_ID != formulation:
        raise RuntimeError(
            f"Selected {formulation}, built {scheduler.FORMULATION_ID}"
        )
    return scheduler, time.perf_counter() - started


def benchmark_one(
    instance_path,
    formulation,
    solver_name,
    time_limit,
    build_only,
    tee,
    executable=None,
    strict_legacy_state=False,
):
    """Build and optionally solve one formulation, returning one CSV row."""
    row = instance_metadata(instance_path)
    row.update({
        "formulation": formulation,
        "routing_scope": ROUTING_SCOPES[formulation],
        "solver": solver_name,
        "time_limit_s": time_limit,
        "nodes_max": "",
        "gap_pct": "",
        "cpu_s": "",
        "objective": "",
        "wall_s": "",
        "status": "build_only" if build_only else "",
        "error": "",
    })

    try:
        scheduler, build_seconds = build_scheduler(
            formulation, instance_path, strict_legacy_state=strict_legacy_state
        )
        variables, constraints = model_size(scheduler.model)
        row.update({
            "build_s": round(build_seconds, 6),
            "vars": variables,
            "constraints": constraints,
        })
        if build_only:
            return row

        report_dir = ROOT / "results" / "tables" / "formulation_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{row['stem']}_{formulation}.txt"
        solve_started = time.perf_counter()
        summary = scheduler.solve(
            solver_name=solver_name,
            tee=tee,
            out_path=str(report_path),
            time_limit=time_limit,
            warm_start=False,
            executable=executable,
        )
        if summary.get("formulation") != formulation:
            raise RuntimeError(
                f"Solved {summary.get('formulation')}, expected {formulation}"
            )
        gap_value = finite_number(summary.get("gap"))
        cpu_value = finite_number(summary.get("cpu"))
        objective_value = finite_number(summary.get("obj"))
        row.update({
            "status": summary["status"],
            "gap_pct": (
                round(gap_value * 100.0, 6)
                if gap_value is not None
                else ""
            ),
            "cpu_s": (
                round(cpu_value, 6)
                if cpu_value is not None
                else ""
            ),
            "objective": (
                round(objective_value, 6)
                if objective_value is not None
                else ""
            ),
            "wall_s": round(time.perf_counter() - solve_started, 6),
        })
    except (ApplicationError, KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
        row.setdefault("build_s", "")
        row.setdefault("vars", "")
        row.setdefault("constraints", "")
        row["status"] = "ERROR"
        row["error"] = f"{type(error).__name__}: {error}"
    return row


def parse_grid_dimensions(path):
    """Extract ``p`` and ``h`` from canonical DataCplex filenames."""
    match = re.search(r"_p=(\d+)_h=(\d+)_", Path(path).name)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def select_instances(args):
    """Resolve explicit, quick, or full instance selections."""
    if args.instances:
        return [Path(path) for path in args.instances]

    candidates = sorted(Path(args.input_dir).glob(args.pattern))
    if args.full:
        return candidates

    quick_dimensions = {(10, 7), (10, 15), (20, 7), (20, 15)}
    return [
        path
        for path in candidates
        if parse_grid_dimensions(path) in quick_dimensions
    ]


def write_results(rows, output_path):
    """Write comparison rows using the repository experiment schema."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = REQUIRED_COLUMNS + EXTRA_COLUMNS
    with open(output_path, "w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--quick",
        action="store_true",
        help="Run h={7,15}, p={10,20}; this is the default selection.",
    )
    selection.add_argument(
        "--full",
        action="store_true",
        help="Run every instance matching --pattern.",
    )
    parser.add_argument(
        "--instances",
        nargs="+",
        help="Explicit instance paths; overrides quick/full discovery.",
    )
    parser.add_argument(
        "--formulations",
        nargs="+",
        choices=FORMULATIONS,
        default=list(FORMULATIONS),
        help="Formulations to run; defaults to the paired comparison.",
    )
    parser.add_argument("--input-dir", default="data/instances")
    parser.add_argument("--pattern", default="DataCplex_*.json")
    parser.add_argument("--solver", default="cplex")
    parser.add_argument("--executable", default=None,
                        help="Explicit solver binary path (bypasses PATH lookup).")
    parser.add_argument("--time-limit", type=int, default=300)
    parser.add_argument(
        "--output",
        default="results/tables/formulation_comparison.csv",
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Compare construction time and model size without invoking a solver.",
    )
    parser.add_argument("--tee", action="store_true")
    parser.add_argument(
        "--strict-legacy-state",
        action="store_true",
        help="Use exact-state-compatible C13/C13b rows for the legacy model.",
    )
    args = parser.parse_args()

    instances = select_instances(args)
    missing = [path for path in instances if not path.is_file()]
    if missing:
        parser.error(f"Instance does not exist: {missing[0]}")
    if not instances:
        parser.error("No instances matched the requested selection.")

    jobs = [
        (instance, formulation)
        for instance in instances
        for formulation in args.formulations
    ]
    rows = []
    for instance, formulation in tqdm(jobs, desc="Comparing formulations"):
        rows.append(
            benchmark_one(
                instance,
                formulation,
                args.solver,
                args.time_limit,
                args.build_only,
                args.tee,
                args.executable,
                args.strict_legacy_state,
            )
        )

    output_path = ROOT / args.output
    write_results(rows, output_path)
    errors = sum(row["status"] == "ERROR" for row in rows)
    print(f"Wrote {len(rows)} rows to {output_path}")
    if errors:
        print(f"Completed with {errors} error row(s); inspect the CSV error column.")


if __name__ == "__main__":
    main()
