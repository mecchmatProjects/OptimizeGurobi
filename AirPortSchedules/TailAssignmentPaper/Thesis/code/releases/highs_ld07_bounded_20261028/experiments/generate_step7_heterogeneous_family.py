"""Generate a heterogeneous feasible family for Step 7 structural plots."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from generate_feasible_instances import build_feasible_instance
from generate_instances import output_name


SPECS = [
    (4, 7, 0.50, 2, "A"),
    (4, 10, 0.65, 2, "A"),
    (6, 7, 0.50, 3, "A"),
    (6, 10, 0.65, 3, "A"),
    (6, 14, 0.65, 3, "A"),
    (8, 7, 0.50, 3, "A"),
    (8, 10, 0.65, 4, "A"),
    (8, 14, 0.65, 4, "A"),
    (10, 7, 0.50, 3, "A"),
    (10, 10, 0.65, 4, "A"),
    (4, 7, 0.50, 2, "AB"),
    (4, 10, 0.65, 2, "AB"),
    (6, 7, 0.50, 2, "AB"),
    (6, 10, 0.65, 2, "AB"),
    (6, 14, 0.65, 2, "AB"),
    (8, 7, 0.50, 2, "AB"),
    (8, 10, 0.65, 2, "AB"),
    (8, 14, 0.65, 2, "AB"),
    (10, 7, 0.50, 2, "AB"),
    (10, 10, 0.65, 2, "AB"),
]


def main():
    output = ROOT / "data" / "step7_feasible_heterogeneous"
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for index, (p, h, density, flights_per_aircraft, family) in enumerate(SPECS):
        data = build_feasible_instance(
            density=density,
            p=p,
            h=h,
            index=index,
            flights_per_aircraft=flights_per_aircraft,
            maintenance_families=family,
        )
        filename = output_name(density, p, h, index)
        path = output / filename
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        manifest.append({
            "file": filename,
            "p": p,
            "h": h,
            "density": density,
            "flights_per_aircraft": flights_per_aircraft,
            "maintenance_family": family,
            "flights": len(data["Flights"]),
            "status": "feasible",
        })
        print(f"Wrote {filename}: p={p}, h={h}, flights={len(data['Flights'])}, family={family}")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Generated {len(manifest)} validated instances in {output}")


if __name__ == "__main__":
    main()
