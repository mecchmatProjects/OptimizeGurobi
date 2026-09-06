"""Run certified fore-benchgen instances through the TAP application."""

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from benchmark_validation import validate_benchmark_certificate
from model import MILP_Sheduler, Scheduler


STANDARD_COLUMNS = [
    "stem", "P", "H", "F", "vars", "constraints", "nodes_max",
    "gap_pct", "cpu_s", "objective",
]


def _metadata(instance, certificate_report):
    generator = instance.get("Generator", {})
    configuration = generator.get("configuration", {})
    return {
        "generator_version": generator.get("version"),
        "generator_seed": configuration.get("root_seed"),
        "topology": configuration.get("route_topology"),
        "threshold_mode": configuration.get("threshold_mode"),
        "cost_model": configuration.get("cost_model"),
        "application_compatible": configuration.get("application_compatible", False),
        "certificate_status": certificate_report["status"],
        "milp_representable": certificate_report["milp_representable"],
    }


def _run_heuristic(path, instance, certificate_report, heuristic):
    started = time.perf_counter()
    scheduler = Scheduler(str(path), allow_ferry=False, heuristic=heuristic)
    routes, unassigned = scheduler.optimize()
    objective = sum(
        timeline["cost"]
        for aircraft in scheduler.aircrafts
        if (timeline := scheduler.get_timeline(aircraft, routes[aircraft])) is not None
    )
    return {
        "stem": path.stem,
        "P": len(instance["Aircrafts"]),
        "H": instance.get("Parameters", {}).get("Target_Horizon_Days"),
        "F": len(instance["Flights"]),
        "vars": None,
        "constraints": None,
        "nodes_max": None,
        "gap_pct": None,
        "cpu_s": round(time.perf_counter() - started, 4),
        "objective": round(objective, 4),
        "mode": f"heuristic:{heuristic}",
        "solver": None,
        "time_limit_s": None,
        "status": "complete" if not unassigned else "partial",
        "assigned": len(instance["Flights"]) - len(unassigned),
        "unassigned": len(unassigned),
        **_metadata(instance, certificate_report),
    }


def _run_milp(path, instance, certificate_report, solver, time_limit):
    if not certificate_report["milp_representable"]:
        return {
            "stem": path.stem, "P": len(instance["Aircrafts"]),
            "H": instance.get("Parameters", {}).get("Target_Horizon_Days"),
            "F": len(instance["Flights"]), "vars": None, "constraints": None,
            "nodes_max": None, "gap_pct": None, "cpu_s": None, "objective": None,
            "mode": "milp", "solver": solver, "time_limit_s": time_limit,
            "status": "certificate-not-representable",
            "assigned": None, "unassigned": None,
            **_metadata(instance, certificate_report),
        }

    optimizer = MILP_Sheduler(str(path))
    optimizer.build_model(allow_ferry=True)
    started = time.perf_counter()
    summary = optimizer.solve(solver_name=solver, time_limit=time_limit)
    return {
        "stem": path.stem,
        "P": len(instance["Aircrafts"]),
        "H": instance.get("Parameters", {}).get("Target_Horizon_Days"),
        "F": len(instance["Flights"]),
        "vars": summary.get("n_vars"),
        "constraints": summary.get("n_cons"),
        "nodes_max": summary.get("nodes"),
        "gap_pct": summary.get("gap"),
        "cpu_s": round(time.perf_counter() - started, 4),
        "objective": summary.get("obj"),
        "mode": "milp",
        "solver": solver,
        "time_limit_s": time_limit,
        "status": summary.get("status"),
        "assigned": len(instance["Flights"]) if summary.get("obj") is not None else None,
        "unassigned": 0 if summary.get("obj") is not None else None,
        **_metadata(instance, certificate_report),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("heuristic", "milp", "both"), default="both")
    parser.add_argument("--heuristic", default="greedy+insertion")
    parser.add_argument("--solver", default="cplex")
    parser.add_argument("--time-limit", type=int, default=60)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "results" / "tables" / "fore_benchgen_runs.csv")
    args = parser.parse_args()

    rows = []
    for path in sorted(args.input_dir.glob("*.json")):
        if path.name.endswith((".solution.json", ".validation.json", ".metrics.json", ".manifest.json")):
            continue
        certificate_path = path.with_name(f"{path.stem}.solution.json")
        if not certificate_path.exists():
            continue
        instance = json.loads(path.read_text(encoding="utf-8"))
        certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
        certificate_report = validate_benchmark_certificate(instance, certificate)
        if args.mode in ("heuristic", "both"):
            rows.append(_run_heuristic(path, instance, certificate_report, args.heuristic))
        if args.mode in ("milp", "both"):
            rows.append(_run_milp(path, instance, certificate_report, args.solver, args.time_limit))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    columns = STANDARD_COLUMNS + [
        "mode", "solver", "time_limit_s", "status", "assigned", "unassigned", "generator_version",
        "generator_seed", "topology", "threshold_mode", "cost_model",
        "application_compatible", "certificate_status", "milp_representable",
    ]
    pd.DataFrame(rows, columns=columns).to_csv(args.output, index=False)
    print(f"Wrote {len(rows)} runs to {args.output}")


if __name__ == "__main__":
    main()