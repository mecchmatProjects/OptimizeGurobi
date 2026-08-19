"""Generate measured hard-vs-soft MILP coverage comparison for Chapter 7.7."""
from __future__ import annotations

import csv
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

from pyomo.environ import value
from pyomo.opt import TerminationCondition

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model import MILP_Sheduler


INSTANCES = [
    {
        "label": "feas_A_p4h7_d05",
        "family": "A-only",
        "path": "data/feasible_family_smoke/A/DataCplex_density=0.5_p=4_h=7_test_0.json",
        "use_existing_hrs": True,
    },
    {
        "label": "feas_AB_p4h7_d05",
        "family": "AB",
        "path": "data/feasible_family_smoke_ab/AB/DataCplex_density=0.5_p=4_h=7_test_0.json",
        "use_existing_hrs": True,
    },
    {
        "label": "feas_ABCD_p4h7_d05",
        "family": "ABCD",
        "path": "data/feasible_family_smoke_abcd/ABCD/DataCplex_density=0.5_p=4_h=7_test_0.json",
        "use_existing_hrs": True,
    },
    {
        "label": "feas_A_p4h7_d08",
        "family": "A-only",
        "path": "data/phase1_feasible_subset_A/DataCplex_density=0.8_p=4_h=7_test_0.json",
        "use_existing_hrs": True,
    },
    {
        "label": "feas_A_p6h10_d05",
        "family": "A-only",
        "path": "data/phase1_feasible_subset_A/DataCplex_density=0.5_p=6_h=10_test_0.json",
        "use_existing_hrs": True,
    },
    {
        "label": "ABCD_cap_botl",
        "family": "capacity",
        "path": "data/instances/ABCD_capacity_bottleneck_test.json",
        "use_existing_hrs": True,
    },
    {
        "label": "ABCD_hier",
        "family": "hierarchy",
        "path": "data/instances/ABCD_check_hierarchy_test.json",
        "use_existing_hrs": True,
    },
    {
        "label": "ABCD_near_thr",
        "family": "threshold",
        "path": "data/instances/ABCD_near_threshold_test.json",
        "use_existing_hrs": True,
    },
    {
        "label": "ABCD_no_maint",
        "family": "baseline",
        "path": "data/instances/ABCD_no_maint_test.json",
        "use_existing_hrs": True,
    },
]


def _count_assigned(model):
    return int(round(sum(value(model.x[i, j]) for i, j in model.X)))


def _count_unassigned(model):
    if not hasattr(model, "u"):
        return None
    return int(round(sum(value(model.u[i]) for i in model.F)))


def _secondary_cost(opt: MILP_Sheduler):
    m = opt.model
    assignment_cost = sum(opt._flight_cost(i, j) * value(m.x[i, j]) for i, j in m.X)
    maintenance_events = sum(value(m.y[j, d, c]) for j in m.P for d in m.D for c in m.C)
    return float(assignment_cost + 100.0 * maintenance_events)


def solve_case(case, soft_coverage):
    opt = MILP_Sheduler(str(ROOT / case["path"]))
    opt.build_model(
        use_maintenance=True,
        allow_ferry=True,
        use_existing_hrs=case["use_existing_hrs"],
        use_paper_c13=False,
        soft_coverage=soft_coverage,
        coverage_weight=1_000_000.0,
    )

    with redirect_stdout(io.StringIO()):
        summary = opt.solve(solver_name="highs", time_limit=120, warm_start=False)

    status = str(summary["status"]).lower()
    flights = len(opt.flight_ids)
    assigned = None
    unassigned = None
    coverage_pct = None
    secondary_cost = None

    if status == str(TerminationCondition.optimal).lower():
        assigned = _count_assigned(opt.model)
        coverage_pct = 100.0 * assigned / flights if flights else 0.0
        if soft_coverage:
            unassigned = _count_unassigned(opt.model)
        secondary_cost = _secondary_cost(opt)

    return {
        "status": status,
        "flights": flights,
        "assigned": assigned,
        "unassigned": unassigned,
        "coverage_pct": coverage_pct,
        "objective": summary.get("obj"),
        "secondary_cost": secondary_cost,
    }


