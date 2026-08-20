"""Create a compact benchmark summary for the 25-instance study.

The script aggregates the current Phase-1/Phase-2 outputs into a single
CSV that can be used directly in the paper and for further sensitivity work.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = ROOT / "results" / "tables" / "phase1_25_forced" / "phase1_instance_taxonomy.csv"
OUTPUT = ROOT / "results" / "tables" / "phase1_25_forced" / "phase1_benchmark_summary.csv"


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_summary(output_path: Path = OUTPUT) -> Path:
    rows = _read_csv(TAXONOMY)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    for row in rows:
        summary_rows.append(
            {
                "instance": row["instance"],
                "category": row["category"],
                "density": row["density"],
                "p": row["p"],
                "h": row["h"],
                "flights": row["flights"],
                "heuristic_assigned": row["heuristic_assigned"],
                "heuristic_unassigned": row["heuristic_unassigned"],
                "milp_status": row["milp_status"],
                "milp_runtime_s": row["milp_runtime_s"],
                "heuristic_runtime_s": row["heuristic_runtime_s"],
                "hardness_score": row["hardness_score"],
            }
        )

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Destination CSV for the benchmark summary")
    args = parser.parse_args()
    path = write_summary(args.output)
    print(f"Wrote benchmark summary to {path}")


if __name__ == "__main__":
    main()
