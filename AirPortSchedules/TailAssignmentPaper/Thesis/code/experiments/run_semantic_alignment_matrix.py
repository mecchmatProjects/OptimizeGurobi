"""Run the MILP-to-timeline semantic validator across exact-feasible cases."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.validate_semantic_alignment import validate

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


def main():
    rows = []
    for label, relative_path, family in INSTANCES:
        result = validate(ROOT / relative_path, solver_name="highs", time_limit=120)
        rows.append({
            "label": label,
            "family": family,
            "solver_status": result.get("solver_status"),
            "alignment_status": result.get("status"),
            "route_valid": result.get("route_valid"),
            "assigned": result.get("assigned"),
            "flights": result.get("flights"),
            "coverage_pct": result.get("coverage_pct"),
            "mismatch_count": len(result.get("mismatches", [])),
        })
        print(rows[-1])

    output = ROOT / "results/tables/exact_feasible/semantic_alignment_matrix.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
