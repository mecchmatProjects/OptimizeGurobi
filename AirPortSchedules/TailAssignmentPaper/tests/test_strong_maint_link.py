import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from model import MILP_Sheduler


SOURCE = ROOT / "data" / "feasible_family_smoke" / "A" / "DataCplex_density=0.5_p=4_h=7_test_0.json"


def test_strong_maintenance_link_is_opt_in_and_handles_multi_day_windows(tmp_path):
    """The new link adds deferred-day rows without changing baseline defaults."""
    data = json.loads(SOURCE.read_text())
    data["Maintenance_Durations"]["C"] = 2 * 24 * 60
    fixture = tmp_path / "multi_day_c.json"
    fixture.write_text(json.dumps(data))

    baseline = MILP_Sheduler(str(fixture), enabled_checks=["C"])
    baseline_model = baseline.build_model(
        allow_ferry=False,
        use_overlap=False,
        use_strong_maint_link=False,
    )

    strengthened = MILP_Sheduler(str(fixture), enabled_checks=["C"])
    strengthened_model = strengthened.build_model(
        allow_ferry=False,
        use_overlap=False,
        use_strong_maint_link=True,
    )

    baseline_expr = str(next(iter(baseline_model.c9.values())).expr)
    strengthened_expr = str(next(iter(strengthened_model.c9.values())).expr)
    assert baseline_expr.count("z[") == 1
    assert strengthened_expr.count("z[") == 2
    assert len(list(strengthened_model.Z)) == len(list(baseline_model.Z))


def test_baseline_c9_remains_default(tmp_path):
    data = json.loads(SOURCE.read_text())
    data["Maintenance_Durations"]["C"] = 2 * 24 * 60
    fixture = tmp_path / "multi_day_c.json"
    fixture.write_text(json.dumps(data))

    baseline = MILP_Sheduler(str(fixture), enabled_checks=["C"])
    default_model = baseline.build_model(
        allow_ferry=False,
        use_overlap=False,
        use_day_spacing=False,
    )

    explicit_baseline = MILP_Sheduler(str(fixture), enabled_checks=["C"])
    explicit_model = explicit_baseline.build_model(
        allow_ferry=False,
        use_overlap=False,
        use_day_spacing=False,
        use_strong_maint_link=False,
    )

    assert len(list(default_model.c9)) == len(list(explicit_model.c9))


def test_sparse_maintenance_domain_removes_infeasible_aircraft_arcs(tmp_path):
    data = json.loads(SOURCE.read_text())
    data["Cost_Matrix"][0][0] = 10000
    fixture = tmp_path / "sparse_domain.json"
    fixture.write_text(json.dumps(data))

    baseline = MILP_Sheduler(str(fixture))
    baseline_model = baseline.build_model(
        allow_ferry=False,
        use_overlap=False,
        use_sparse_maint_aircraft_domain=False,
    )
    sparse = MILP_Sheduler(str(fixture))
    sparse_model = sparse.build_model(
        allow_ferry=False,
        use_overlap=False,
        use_sparse_maint_aircraft_domain=True,
    )

    assert len(list(sparse_model.Z)) < len(list(baseline_model.Z))
    assert all(
        (flight, aircraft) in sparse_model.X
        for flight, aircraft, _, _ in sparse_model.Z
    )


def test_empty_capacity_rows_are_skipped(tmp_path):
    data = json.loads(SOURCE.read_text())
    data["Station_Capacity"] = {airport: 0 for airport in data["Station_Capacity"]}
    fixture = tmp_path / "empty_capacity.json"
    fixture.write_text(json.dumps(data))

    scheduler = MILP_Sheduler(str(fixture))
    model = scheduler.build_model(allow_ferry=False, use_overlap=False)

    assert len(list(model.c10)) == 0


def test_tight_c13_m_is_opt_in_and_interval_bounded():
    scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])

    baseline = scheduler.build_model(
        allow_ferry=False,
        use_overlap=False,
        use_tight_c13_m=False,
    )
    tight_scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
    tight = tight_scheduler.build_model(
        allow_ferry=False,
        use_overlap=False,
        use_tight_c13_m=True,
    )

    assert len(list(baseline.c13)) == len(list(tight.c13))
    assert tight_scheduler._c13_big_m("A", 1, 1, 3) >= 0
    assert "9999999" in str(next(iter(baseline.c13.values())).expr)
    assert "9999999" not in str(next(iter(tight.c13.values())).expr)


def test_reachability_removes_deferred_trigger_after_station_departure(tmp_path):
    data = json.loads(SOURCE.read_text())
    data["Maintenance_Durations"]["C"] = 2 * 24 * 60
    data["Flights"].append([15, "M", "H", 500, 560])
    data["Cost_Matrix"].append([10, 10, 10, 10])
    fixture = tmp_path / "reachability.json"
    fixture.write_text(json.dumps(data))

    baseline = MILP_Sheduler(str(fixture), enabled_checks=["C"])
    baseline_model = baseline.build_model(
        allow_ferry=False,
        use_overlap=False,
        use_day_spacing=False,
        use_capacity=False,
        use_maint_reachability=False,
    )
    filtered = MILP_Sheduler(str(fixture), enabled_checks=["C"])
    filtered_model = filtered.build_model(
        allow_ferry=False,
        use_overlap=False,
        use_day_spacing=False,
        use_capacity=False,
        use_maint_reachability=True,
    )

    assert len(list(filtered_model.Z)) < len(list(baseline_model.Z))


def test_strong_maintenance_conflicts_disaggregate_blocked_flights(tmp_path):
    data = json.loads(SOURCE.read_text())
    data["Maintenance_Durations"]["C"] = 2 * 24 * 60
    data["Flights"].extend([
        [15, "M", "H", 150, 210],
        [16, "M", "H", 240, 300],
    ])
    data["Cost_Matrix"].extend([[10, 10, 10, 10], [10, 10, 10, 10]])
    fixture = tmp_path / "strong_conflicts.json"
    fixture.write_text(json.dumps(data))

    baseline = MILP_Sheduler(str(fixture), enabled_checks=["C"])
    baseline_model = baseline.build_model(
        allow_ferry=False,
        use_overlap=False,
        use_day_spacing=False,
        use_capacity=False,
        use_strong_maint_conflicts=False,
    )
    strong = MILP_Sheduler(str(fixture), enabled_checks=["C"])
    strong_model = strong.build_model(
        allow_ferry=False,
        use_overlap=False,
        use_day_spacing=False,
        use_capacity=False,
        use_strong_maint_conflicts=True,
    )

    assert len(list(strong_model.c8)) > len(list(baseline_model.c8))
