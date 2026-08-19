"""Matched seven-heuristic and MILP tournament on exact-feasible instances."""
import csv
import json
import sys
import time
from pathlib import Path

from pyomo.environ import value

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model import MILP_Sheduler, Scheduler

INSTANCES = [
    ("feas_A_p4h7_d05", "data/feasible_family_smoke/A/DataCplex_density=0.5_p=4_h=7_test_0.json", "A-only"),
    ("feas_AB_p4h7_d05", "data/feasible_family_smoke_ab/AB/DataCplex_density=0.5_p=4_h=7_test_0.json", "AB"),
    ("feas_ABCD_p4h7_d05", "data/feasible_family_smoke_abcd/ABCD/DataCplex_density=0.5_p=4_h=7_test_0.json", "ABCD"),
    ("feas_A_p4h7_d08", "data/phase1_feasible_subset_A/DataCplex_density=0.8_p=4_h=7_test_0.json", "A-only"),
    ("feas_A_p6h10_d05", "data/phase1_feasible_subset_A/DataCplex_density=0.5_p=6_h=10_test_0.json", "A-only"),
    ("ABCD_cap_botl", "data/instances/ABCD_capacity_bottleneck_test.json", "capacity"),
    ("ABCD_hier", "data/instances/ABCD_check_hierarchy_test.json", "hierarchy"),
    ("ABCD_near_thr", "data/instances/ABCD_near_threshold_test.json", "threshold"),
    ("ABCD_no_maint", "data/instances/ABCD_no_maint_test.json", "baseline"),
]

HEURISTICS = ["greedy", "insertion", "greedy+insertion", "repair", "local_search", "dijkstra", "aco"]


def heuristic_row(label, path, family, method):
    started = time.perf_counter()
    scheduler = Scheduler(str(path), heuristic=method)
    routes, unassigned = scheduler.optimize()
    wall = time.perf_counter() - started
    assignment_cost = 0.0
    ferry_cost = 0.0
    maintenance_events = 0
    valid = True
    for aid, flights in routes.items():
        timeline = scheduler.get_timeline(aid, flights)
        if timeline is None:
            valid = False
            continue
        for event in timeline["events"]:
            if event["kind"] == "FLIGHT":
                assignment_cost += float(event["cost"])
            elif event["kind"] == "FERRY":
                ferry_cost += float(event.get("cost", scheduler.ferry_cost))
            elif event["kind"] == "MAINT":
                maintenance_events += 1
    maintenance_cost = 100.0 * maintenance_events
    total = assignment_cost + ferry_cost + maintenance_cost
    flights = len(scheduler.flights)
    assigned = flights - len(unassigned)
    return {
        "label": label, "family": family, "method": method,
        "status": "complete" if valid and assigned == flights else "partial" if valid else "invalid",
        "flights": flights, "assigned": assigned, "coverage_pct": 100.0 * assigned / flights,
        "assignment_cost": assignment_cost, "maintenance_cost": maintenance_cost,
        "ferry_cost": ferry_cost, "maintenance_events": maintenance_events,
        "total_cost": total, "wall_s": wall, "solver": "python",
    }


def milp_row(label, path, family, integrated):
    started = time.perf_counter()
    optimizer = MILP_Sheduler(str(path))
    optimizer.build_model(use_maintenance=integrated, allow_ferry=True)
    summary = optimizer.solve(solver_name="highs", time_limit=120, warm_start=False)
    wall = time.perf_counter() - started
    status = str(summary["status"]).lower()
    row = {
        "label": label, "family": family,
        "method": "integrated_milp" if integrated else "classical_milp",
        "status": status, "flights": len(optimizer.flight_ids), "assigned": None,
        "coverage_pct": None, "assignment_cost": None, "maintenance_cost": None,
        "ferry_cost": 0.0, "maintenance_events": None, "total_cost": summary.get("obj"),
        "wall_s": wall, "solver": "highs",
        "num_vars": summary.get("n_vars"), "num_constraints": summary.get("n_cons"),
        "mip_gap": summary.get("gap"),
    }
    if status == "optimal":
        assignment_cost = sum(
            optimizer._flight_cost(i, j) * value(optimizer.model.x[i, j])
            for i, j in optimizer.model.X
        )
        maintenance_events = sum(
            value(optimizer.model.y[j, d, c])
            for j in optimizer.model.P for d in optimizer.model.D for c in optimizer.model.C
        ) if integrated else 0.0
        row["assignment_cost"] = float(assignment_cost)
        row["maintenance_events"] = int(round(maintenance_events))
        row["maintenance_cost"] = 100.0 * maintenance_events
    return row


def main():
    rows = []
    for label, relative_path, family in INSTANCES:
        path = ROOT / relative_path
        for method in HEURISTICS:
            row = heuristic_row(label, path, family, method)
            rows.append(row)
            print(label, method, row["status"], f"coverage={row['coverage_pct']:.1f}%", f"cost={row['total_cost']:.0f}")
        for integrated in (False, True):
            row = milp_row(label, path, family, integrated)
            rows.append(row)
            print(label, row["method"], row["status"], f"obj={row['total_cost']}")

    output = ROOT / "results/tables/exact_feasible/full_seven_method_tournament.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
