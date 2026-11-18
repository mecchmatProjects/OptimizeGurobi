import json
from pathlib import Path
import sys

from pyomo.environ import value

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from benchmark_validation import validate_a_hour_exposure, validate_benchmark_certificate
from event_model import EventMILPScheduler


def test_historical_event_retroactive_repair_fails_independent_replay(tmp_path):
    instance = {
        "Aircrafts": [0],
        "AIRCRAFT_INIT_POS": {"0": "A"},
        "Flights": [
            [1, "A", "A", 100, 180],
            [2, "A", "A", 260, 300],
        ],
        "Cost_Matrix": [[1], [1]],
        "Maintenance_Thresholds": {"A": 100, "B": 2000, "C": 30, "D": 60},
        "Maintenance_Durations": {"A": 20, "B": 20, "C": 20, "D": 20},
        "Station_Capacity": {"A": 1},
        "Initial_Checks": {
            "A": {"0": 40},
            "B": {"0": 0},
            "C_Days": {"0": 0},
            "D_Days": {"0": 0},
        },
        "Parameters": {"Min_Turn_Minutes": 30, "Target_Horizon_Days": 1},
    }
    fixture = tmp_path / "historical_event_retroactive_repair.json"
    fixture.write_text(json.dumps(instance))
    scheduler = EventMILPScheduler(str(fixture))
    model = scheduler.build_model()

    certificate = {
        "assignment": {"1": 0, "2": 0},
        "maintenance_events": [
            {
                "tail": 0,
                "check": "A",
                "station": "A",
                "start": 180,
                "end": 200,
                "trigger_flight": 1,
            }
        ],
    }

    assert scheduler.PROFILE_ID == "event_historical_unverified"
    assert scheduler.VERIFICATION_STATUS == "unverified"
    assert (1, 0, "A") in model.Z

    for index in model.x:
        model.x[index].set_value(1)
    for index in model.z:
        model.z[index].set_value(int(index == (1, 0, "A")))
    for index in model.first:
        model.first[index].set_value(int(index == (1, 0)))
    for index in model.last:
        model.last[index].set_value(int(index == (2, 0)))
    for index in model.y:
        model.y[index].set_value(int(index == (1, 2, 0)))
    for index in model.u:
        flight, aircraft, check = index
        if flight == 1 and check == "A":
            model.u[index].set_value(120)
        elif flight == 2 and check == "A":
            model.u[index].set_value(40)
        else:
            model.u[index].set_value(0)

    event_hour_violations = []
    for family in (model.c11_hour_bounds, model.c12_hour_flow, model.c13_initial_hours):
        for index, constraint in family.items():
            body = value(constraint.body)
            lower = value(constraint.lower) if constraint.lower is not None else None
            upper = value(constraint.upper) if constraint.upper is not None else None
            if (lower is not None and body < lower - 1e-7) or (
                upper is not None and body > upper + 1e-7
            ):
                event_hour_violations.append((family.local_name, index))
    assert event_hour_violations
    assert validate_benchmark_certificate(instance, certificate)["status"] == "PASS"
    violations = validate_a_hour_exposure(instance, certificate)
    assert [(item["flight"], item["exposure_minutes"]) for item in violations] == [
        (1, 120)
    ]

    replay = validate_benchmark_certificate(
        instance, certificate, strict_a_hour_limit=True
    )

    assert replay["status"] == "FAIL"
    assert any("A-hour limit" in error and "120.0" in error for error in replay["errors"])
