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
