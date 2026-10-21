"""Tests for the compact A-check-only event prototype."""

import sys
import unittest
import contextlib
import io
import itertools
import json
import os
import tempfile
from pathlib import Path

from pyomo.core.expr.visitor import identify_variables
from pyomo.environ import Constraint, NonNegativeIntegers, Var, value

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.compact_a_event_model import (
    CompactAEventMILPScheduler,
    FlexiblePaperEventBasedMILPScheduler,
    OptimizedPaperEventBasedMILPScheduler,
    OrderedAEventMILPScheduler,
    OrderedABEventMILPScheduler,
    OrderedABCDEventMILPScheduler,
    UniformFlexibleDayMILPScheduler,
    UniformFlexibleEventMILPScheduler,
    UniformNightDayMILPScheduler,
    UniformNightEventMILPScheduler,
)
from src.event_model import EventMILPScheduler
from src.validate_maintenance import validate_solved_model


SOURCE = ROOT / "data" / "instances" / "event_vs_legacy_clean_test.json"
ABCD_SOURCE = ROOT / "data" / "feasible_instances" / "abcd" / "DataCplex_density=1_p=10_h=7_test_0.json"


class CompactAEventTests(unittest.TestCase):
    def test_uniform_cross_day_solution_matches_enumerated_start_times(self):
        executable = os.environ.get(
            "TAP_PYOMO_SOLVER_EXECUTABLE",
            "F:/Progs/IBM.ILOG.CPLEX.for.AMPL.v12.6-EAT/CPLEXamp.exe",
        )
        if not Path(executable).is_file():
            self.skipTest("Set TAP_PYOMO_SOLVER_EXECUTABLE to the CPLEX AMPL executable.")
        flights = [[1, "M", "M", 10, 20], [2, "M", "M", 70, 80], [3, "M", "M", 1510, 1520]]
        data = {
            "Aircrafts": [0], "AIRCRAFT_INIT_POS": {"0": "M"},
            "Flights": flights, "Cost_Matrix": [[100], [100], [100]],
            "Maintenance_Thresholds": {"A": 15, "B": 99999, "C": 9999, "D": 9999},
            "Maintenance_Durations": {"A": 10, "B": 10, "C": 10, "D": 10},
            "Maintenance_Families": ["A"], "Station_Capacity": {"M": 1},
        }
        feasible_starts = []
        for first, second in itertools.product(range(20, 1461, 10), range(80, 1521, 10)):
            if first + 10 + 30 > 70 or second + 10 + 30 > 1510:
                continue
            if first // 1440 == second // 1440:
                continue
            feasible_starts.append((first, second))
        self.assertTrue(feasible_starts)
        self.assertTrue(all(second >= 1440 for _, second in feasible_starts))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cross_day.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            for builder in (UniformFlexibleDayMILPScheduler, UniformFlexibleEventMILPScheduler):
                with self.subTest(builder=builder.__name__):
                    scheduler = builder(str(path))
                    scheduler.MAINTENANCE_TIME_GRID = 10
                    scheduler.build_model()
                    with contextlib.redirect_stdout(io.StringIO()):
                        result = scheduler.solve(
                            solver_name="cplexamp", executable=executable,
                            time_limit=10, solver_options={"threads": 1},
                        )
                    self.assertEqual(result["status"], "optimal")
                    self.assertEqual(result["obj"], 300 + 2 * 100)
                    self.assertEqual(validate_solved_model(scheduler), [])
                    for index in scheduler.model.Z_START:
                        scheduler._start_variable(scheduler.model, index).set_value(0)
                    for key in scheduler.model.Z:
                        if key[0] in (1, 2):
                            scheduler.model.s_ticks[key].set_value(1)
                            if not scheduler.DAY_INDEXED_Z:
                                scheduler.model.z[key].set_value(1)
                            scheduler._start_variable(
                                scheduler.model, (key[0], key[1], 1, key[2])
                            ).set_value(1)
                    violations = validate_solved_model(scheduler)
                    self.assertIn("multiple_checks_per_start_day", {item.get("type") for item in violations})
            for builder in (UniformNightDayMILPScheduler, UniformNightEventMILPScheduler):
                scheduler = builder(str(path))
                scheduler.MAINTENANCE_TIME_GRID = 10
                scheduler.build_model()
                with contextlib.redirect_stdout(io.StringIO()):
                    result = scheduler.solve(
                        solver_name="cplexamp", executable=executable,
                        time_limit=10, solver_options={"threads": 1},
                    )
                self.assertEqual(result["status"], "infeasible")

    def test_uniform_models_group_checks_by_actual_start_day(self):
        for builder in (UniformFlexibleDayMILPScheduler, UniformFlexibleEventMILPScheduler):
            with self.subTest(builder=builder.__name__):
                scheduler = builder(str(SOURCE))
                scheduler.flight_data[1]["arrivalTime"] = 1430
                model = scheduler.build_model()
                event = next(key for key in model.Z if key[0] == 1)
                self.assertEqual(
                    {key[2] for key in scheduler.start_keys_by_event[event]}, {1, 2}
                )
                for index in model.Z_START:
                    scheduler._start_variable(model, index).set_value(0)
                if not scheduler.DAY_INDEXED_Z:
                    for variable in model.z.values():
                        variable.set_value(0)
                    model.z[event].set_value(1)
                scheduler._start_variable(model, (event[0], event[1], 2, event[2])).set_value(1)
                model.s_ticks[event].set_value(1440 - 1430 + scheduler.check_dur["A"])
                for row in model.c_start_day_time.values():
                    if any(
                        variable is model.s_ticks[event]
                        for variable in identify_variables(row.body)
                    ):
                        self.assertLessEqual(value(row.body), value(row.upper) + 1e-8) if row.has_ub() else self.assertGreaterEqual(value(row.body), value(row.lower) - 1e-8)
                self.assertTrue(hasattr(model, "c_one_check_per_start_day"))
                self.assertEqual(model.z.index_set().dimen, 4 if scheduler.DAY_INDEXED_Z else 3)
                self.assertEqual(value(model.event_z[event]), 1)

    def test_uniform_night_builders_only_restrict_flexible_starts(self):
        for flexible_builder, night_builder in (
            (UniformFlexibleDayMILPScheduler, UniformNightDayMILPScheduler),
            (UniformFlexibleEventMILPScheduler, UniformNightEventMILPScheduler),
        ):
            flexible = flexible_builder(str(SOURCE)).build_model()
            night = night_builder(str(SOURCE)).build_model()
            for family in (
                "e9_e13_prefix_state", "e14_flex_maintenance_block",
                "e20_flex_station_capacity", "c_one_check_per_start_day",
            ):
                self.assertEqual(len(getattr(flexible, family)), len(getattr(night, family)))
            self.assertEqual(len(flexible.c_fixed_night_start), 0)
            self.assertEqual(len(night.c_fixed_night_start), len(night.Z))

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

    def test_immediate_capacity_uses_arrival_started_event_windows(self):
        scheduler = OrderedAEventMILPScheduler(str(SOURCE))
        scheduler.station_cap["M"] = 1
        scheduler.flight_data[1]["departureTime"] = 0.0
        scheduler.flight_data[1]["arrivalTime"] = 100.0
        scheduler.flight_data[2]["departureTime"] = 50.0
        scheduler.flight_data[2]["arrivalTime"] = 110.0

        model = scheduler.build_model()
        actual_signatures = [
            tuple(sorted(
                variable.index()
                for variable in identify_variables(row.body)
                if variable.parent_component() is model.z
            ))
            for row in model.e15_maintenance_capacity.values()
        ]
        expected_signatures = []
        for breakpoint_flight in scheduler.maint_flight_ids:
            breakpoint = scheduler.flight_data[breakpoint_flight]["arrivalTime"]
            signature = tuple(sorted(
                event
                for event in model.Z
                if scheduler.flight_data[event[0]]["destination"] == "M"
                and scheduler.flight_data[event[0]]["arrivalTime"] <= breakpoint
                < scheduler.flight_data[event[0]]["arrivalTime"]
                + scheduler.check_dur[event[2]]
            ))
            if signature:
                expected_signatures.append(signature)

        self.assertEqual(actual_signatures, expected_signatures)

    def test_immediate_blocking_includes_departure_at_trigger_arrival(self):
        scheduler = OrderedAEventMILPScheduler(str(SOURCE))
        scheduler.flight_data[2]["departureTime"] = scheduler.flight_data[1]["arrivalTime"]

        model = scheduler.build_model()
        boundary_pairs = {
            (
                variable.index(),
                event.index(),
            )
            for row in model.e14_maintenance_block.values()
            for variable in identify_variables(row.body)
            if variable.parent_component() is model.x
            for event in identify_variables(row.body)
            if event.parent_component() is model.z
        }

        self.assertTrue(
            any(
                assignment[0] == 2 and trigger[0] == 1 and assignment[1] == trigger[1]
                for assignment, trigger in boundary_pairs
            )
        )

    def test_ordered_model_has_one_transition_block_per_flight_aircraft(self):
        scheduler = OrderedAEventMILPScheduler(str(SOURCE))
        model = scheduler.build_model()

        self.assertEqual(
            len(list(model.e9_e13_prefix_state)),
            7 * len(model.Q),
        )

    def test_optimized_ordered_model_removes_a_only_redundancies(self):
        baseline_scheduler = OrderedAEventMILPScheduler(str(SOURCE))
        baseline = baseline_scheduler.build_model()
        optimized_scheduler = OptimizedPaperEventBasedMILPScheduler(str(SOURCE))
        optimized = optimized_scheduler.build_model()

        self.assertFalse(hasattr(optimized, "event_count"))
        self.assertFalse(hasattr(optimized, "c11_event_count"))
        self.assertFalse(hasattr(optimized, "event_type_exclusivity"))
        self.assertFalse(hasattr(optimized, "e7_pairwise_overlap"))
        self.assertTrue(hasattr(optimized, "e7_clique_strengthening"))
        self.assertEqual(
            len(list(optimized.e9_e13_prefix_state)),
            6 * len(optimized.Q),
        )
        sample = next(iter(optimized.q.values()))
        self.assertEqual(sample.lb, 0.0)
        self.assertIsNotNone(sample.ub)
        self.assertLess(
            len(list(optimized.component_data_objects(Var, active=True))),
            len(list(baseline.component_data_objects(Var, active=True))),
        )
        self.assertLess(
            len(list(optimized.component_data_objects(Constraint, active=True))),
            len(list(baseline.component_data_objects(Constraint, active=True))),
        )

    def test_flexible_model_replaces_immediate_timing_families(self):
        scheduler = FlexiblePaperEventBasedMILPScheduler(str(SOURCE))
        model = scheduler.build_model()

        self.assertEqual(scheduler.FORMULATION_ID, "event_based_flex")
        self.assertFalse(hasattr(model, "e14_maintenance_block"))
        self.assertFalse(hasattr(model, "e15_maintenance_capacity"))
        self.assertTrue(hasattr(model, "s"))
        self.assertTrue(hasattr(model, "s_ticks"))
        self.assertTrue(hasattr(model, "event_selected"))
        self.assertTrue(hasattr(model, "event_offset"))
        self.assertTrue(hasattr(model, "event_completion"))
        self.assertTrue(hasattr(model, "e14_flex_maintenance_block"))
        self.assertTrue(hasattr(model, "e15_flex_completion_bounds"))
        self.assertTrue(hasattr(model, "e17_flex_time_comparisons"))
        self.assertTrue(hasattr(model, "e18_flex_time_comparisons"))
        self.assertTrue(hasattr(model, "e19_flex_active_at_start"))
        self.assertTrue(hasattr(model, "e20_flex_station_capacity"))
        self.assertTrue(hasattr(model, "e21_flex_event_uniqueness"))
        self.assertFalse(hasattr(model, "flex_order"))

    def test_flexible_model_keeps_e1_e13_rows_unchanged(self):
        optimized = OptimizedPaperEventBasedMILPScheduler(str(SOURCE)).build_model()
        flexible = FlexiblePaperEventBasedMILPScheduler(str(SOURCE)).build_model()

        for family in (
            "e4_coverage",
            "e5_e6_continuity_turn",
            "e7_clique_strengthening",
            "e8_event_assignment",
            "e9_e13_prefix_state",
        ):
            self.assertEqual(
                len(list(getattr(flexible, family))),
                len(list(getattr(optimized, family))),
                family,
            )
        self.assertEqual(len(flexible.Z), len(optimized.Z))
        self.assertEqual(len(flexible.Q), len(optimized.Q))

    def test_flexible_offsets_span_the_deferral_window(self):
        scheduler = FlexiblePaperEventBasedMILPScheduler(str(SOURCE))
        model = scheduler.build_model()

        expected_ub = scheduler.check_dur["A"] + scheduler.MAX_MAINT_DEFER
        self.assertEqual(len(model.s), len(model.Z))
        self.assertEqual(len(model.s_ticks), len(model.Z))
        for offset_ticks in model.s_ticks.values():
            self.assertIs(offset_ticks.domain, NonNegativeIntegers)
            self.assertEqual(offset_ticks.lb, 0)
            self.assertEqual(offset_ticks.ub, expected_ub)
        self.assertEqual(len(model.e15_flex_completion_bounds), 2 * len(model.Z))

    def test_flexible_model_builds_exact_capacity_pairs(self):
        scheduler = FlexiblePaperEventBasedMILPScheduler(str(SOURCE))
        scheduler.station_cap["M"] = 1
        model = scheduler.build_model()

        self.assertGreater(len(model.FLEX_DISTINCT_PAIRS), 0)
        self.assertEqual(
            len(model.e17_flex_time_comparisons),
            2 * len(model.FLEX_DISTINCT_PAIRS),
        )
        self.assertEqual(
            len(model.e18_flex_time_comparisons),
            2 * len(model.FLEX_DISTINCT_PAIRS),
        )
        self.assertEqual(
            len(model.e20_flex_station_capacity),
            len(model.FM),
        )
        self.assertEqual(
            len(model.e21_flex_event_uniqueness),
            len(model.FM),
        )
        self.assertTrue(
            all((flight, flight) in model.FLEX_PAIRS for flight in model.FM)
        )

    def test_flexible_capacity_uses_half_open_event_start_occupancy(self):
        scheduler = FlexiblePaperEventBasedMILPScheduler(str(SOURCE))
        scheduler.station_cap["M"] = 1
        model = scheduler.build_model()
        first, second = min(
            model.FLEX_DISTINCT_PAIRS,
            key=lambda pair: abs(
                scheduler.flight_data[pair[0]]["arrivalTime"]
                - scheduler.flight_data[pair[1]]["arrivalTime"]
            ),
        )
        reverse_pair = (second, first)
        self.assertIn(reverse_pair, model.FLEX_DISTINCT_PAIRS)

        first_key = next(key for key in model.Z if key[0] == first)
        second_key = next(key for key in model.Z if key[0] == second)
        first_arrival = scheduler.flight_data[first]["arrivalTime"]
        second_arrival = scheduler.flight_data[second]["arrivalTime"]
        duration = scheduler.check_dur["A"]
        grid = scheduler.MAINTENANCE_TIME_GRID
        fm_order = list(model.FM)

        def set_events(completions):
            for key in model.Z:
                model.z[key].set_value(0)
                model.s_ticks[key].set_value(0)
            for flight, completion in completions.items():
                key = first_key if flight == first else second_key
                model.z[key].set_value(1)
                offset_ticks = round(
                    (completion - scheduler.flight_data[flight]["arrivalTime"])
                    / grid
                )
                model.s_ticks[key].set_value(offset_ticks)

            for pair in model.FLEX_DISTINCT_PAIRS:
                r, q = pair
                difference = value(
                    model.event_completion[q] - model.event_completion[r]
                )
                before = int(difference <= 0)
                in_window = int(difference >= -duration + grid)
                model.flex_before[pair].set_value(before)
                model.flex_in_window[pair].set_value(in_window)
                event_r = value(model.event_selected[r] > 0.5)
                event_q = value(model.event_selected[q] > 0.5)
                model.flex_active_at_start[pair].set_value(
                    int(event_r and event_q and before and in_window)
                )
            for flight in model.FM:
                model.flex_active_at_start[flight, flight].set_value(
                    int(value(model.event_selected[flight]) > 0.5)
                )

            for family in (
                model.e17_flex_time_comparisons,
                model.e18_flex_time_comparisons,
                model.e19_flex_active_at_start,
            ):
                for constraint in family.values():
                    body = value(constraint.body)
                    if constraint.has_lb():
                        self.assertGreaterEqual(body, value(constraint.lower) - 1e-8)
                    if constraint.has_ub():
                        self.assertLessEqual(body, value(constraint.upper) + 1e-8)

        common_completion = max(first_arrival, second_arrival) + duration
        set_events({first: common_completion, second: common_completion})
        first_capacity_row = model.e20_flex_station_capacity[
            fm_order.index(first) + 1
        ]
        self.assertGreater(value(first_capacity_row.body), 0.0)

        set_events({first: common_completion, second: common_completion + duration})
        self.assertLessEqual(value(first_capacity_row.body), 0.0)

    def test_flexible_model_rejects_off_grid_timestamps(self):
        scheduler = FlexiblePaperEventBasedMILPScheduler(str(SOURCE))
        flight = scheduler.flight_ids[0]
        scheduler.flight_data[flight]["arrivalTime"] += 0.5

        with self.assertRaisesRegex(ValueError, "1-minute grid"):
            scheduler.build_model()

    def test_baseline_event_models_keep_immediate_maintenance_timing(self):
        for builder in (
            OrderedAEventMILPScheduler,
            OptimizedPaperEventBasedMILPScheduler,
        ):
            model = builder(str(SOURCE)).build_model()
            self.assertTrue(hasattr(model, "e14_maintenance_block"), builder.__name__)
            self.assertTrue(hasattr(model, "e15_maintenance_capacity"), builder.__name__)
            self.assertFalse(hasattr(model, "s"), builder.__name__)

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
