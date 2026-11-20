import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.generate_profile_timing import build_option_a_overnight_instance
from benchmark_validation import (
    extract_milp_certificate,
    validate_benchmark_certificate,
    verify_milp_certificate,
)
from model import (
    CorrectedAOnlyLegacyPlacementScheduler,
    CorrectedAOnlyNoOverlapScheduler,
    CorrectedAOnlyScheduler,
    EndpointSplitC13Scheduler,
    KhaledPrintedC13Scheduler,
    OptionAExecutableScheduler,
    OptionBProtectedScheduler,
)


@pytest.mark.parametrize(
    ("scheduler_type", "profile_id", "rows_per_window"),
    [
        (KhaledPrintedC13Scheduler, "khaled_printed", 1),
        (EndpointSplitC13Scheduler, "endpoint_split", 2),
    ],
)
def test_named_legacy_profiles_freeze_shared_assumptions(
    scheduler_type, profile_id, rows_per_window, tmp_path
):
    fixture = _option_ab_fixture(tmp_path)
    scheduler = scheduler_type(str(fixture), a_calendar_dmax=4)
    model = scheduler.build_model()

    assert scheduler.profile_settings() == {
        "formulation_id": scheduler.FORMULATION_ID,
        "profile_id": profile_id,
        "enabled_checks": ["A"],
        "c13_dmax": 4,
        "a_calendar_dmax": 4,
        "max_hour_check_deferral_days": 0,
    }
    assert not hasattr(model, "c13b")
    assert all(index[2] == scheduler.flight_data[index[0]]["day_arrival"] for index in model.Z)
    assert len(model.c12) == len(model.P) * (len(model.D) - 4 + 1)

    if rows_per_window == 1:
        assert str(next(iter(model.c13.values())).expr).count("mega[") == 3
    else:
        assert len(model.c13) == 2 * len(KhaledPrintedC13Scheduler(
            str(fixture), a_calendar_dmax=4
        ).build_model().c13)


def test_corrected_a_only_profile_forces_shared_exact_domains(tmp_path):
    fixture = _option_ab_fixture(tmp_path)
    scheduler = CorrectedAOnlyScheduler(str(fixture))
    model = scheduler.build_model(objective="check_days")

    day_count = len(model.D)
    assert scheduler.PROFILE_ID == "corrected_a_interval"
    assert scheduler.max_hour_check_deferral_days == 0
    assert scheduler.c13_dmax is None
    assert scheduler.a_calendar_dmax is None
    assert len(model.c13) == len(model.P) * day_count * (day_count - 1) // 2
    assert len(model.c13b) == len(model.P) * day_count
    assert all(index[2] == scheduler.flight_data[index[0]]["day_arrival"] for index in model.Z)
    assert not any("c12" == component.local_name for component in model.component_objects())


def test_corrected_a_only_one_factor_ablations(tmp_path):
    fixture = _option_ab_fixture(tmp_path)
    reference = CorrectedAOnlyScheduler(str(fixture), a_calendar_dmax=4)
    reference_model = reference.build_model(objective="check_days")
    no_overlap = CorrectedAOnlyNoOverlapScheduler(str(fixture), a_calendar_dmax=4)
    no_overlap_model = no_overlap.build_model(objective="check_days")
    legacy_placement = CorrectedAOnlyLegacyPlacementScheduler(
        str(fixture), a_calendar_dmax=4
    )
    legacy_model = legacy_placement.build_model(objective="check_days")

    assert len(no_overlap_model.c13) == len(reference_model.c13)
    assert len(no_overlap_model.c13b) == len(reference_model.c13b)
    assert hasattr(reference_model, "c_overlap")
    assert not hasattr(no_overlap_model, "c_overlap")
    assert legacy_placement.PAPER_ARRIVAL_DAY_PLACEMENT is False
    assert len(legacy_model.c13) == len(reference_model.c13)
    assert len(legacy_model.c13b) == len(reference_model.c13b)


def test_corrected_a_only_profile_allows_explicit_calendar_policy(tmp_path):
    fixture = _option_ab_fixture(tmp_path)
    scheduler = CorrectedAOnlyScheduler(str(fixture), a_calendar_dmax=4)
    model = scheduler.build_model(objective="check_days")

    assert scheduler.a_calendar_dmax == 4
    assert len(model.c12) == len(model.P) * (len(model.D) - 4 + 1)


