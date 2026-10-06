"""Build a data-driven taxonomy for the 25-instance benchmark set.

The script consumes the existing Phase-1 metadata file and the Phase-2
heuristic/MILP batch outputs to classify each instance as easy, medium, or
hard. The output is written as a CSV so it can be reused later in the paper,
benchmark reports, and sensitivity analysis.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
PHASE1_METADATA = ROOT / "results" / "tables" / "phase1_25_forced" / "phase1_metadata.csv"
PHASE2_MILP = ROOT / "results" / "tables" / "phase2" / "_batch_classical_milp.csv"
PHASE2_HEURISTIC = ROOT / "results" / "tables" / "phase2" / "_batch_heu_all25.csv"
DEFAULT_OUTPUT = ROOT / "results" / "tables" / "phase1_25_forced" / "phase1_instance_taxonomy.csv"
DEFAULT_SUMMARY = ROOT / "results" / "tables" / "phase1_25_forced" / "phase1_instance_taxonomy_summary.csv"


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _stem_for_row(row: Dict[str, str]) -> str:
    cell = row["cell"]
    density = row["density"]
    p = row["p"]
    h = row["h"]
    return f"I{cell}_density={density}_p={p}_h={h}"


def _metric_value(row: Dict[str, str], key: str, default: float = 0.0) -> float:
    value = row.get(key, "")
    if value in {"", None}:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _build_records() -> List[Dict[str, object]]:
    metadata_rows = _read_csv(PHASE1_METADATA)
    milp_rows = {row["stem"]: row for row in _read_csv(PHASE2_MILP)}
    heuristic_rows = {row["stem"]: row for row in _read_csv(PHASE2_HEURISTIC)}

    records: List[Dict[str, object]] = []
    for row in metadata_rows:
        stem = _stem_for_row(row)
        milp_row = milp_rows.get(stem, {})
        heuristic_row = heuristic_rows.get(stem, {})

        flights = int(_metric_value(row, "flights", 0))
        density = _metric_value(row, "density")
        p = int(_metric_value(row, "p"))
        h = int(_metric_value(row, "h"))
        assigned = int(_metric_value(row, "assigned", 0))
        heuristic_unassigned = int(_metric_value(heuristic_row, "unassigned", 0))
        heuristic_assigned = int(_metric_value(heuristic_row, "assigned", assigned))
        heuristic_ratio = heuristic_assigned / flights if flights else 0.0

        milp_status = str(milp_row.get("status", "not_run")).strip() or "not_run"
        milp_runtime = _metric_value(milp_row, "wall_s", _metric_value(milp_row, "cpu_s", 0.0))
        heuristic_runtime = _metric_value(heuristic_row, "wall_s", _metric_value(heuristic_row, "cpu_s", 0.0))

        size_pressure = (flights / max(1, max(int(r["flights"]) for r in metadata_rows)))
        density_pressure = density / 1.0
        fleet_pressure = p / max(1, max(int(_metric_value(r, "p")) for r in metadata_rows))
        horizon_pressure = h / max(1, max(int(_metric_value(r, "h")) for r in metadata_rows))

        hardness_score = 0.55 * size_pressure + 0.2 * density_pressure + 0.15 * fleet_pressure + 0.10 * horizon_pressure
        if milp_status == "infeasible":
            hardness_score += 0.12
        elif milp_status in {"ERROR", "error"}:
            hardness_score += 0.20
        elif milp_status == "optimal":
            hardness_score -= 0.08
        if heuristic_ratio < 0.999:
            hardness_score += 0.08
        if heuristic_unassigned > 0:
            hardness_score += 0.04

        records.append(
            {
                "instance": stem,
                "cell": row["cell"],
                "density": density,
                "p": p,
                "h": h,
                "flights": flights,
                "heuristic_assigned": heuristic_assigned,
                "heuristic_unassigned": heuristic_unassigned,
                "milp_status": milp_status,
                "milp_runtime_s": round(milp_runtime, 2),
                "heuristic_runtime_s": round(heuristic_runtime, 2),
                "hardness_score": round(hardness_score, 3),
            }
        )

    return records


def _assign_categories(records: List[Dict[str, object]]) -> List[Dict[str, object]]:
    ordered = sorted(records, key=lambda r: (float(r["hardness_score"]), int(r["flights"])))
    count = len(ordered)
    cut1 = count // 3
    cut2 = 2 * count // 3

    categories = ["easy", "medium", "hard"]
    for index, record in enumerate(ordered):
        if index < cut1:
            category = categories[0]
        elif index < cut2:
            category = categories[1]
        else:
            category = categories[2]

        if record["milp_status"] == "optimal":
            reason = (
                f"MILP solves to optimality on a compact instance; heuristic also covers "
                f"{record['heuristic_assigned']}/{record['flights']} flights."
            )
        elif record["milp_status"] == "infeasible":
            reason = (
                f"MILP proves infeasibility quickly while the heuristic still constructs a schedule "
                f"for {record['heuristic_assigned']}/{record['flights']} flights."
            )
        else:
            reason = (
                f"MILP remains unresolved within the current run budget; the instance is large/dense "
                f"enough to stress the solver."
            )

        if float(record["hardness_score"]) >= 0.75:
            reason += " This is among the more difficult instances in the set."
        elif float(record["hardness_score"]) <= 0.4:
            reason += " This is one of the easier instances in the set."

        record["category"] = category
        record["reason"] = reason

    return ordered


def write_taxonomy(output_path: Path = DEFAULT_OUTPUT, summary_path: Path = DEFAULT_SUMMARY) -> List[Dict[str, object]]:
    records = _assign_categories(_build_records())
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "instance",
        "cell",
        "density",
        "p",
        "h",
        "flights",
        "heuristic_assigned",
        "heuristic_unassigned",
        "milp_status",
        "milp_runtime_s",
        "heuristic_runtime_s",
        "hardness_score",
        "category",
        "reason",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    summary_rows: List[Dict[str, object]] = []
    for category in ["easy", "medium", "hard"]:
        subset = [r for r in records if r["category"] == category]
        summary_rows.append(
            {
                "category": category,
                "count": len(subset),
                "avg_flights": round(sum(int(r["flights"]) for r in subset) / max(1, len(subset)), 2),
                "avg_hardness": round(sum(float(r["hardness_score"]) for r in subset) / max(1, len(subset)), 3),
                "optimal_count": sum(1 for r in subset if r["milp_status"] == "optimal"),
                "infeasible_count": sum(1 for r in subset if r["milp_status"] == "infeasible"),
                "other_count": sum(1 for r in subset if r["milp_status"] not in {"optimal", "infeasible"}),
            }
        )

    summary_fields = ["category", "count", "avg_flights", "avg_hardness", "optimal_count", "infeasible_count", "other_count"]
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows(summary_rows)

    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Destination CSV for the per-instance taxonomy")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY, help="Destination CSV for the category summary")
    args = parser.parse_args()
    write_taxonomy(args.output, args.summary)
    print(f"Wrote taxonomy to {args.output}")
    print(f"Wrote summary to {args.summary}")


if __name__ == "__main__":
    main()
