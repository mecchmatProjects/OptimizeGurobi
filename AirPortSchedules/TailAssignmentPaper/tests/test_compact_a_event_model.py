"""Tests for the compact A-check-only event prototype."""

import sys
import unittest
from pathlib import Path

from pyomo.environ import Constraint, Var

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.compact_a_event_model import (
    CompactAEventMILPScheduler,
    OrderedAEventMILPScheduler,
    OrderedABEventMILPScheduler,
    OrderedABCDEventMILPScheduler,
)
from src.event_model import EventMILPScheduler


SOURCE = ROOT / "data" / "instances" / "event_vs_legacy_clean_test.json"
ABCD_SOURCE = ROOT / "data" / "feasible_instances" / "abcd" / "DataCplex_density=1_p=10_h=7_test_0.json"


class CompactAEventTests(unittest.TestCase):
    def test_only_a_check_events_and_state_are_instantiated(self):
        scheduler = CompactAEventMILPScheduler(str(SOURCE))
        model = scheduler.build_model()

        self.assertEqual(scheduler.FORMULATION_ID, "compact_a_event")
        self.assertEqual(list(model.C), ["A"])
        self.assertTrue(all(check == "A" for _, _, check in model.Z))
        self.assertTrue(all(check == "A" for _, _, check in model.U))
        self.assertEqual(scheduler.CALENDAR_CHECKS, ())
        self.assertFalse(hasattr(model, "c14_initial_calendar"))
        self.assertFalse(hasattr(model, "c14_calendar_chain"))

    def test_route_domain_matches_full_event_model(self):
        compact = CompactAEventMILPScheduler(str(SOURCE))
        full = EventMILPScheduler(str(SOURCE))
        compact.build_model()
        full.build_model()

        self.assertEqual(set(compact.route_arcs), set(full.route_arcs))
        self.assertEqual(set(compact.source_arcs), set(full.source_arcs))
        self.assertEqual(
            set(compact.model.E), set(full.model.E)
        )

    def test_model_contains_expected_event_state_components(self):
        scheduler = CompactAEventMILPScheduler(str(SOURCE))
        model = scheduler.build_model()

        self.assertTrue(hasattr(model, "x"))
        self.assertTrue(hasattr(model, "y"))
        self.assertTrue(hasattr(model, "z"))
        self.assertTrue(hasattr(model, "u"))
        self.assertTrue(hasattr(model, "c11_hour_bounds"))
        self.assertTrue(hasattr(model, "c12_hour_flow"))
        self.assertTrue(hasattr(model, "c13_initial_hours"))
        self.assertGreater(
            len(list(model.component_data_objects(Var, active=True))), 0
        )
        self.assertGreater(
            len(list(model.component_data_objects(Constraint, active=True))), 0
        )

    def test_ordered_model_removes_successor_arc_variables(self):
        scheduler = OrderedAEventMILPScheduler(str(SOURCE))
        model = scheduler.build_model()

        self.assertEqual(list(model.C), ["A"])
        self.assertEqual(len(model.Z), len(model.X))
        self.assertEqual(len(model.Q), len(model.X))
        self.assertFalse(hasattr(model, "y"))
        self.assertFalse(hasattr(model, "w"))
        self.assertFalse(hasattr(model, "c13_event_day_cap"))
        self.assertTrue(hasattr(model, "e4_coverage"))
        self.assertTrue(hasattr(model, "e5_e6_continuity_turn"))
        self.assertTrue(hasattr(model, "e7_pairwise_overlap"))
        self.assertTrue(hasattr(model, "e8_event_assignment"))
        self.assertTrue(hasattr(model, "e14_maintenance_block"))
        self.assertTrue(hasattr(model, "e15_maintenance_capacity"))

    def test_ordered_model_aggregates_events_without_daily_cap(self):
        scheduler = OrderedAEventMILPScheduler(str(SOURCE))
        model = scheduler.build_model()

        self.assertTrue(hasattr(model, "event_count"))
        self.assertTrue(hasattr(model, "c11_event_count"))
        self.assertEqual(
            len(list(model.c11_event_count)),
            len(model.P) * len(model.D),
        )
        self.assertFalse(hasattr(model, "c13_event_day_cap"))
        self.assertTrue(hasattr(model, "e15_maintenance_capacity"))

    def test_ordered_model_has_one_transition_block_per_flight_aircraft(self):
        scheduler = OrderedAEventMILPScheduler(str(SOURCE))
        model = scheduler.build_model()

        self.assertEqual(
            len(list(model.e9_e13_prefix_state)),
            7 * len(model.Q),
        )

    def test_ordered_model_global_state_indexing_restores_full_q_shape(self):
        scheduler = OrderedAEventMILPScheduler(str(SOURCE))
        model = scheduler.build_model(local_state_indexing=False)

        expected = 0
        for flight in scheduler.flight_ids:
            for aircraft in scheduler.aircraft_ids:
                expected += 7 if scheduler._x_has_arc(flight, aircraft) else 1

        self.assertEqual(
            len(model.Q),
            len(scheduler.flight_ids) * len(scheduler.aircraft_ids),
        )
        self.assertEqual(
            len(list(model.e9_e13_prefix_state)),
            expected,
        )

    def test_ordered_ab_model_has_two_hour_states_and_hierarchy_events(self):
        scheduler = OrderedABEventMILPScheduler(str(SOURCE))
        model = scheduler.build_model()

        self.assertEqual(list(model.C), ["A", "B"])
        self.assertTrue(all(check in {"A", "B"} for _, _, check in model.Z))
        self.assertTrue(all(check in {"A", "B"} for _, _, check in model.Q))
        self.assertEqual(len(model.Q), len(model.X) * 2)
        self.assertTrue(hasattr(model, "event_type_exclusivity"))

    def test_ordered_full_model_adds_calendar_event_domain(self):
        scheduler = OrderedABCDEventMILPScheduler(str(SOURCE))
        model = scheduler.build_model()

        self.assertEqual(list(model.C), ["A", "B", "C", "D"])
        self.assertEqual(len(model.Q), len(model.X) * 2)
        self.assertTrue(all(check in {"A", "B", "C", "D"} for _, _, check in model.Z))
        self.assertTrue(hasattr(model, "c14_calendar"))

    def test_ordered_full_model_builds_feasible_abcd_instance(self):
        scheduler = OrderedABCDEventMILPScheduler(str(ABCD_SOURCE))
        model = scheduler.build_model()

        self.assertEqual(list(model.C), ["A", "B", "C", "D"])
        self.assertGreater(len(model.Z), 0)
        self.assertGreater(len(list(model.c14_calendar)), 0)

    def test_ordered_full_model_builds_with_calendar_pruning_disabled(self):
        scheduler = OrderedABCDEventMILPScheduler(str(ABCD_SOURCE))
        model = scheduler.build_model(calendar_candidate_pruning=False)

        self.assertEqual(list(model.C), ["A", "B", "C", "D"])
        self.assertGreater(len(model.Z), 0)
        self.assertGreater(len(list(model.c14_calendar)), 0)


if __name__ == "__main__":
    unittest.main()