def _option_ab_fixture(tmp_path):
    instance = {
        "Aircrafts": [0],
        "AIRCRAFT_INIT_POS": {"0": "M"},
        "Flights": [
            [1, "M", "M", 100, 160],
            [2, "M", "M", 1540, 1600],
            [3, "M", "M", 2980, 3040],
        ],
        "Cost_Matrix": [[100], [100], [100]],
        "Maintenance_Thresholds": {"A": 600, "B": 999999, "C": 9999, "D": 9999},
        "Maintenance_Durations": {"A": 30, "B": 30, "C": 30, "D": 30},
        "Station_Capacity": {"M": 1},
        "Initial_Checks": {
            "A": {"0": 0}, "B": {"0": 0},
            "C_Days": {"0": 0}, "D_Days": {"0": 0},
        },
        "Parameters": {"Min_Turn_Minutes": 30, "Target_Horizon_Days": 3},
        "Maintenance_Buffers": {
            "A": {"0": {"preparation": 0, "release": 5}}
        },
        "Maintenance_Service_Windows": {
            "M": {
                "1": [1320, 1410],
                "2": [2760, 2850],
                "3": [4200, 4290],
            }
        },
        "Protected_Maintenance_Periods": {
            "1": [1320, 1360],
            "2": [2760, 2800],
            "3": [4200, 4240],
        },
        "Terminal_Release_Minutes": {"0": 4320},
    }
    fixture = tmp_path / "option_ab.json"
    fixture.write_text(json.dumps(instance))
    return fixture


def test_option_a_and_certified_option_b_have_same_projection_domain(tmp_path):
    fixture = _option_ab_fixture(tmp_path)
    option_a = OptionAExecutableScheduler(str(fixture))
    option_b = OptionBProtectedScheduler(str(fixture))

    model_a = option_a.build_model(objective="check_days")
    model_b = option_b.build_model(objective="check_days")

    assert option_b.option_b_certification["status"] == "SUPPORTED"
    assert len(model_a.X) == len(model_b.X)
    assert len(model_a.Z) == len(model_b.Z)
    assert len(model_a.c13) == len(model_b.c13)
    assert len(model_a.c13b) == len(model_b.c13b)
    assert hasattr(model_a, "c_option_a_timing")
    assert hasattr(model_a, "c_option_a_capacity")
    assert not hasattr(model_b, "c_option_a_timing")
    assert not hasattr(model_b, "c_option_a_capacity")
    assert len(list(model_a.component_data_objects())) >= len(
        list(model_b.component_data_objects())
    )
    assert option_a.profile_settings()["profile_id"] == "option_a"
    assert option_b.profile_settings()["profile_id"] == "option_b"


def test_option_a_exact_timing_admits_cross_midnight_certificate(tmp_path):
    instance, certificate = build_option_a_overnight_instance(4, 4, 0)
    fixture = tmp_path / "option_a_overnight.json"
    fixture.write_text(json.dumps(instance))
    scheduler = OptionAExecutableScheduler(str(fixture), a_calendar_dmax=4)

    report = verify_milp_certificate(scheduler, certificate, objective="early_check")

    assert report["status"] == "PASS"
    assert not hasattr(scheduler.model, "c8")

    summary = scheduler.solve(solver_name="highs", time_limit=60)
    solved_certificate = extract_milp_certificate(scheduler)
    replay = validate_benchmark_certificate(
        instance,
        solved_certificate,
        capacity_semantics="simultaneous",
        strict_a_hour_limit=True,
    )
    assert summary["status"] == "optimal"
    assert replay["status"] == "PASS"


def test_option_b_uncertified_input_is_unsupported_not_infeasible(tmp_path):
    fixture = _option_ab_fixture(tmp_path)
    instance = json.loads(fixture.read_text())
    del instance["Protected_Maintenance_Periods"]
    fixture.write_text(json.dumps(instance))

    scheduler = OptionBProtectedScheduler(str(fixture))
    model = scheduler.build_model()
    summary = scheduler.solve()

    assert model is None
    assert scheduler.option_b_certification["status"] == "UNSUPPORTED"
    assert summary["status"] == "unsupported"
    assert summary["errors"]


def test_named_profiles_require_explicit_calendar_span(tmp_path):
    fixture = _option_ab_fixture(tmp_path)
    with pytest.raises(TypeError):
        KhaledPrintedC13Scheduler(str(fixture))
    with pytest.raises(ValueError, match="at least 2"):
        EndpointSplitC13Scheduler(str(fixture), a_calendar_dmax=1)
