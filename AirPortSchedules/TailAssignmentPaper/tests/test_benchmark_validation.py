import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from benchmark_validation import (
    validate_benchmark_certificate,
    verify_milp_certificate,
)
import fore_benchgen
from model import MILP_Sheduler, Scheduler


def _instance():
    return {
        "Aircrafts": [0],
        "AIRCRAFT_INIT_POS": {"0": "A"},
        "Flights": [[0, "A", "B", 60, 120], [1, "B", "A", 165, 225]],
        "Cost_Matrix": [[1], [1]],
        "Maintenance_Thresholds": {"A": 10000, "B": 20000, "C": 10, "D": 20},
        "Maintenance_Durations": {"A": 30, "B": 30, "C": 30, "D": 30},
        "Station_Capacity": {"A": 1, "B": 1},
        "Initial_Checks": {
            "A": {"0": 0}, "B": {"0": 0},
            "C_Days": {"0": 0}, "D_Days": {"0": 0},
        },
        "Parameters": {"Min_Turn_Minutes": 45},
    }


def test_certificate_respects_configured_turn_and_is_milp_representable():
    certificate = {
        "assignment": {"0": 0, "1": 0},
        "maintenance_events": [],
    }

    report = validate_benchmark_certificate(_instance(), certificate)

    assert report["status"] == "PASS"
    assert report["milp_representable"]


def test_day_start_maintenance_is_flagged_as_not_milp_representable():
    certificate = {
        "assignment": {"0": 0, "1": 0},
        "maintenance_events": [{
            "tail": 0, "check": "A", "station": "A", "start": 0, "end": 30,
        }],
    }

    report = validate_benchmark_certificate(_instance(), certificate)

    assert report["status"] == "PASS"
    assert not report["milp_representable"]
    assert report["milp_representability_errors"]


def test_overnight_maintenance_can_use_a_deferred_trigger():
    certificate = {
        "assignment": {"0": 0, "1": 0},
        "maintenance_events": [{
            "tail": 0, "check": "A", "station": "A", "start": 1440, "end": 1470,
        }],
    }

    report = validate_benchmark_certificate(_instance(), certificate)

    assert report["status"] == "PASS"
    assert report["milp_representable"]


def test_generated_instance_uses_one_based_ids_and_application_cost_indexing(tmp_path):
    instance, certificate, report = fore_benchgen.generate(fore_benchgen.preset("sma1"))
    fixture = tmp_path / "generated.json"
    fixture.write_text(__import__("json").dumps(instance))

    assert report["feasibility_status"] == "PASS"
    assert min(flight[0] for flight in instance["Flights"]) == 1
    assert len(instance["Flights"]) == len(instance["Cost_Matrix"])
    assert Scheduler(str(fixture), allow_ferry=False)
    milp = MILP_Sheduler(str(fixture), enabled_checks=["A"])

    benchmark_report = validate_benchmark_certificate(instance, certificate)
    assert benchmark_report["status"] == "PASS"
    assert benchmark_report["milp_representable"]

    milp_report = verify_milp_certificate(milp, certificate)
    assert milp_report["status"] == "PASS"
    assert milp_report["checked_constraints"] > 0


def test_application_compatible_hierarchy_certificate_passes_full_milp(tmp_path):
    instance, certificate, report = fore_benchgen.generate(fore_benchgen.preset(
        "sma1",
        route_topology="euler",
        threshold_mode="coprime",
        application_compatible=True,
    ))
    fixture = tmp_path / "compatible_hierarchy.json"
    fixture.write_text(__import__("json").dumps(instance))

    assert report["feasibility_status"] == "PASS"
    assert validate_benchmark_certificate(instance, certificate)["milp_representable"]

    milp_report = verify_milp_certificate(MILP_Sheduler(str(fixture)), certificate)
    assert milp_report["status"] == "PASS"
    assert milp_report["checked_constraints"] > 0