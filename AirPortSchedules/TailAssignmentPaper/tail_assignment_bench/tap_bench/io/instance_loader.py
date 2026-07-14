from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from tap_bench.domain.models import Aircraft, Flight, SchedulingInstance, StationCapacity


class InstanceLoader:
    @staticmethod
    def load(instance_path: str) -> SchedulingInstance:
        path = Path(instance_path)
        raw = json.loads(path.read_text(encoding="utf-8"))

        flights = [
            Flight(
                id=int(row[0]),
                origin=str(row[1]),
                destination=str(row[2]),
                dep_min=float(row[3]),
                arr_min=float(row[4]),
            )
            for row in raw["Flights"]
        ]

        init_pos = raw.get("AIRCRAFT_INIT_POS", {})
        init_checks = raw.get("Initial_Checks", {})
        c_days = init_checks.get("C_Days", init_checks.get("C", {}))
        d_days = init_checks.get("D_Days", init_checks.get("D", {}))

        aircraft = []
        for aid in raw["Aircrafts"]:
            key = str(aid)
            aircraft.append(
                Aircraft(
                    id=int(aid),
                    initial_airport=str(init_pos.get(key, "")),
                    init_a_min=float(init_checks.get("A", {}).get(key, 0.0)),
                    init_b_min=float(init_checks.get("B", {}).get(key, 0.0)),
                    init_c_days=float(c_days.get(key, 0.0)),
                    init_d_days=float(d_days.get(key, 0.0)),
                )
            )

        metadata: Dict[str, Any] = raw.get("_metadata", {})
        metadata["source_path"] = str(path)

        return SchedulingInstance(
            stem=path.stem,
            flights=flights,
            aircraft=aircraft,
            station_capacity=StationCapacity(
                by_airport={k: int(v) for k, v in raw.get("Station_Capacity", {}).items()}
            ),
            maintenance_thresholds={
                k: float(v) for k, v in raw.get("Maintenance_Thresholds", {}).items()
            },
            maintenance_durations={
                k: float(v) for k, v in raw.get("Maintenance_Durations", {}).items()
            },
            cost_matrix=[[float(x) for x in row] for row in raw["Cost_Matrix"]],
            metadata={k: str(v) for k, v in metadata.items()},
        )
