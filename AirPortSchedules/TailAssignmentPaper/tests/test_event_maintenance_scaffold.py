"""Phase-2 regression tests for the event-maintenance scaffold."""

import sys
import unittest
from pathlib import Path
from pyomo.core.expr.visitor import identify_variables
from pyomo.environ import value as pyo_value

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model import MILP_Sheduler

SOURCE = ROOT / "data" / "instances" / "ABCD_capacity_bottleneck_test.json"


class EventMaintenanceScaffoldTests(unittest.TestCase):
    def test_scaffold_adds_event_sets_and_constraints(self):
        scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A", "C"])
        model = scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_event_maintenance=True,
        )

        self.assertTrue(hasattr(model, "E"))
        self.assertTrue(hasattr(model, "YE"))
        self.assertTrue(hasattr(model, "Y0E"))
        self.assertTrue(hasattr(model, "YWE"))
        self.assertTrue(hasattr(model, "ZE"))
        self.assertTrue(hasattr(model, "z_event"))

        self.assertTrue(hasattr(model, "c5_event"))
        self.assertTrue(hasattr(model, "c6_event"))
        self.assertTrue(hasattr(model, "c2e_pred_unique"))
        self.assertTrue(hasattr(model, "c3e_succ_unique"))
        self.assertTrue(hasattr(model, "c4e_route_count"))
        self.assertTrue(hasattr(model, "c8e_block"))
        self.assertTrue(hasattr(model, "c9e_capacity"))
        self.assertTrue(hasattr(model, "c_event_bridge"))

        self.assertGreater(len(model.ZE), 0)
        self.assertGreater(len(list(model.c5_event)), 0)
        self.assertGreater(len(list(model.c6_event)), 0)
        self.assertGreater(len(list(model.c2e_pred_unique)), 0)
        self.assertGreater(len(list(model.c3e_succ_unique)), 0)
        self.assertGreater(len(list(model.c9e_capacity)), 0)
        self.assertGreater(len(list(model.c_event_bridge)), 0)

    def test_c8e_block_row_count_matches_incompatible_arc_count(self):
        scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
        model = scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_event_maintenance=True,
        )

        expected = 0
        for i, ell, j in model.YE:
            dep_ell = scheduler.flight_data[ell]["departureTime"]
            arr_i = scheduler.flight_data[i]["arrivalTime"]
            for c in scheduler.CHECK_LIST:
                if (i, j, c) not in model.ZE:
                    continue
                ready_after_maint = arr_i + scheduler.check_dur[c] + scheduler.MIN_TURN
                if dep_ell < ready_after_maint:
                    expected += 1

        self.assertEqual(len(list(model.c8e_block)), expected)

    def test_c8e_block_semantics_forbid_y_and_z_simultaneously(self):
        scheduler = MILP_Sheduler(str(SOURCE))
        model = scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_event_maintenance=True,
        )

        rows = list(model.c8e_block.values())
        self.assertTrue(rows)
        row = rows[0]

        vars_in_row = list(identify_variables(row.body))
        self.assertGreaterEqual(len(vars_in_row), 2)

        previous = [v.value for v in vars_in_row]
        try:
            for v in vars_in_row:
                v.set_value(1)
            body_val = pyo_value(row.body)
            upper_val = pyo_value(row.upper)
            self.assertGreater(body_val, upper_val)
        finally:
            for v, old in zip(vars_in_row, previous):
                v.set_value(old)

    def test_event_mode_keeps_legacy_objective_and_exposes_event_cost_expr(self):
        scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
        model = scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_event_maintenance=True,
        )

        obj_text = str(model.obj.expr)
        self.assertIn("maintenance_start", obj_text)
        self.assertTrue(hasattr(model, "event_maintenance_cost_expr"))
        self.assertIn("z_event", str(model.event_maintenance_cost_expr))

    def test_strict_event_bridge_is_opt_in(self):
        scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
        loose = scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_event_maintenance=True,
            use_event_bridge_strict=False,
        )

        strict_scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
        strict = strict_scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_event_maintenance=True,
            use_event_bridge_strict=True,
        )

        self.assertFalse(hasattr(loose, "c_event_bridge_strict"))
        self.assertTrue(hasattr(strict, "c_event_bridge_strict"))
        self.assertGreater(len(list(strict.c_event_bridge_strict)), 0)

    def test_event_only_block_capacity_skips_legacy_c8_c10(self):
        scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
        legacy = scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_event_maintenance=False,
        )

        trial_scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
        trial = trial_scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_event_maintenance=True,
            use_event_bridge_strict=True,
            use_event_only_block_capacity=True,
        )

        self.assertTrue(hasattr(legacy, "c8"))
        self.assertTrue(hasattr(legacy, "c10"))
        self.assertFalse(hasattr(trial, "c8"))
        self.assertFalse(hasattr(trial, "c10"))
        self.assertTrue(hasattr(trial, "c8e_block"))
        self.assertTrue(hasattr(trial, "c9e_capacity"))


if __name__ == "__main__":
    unittest.main()