def main():
    rows = []
    for case in INSTANCES:
        hard = solve_case(case, soft_coverage=False)
        soft = solve_case(case, soft_coverage=True)

        delta_assigned = None
        delta_coverage_pp = None
        if hard["assigned"] is not None and soft["assigned"] is not None:
            delta_assigned = soft["assigned"] - hard["assigned"]
            delta_coverage_pp = soft["coverage_pct"] - hard["coverage_pct"]

        rows.append(
            {
                "label": case["label"],
                "family": case["family"],
                "flights": hard["flights"],
                "use_existing_hrs": case["use_existing_hrs"],
                "hard_status": hard["status"],
                "hard_assigned": hard["assigned"],
                "hard_coverage_pct": hard["coverage_pct"],
                "hard_obj": hard["objective"],
                "hard_secondary_cost": hard["secondary_cost"],
                "soft_status": soft["status"],
                "soft_assigned": soft["assigned"],
                "soft_unassigned": soft["unassigned"],
                "soft_coverage_pct": soft["coverage_pct"],
                "soft_obj": soft["objective"],
                "soft_secondary_cost": soft["secondary_cost"],
                "delta_assigned": delta_assigned,
                "delta_coverage_pp": delta_coverage_pp,
            }
        )

    both_optimal = [
        row
        for row in rows
        if row["hard_status"] == "optimal" and row["soft_status"] == "optimal"
    ]
    mean_delta_coverage_pp = (
        sum(row["delta_coverage_pp"] for row in both_optimal) / len(both_optimal)
        if both_optimal
        else None
    )
    recovered_from_infeasible = sum(
        1
        for row in rows
        if row["hard_status"] != "optimal" and row["soft_status"] == "optimal"
    )

    rows.append(
        {
            "label": "AGGREGATE",
            "family": "exact_feasible_9",
            "flights": sum(row["flights"] for row in rows),
            "use_existing_hrs": "mixed",
            "hard_status": "summary",
            "hard_assigned": sum(
                row["hard_assigned"] for row in rows if row["hard_assigned"] is not None
            ),
            "hard_coverage_pct": None,
            "hard_obj": None,
            "hard_secondary_cost": None,
            "soft_status": "summary",
            "soft_assigned": sum(
                row["soft_assigned"] for row in rows if row["soft_assigned"] is not None
            ),
            "soft_unassigned": sum(
                row["soft_unassigned"] for row in rows if row["soft_unassigned"] is not None
            ),
            "soft_coverage_pct": None,
            "soft_obj": None,
            "soft_secondary_cost": None,
            "delta_assigned": sum(
                row["delta_assigned"] for row in rows if row["delta_assigned"] is not None
            ),
            "delta_coverage_pp": mean_delta_coverage_pp,
            "both_optimal_count": len(both_optimal),
            "hard_optimal_count": sum(1 for row in rows if row["hard_status"] == "optimal"),
            "soft_optimal_count": sum(1 for row in rows if row["soft_status"] == "optimal"),
            "recovered_from_infeasible": recovered_from_infeasible,
        }
    )

    output = ROOT / "results/tables/exact_feasible/soft_coverage_comparison.csv"
    output.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "label",
        "family",
        "flights",
        "use_existing_hrs",
        "hard_status",
        "hard_assigned",
        "hard_coverage_pct",
        "hard_obj",
        "hard_secondary_cost",
        "soft_status",
        "soft_assigned",
        "soft_unassigned",
        "soft_coverage_pct",
        "soft_obj",
        "soft_secondary_cost",
        "delta_assigned",
        "delta_coverage_pp",
        "both_optimal_count",
        "hard_optimal_count",
        "soft_optimal_count",
        "recovered_from_infeasible",
    ]

    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {output}")
    for row in rows:
        if row["label"] == "AGGREGATE":
            print(
                "AGGREGATE",
                f"hard_optimal={row['hard_optimal_count']}",
                f"soft_optimal={row['soft_optimal_count']}",
                f"mean_delta_pp={row['delta_coverage_pp']}",
                f"recovered={row['recovered_from_infeasible']}",
            )
        else:
            print(
                row["label"],
                f"hard={row['hard_status']} ({row['hard_assigned']}/{row['flights']})",
                f"soft={row['soft_status']} ({row['soft_assigned']}/{row['flights']})",
            )


if __name__ == "__main__":
    main()
