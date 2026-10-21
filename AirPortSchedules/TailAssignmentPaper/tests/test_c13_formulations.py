"""Tests for the C13 formulation toggles ported from the thesis_version branch.

Covers the paper-vs-split selector (``use_paper_c13``) and the interval-tight
big-M option (``use_tight_c13_m``) merged into ``src/model.py``.
"""
import sys
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from pyomo.environ import Binary, ConcreteModel, NonNegativeReals, Set, Var, value

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model import (
    LegacyCorrectedMILPScheduler,
    LegacyCorrectedStrengthenedMILPScheduler,
    LegacyHourPrefixMILPScheduler,
    LegacyPaperC13MILPScheduler,
    LegacyStrictIntervalMILPScheduler,
    MILP_Sheduler,
)
from src.validate_maintenance import validate_solved_model

SOURCE = ROOT / "data" / "instances" / "ABCD_near_threshold_test.json"


class C13FormulationTests(unittest.TestCase):
    def test_paper_c13_omits_consecutive_checked_days(self):
        data = json.loads((ROOT / "data" / "instances" / "c13_loophole_test.json").read_text(encoding="utf-8"))
        data["Flights"][1][4] = 2060.0
        fixture = ROOT / "tests" / "_temporary_adjacent_c13_fixture.json"
        fixture.write_text(json.dumps(data), encoding="utf-8")
        try:
            scheduler = LegacyPaperC13MILPScheduler(
                str(fixture), enabled_checks=["A"], max_hour_check_deferral_days=0
            )
            model = scheduler.build_model(use_paper_c13=True)
            for variable in model.x.values():
                variable.set_value(1)
            for variable in model.z.values():
                variable.set_value(0)
            for variable in model.y.values():
                variable.set_value(0)
            for variable in model.mega.values():
                variable.set_value(0)
            model.z[1, 0, 1, "A"].set_value(1)
            model.z[2, 0, 2, "A"].set_value(1)
            model.y[0, 1, "A"].set_value(1)
            model.y[0, 2, "A"].set_value(1)
            model.mega[0, 1, "A"].set_value(1)
            model.mega[0, 2, "A"].set_value(1)

            for family in (model.c13, model.c13b):
                for row in family.values():
                    self.assertLessEqual(value(row.body), value(row.upper) + 1e-6)
            self.assertGreater(len(validate_solved_model(scheduler)), 0)
        finally:
            fixture.unlink(missing_ok=True)

    def test_strict_opening_without_first_day_flights_stays_symbolic(self):
        scheduler = LegacyStrictIntervalMILPScheduler(str(SOURCE), enabled_checks=["A"])
        scheduler._f_dep_between_days = lambda _first, _last: []
        model = ConcreteModel()
        model.P = Set(initialize=[0])
        model.D = Set(initialize=[1])
        model.C = Set(initialize=["A"])
        model.mega = Var(model.P, model.D, model.C, domain=Binary, initialize=0)
        scheduler.days = [1]
        scheduler._add_c13b_existing_hrs(model, use_strict_state=True)
        self.assertEqual(len(model.c13b), 1)
        self.assertLessEqual(value(model.c13b[1].body), value(model.c13b[1].upper))

    def test_strict_opening_hours_include_first_and_last_days(self):
        source = ROOT / "data" / "instances" / "c13_loophole_test.json"
        for scheduler_type in (
            LegacyStrictIntervalMILPScheduler,
            LegacyHourPrefixMILPScheduler,
        ):
            for initial_minutes, expected_violation in ((594, True), (590, False)):
                with self.subTest(
                    formulation=scheduler_type.__name__, initial=initial_minutes
                ):
                    scheduler = scheduler_type(
                        str(source), enabled_checks=["A"],
                        max_hour_check_deferral_days=0,
                    )
                    scheduler.init_check_hrs["A"][0] = initial_minutes / 60
                    model = scheduler.build_model()
                    for variable in model.x.values():
                        variable.set_value(0)
                    for variable in model.mega.values():
                        variable.set_value(0)
                    model.x[1, 0].set_value(1)
                    model.mega[0, 1, "A"].set_value(1)
                    if hasattr(model, "hour_cumulative"):
                        for (aircraft, day), variable in model.hour_cumulative.items():
                            variable.set_value(10 if day >= 1 else 0)
                    opening = model.c13b[1]
                    violated = value(opening.body) > value(opening.upper) + 1e-6
                    self.assertEqual(violated, expected_violation)
                    self.assertEqual(len(model.c13b), len(model.P) * len(model.D))
                    if hasattr(model, "hour_cumulative"):
                        final_row = model.c13b[len(model.c13b)]
                        self.assertIn(
                            f"hour_cumulative[0,{max(model.D)}]", str(final_row.expr)
                        )

    def test_unneeded_a_check_pruning_requires_a_only_safe_bound(self):
        data = json.loads(SOURCE.read_text(encoding="utf-8"))
        data["Maintenance_Thresholds"]["A"] = 100_000
        for aircraft in data["Aircrafts"]:
            data["Initial_Checks"]["A"][str(aircraft)] = 0
        fixture = ROOT / "tests" / "_temporary_pruning_fixture.json"
        fixture.write_text(json.dumps(data), encoding="utf-8")
        try:
            baseline_scheduler = LegacyCorrectedStrengthenedMILPScheduler(
                str(fixture), enabled_checks=["A"]
            )
            baseline = baseline_scheduler.build_model()
            pruned_scheduler = LegacyCorrectedStrengthenedMILPScheduler(
                str(fixture), enabled_checks=["A"]
            )
            pruned = pruned_scheduler.build_model(prune_unneeded_hour_checks=True)

            self.assertEqual(
                pruned_scheduler.unneeded_hour_checks_by_aircraft,
                set(data["Aircrafts"]),
            )
            self.assertGreater(len(baseline.Z), 0)
            self.assertEqual(len(pruned.Z), 0)
            self.assertGreater(len(list(baseline.c9)), len(list(pruned.c9)))

            hierarchy_scheduler = MILP_Sheduler(
                str(fixture), enabled_checks=["A", "C"]
            )
            hierarchy = hierarchy_scheduler.build_model(
                prune_unneeded_hour_checks=True
            )
            self.assertEqual(
                len(hierarchy.Z),
                hierarchy_scheduler.z_var_count,
            )
            self.assertEqual(
                hierarchy_scheduler.unneeded_hour_checks_by_aircraft,
                set(),
            )
        finally:
            fixture.unlink(missing_ok=True)

    def test_prefix_flow_replaces_interval_flight_sums(self):
        interval_scheduler = LegacyStrictIntervalMILPScheduler(
            str(SOURCE),
            enabled_checks=["A"],
            max_hour_check_deferral_days=0,
        )
        interval_model = interval_scheduler.build_model()
        prefix_scheduler = LegacyHourPrefixMILPScheduler(
            str(SOURCE), enabled_checks=["A"], max_hour_check_deferral_days=0
        )
        prefix_model = prefix_scheduler.build_model()

        self.assertFalse(hasattr(interval_model, "hour_cumulative"))
        self.assertTrue(hasattr(prefix_model, "hour_cumulative"))
        self.assertEqual(len(prefix_model.HOUR_DAYS), len(prefix_model.D) + 1)
        self.assertEqual(
            len(list(prefix_model.hour_state_flow)),
            len(prefix_model.P) * len(prefix_model.D),
        )
        self.assertEqual(len(list(prefix_model.c13)), len(list(interval_model.c13)))
        self.assertEqual(len(list(prefix_model.c13b)), len(list(interval_model.c13b)))

    def test_zero_legacy_deferral_builds_without_empty_capacity_rows(self):
        scheduler = MILP_Sheduler(
            str(SOURCE),
            enabled_checks=["A"],
            max_hour_check_deferral_days=0,
        )
        model = scheduler.build_model()

        self.assertTrue(hasattr(model, "c10"))
        self.assertGreater(len(model.c10), 0)

    def test_maintenance_replay_accepts_legacy_and_ordered_trigger_indices(self):
        flight_data = {
            1: {"origin": "M", "destination": "M", "departureTime": 0, "arrivalTime": 60, "duration": 60, "day_departure": 1, "day_arrival": 1},
            2: {"origin": "M", "destination": "M", "departureTime": 200, "arrivalTime": 250, "duration": 50, "day_departure": 2, "day_arrival": 2},
        }
        for z_dimension, trigger_index in (
            (3, (1, 0, "A")),
            (4, (1, 0, 1, "A")),
        ):
            with self.subTest(z_dimension=z_dimension):
                model = ConcreteModel()
                model.F = Set(initialize=[1, 2])
                model.P = Set(initialize=[0])
                model.X = Set(dimen=2, initialize=[(1, 0), (2, 0)])
                model.Z = Set(dimen=z_dimension, initialize=[trigger_index])
                model.x = Var(model.X, domain=Binary, initialize=1)
                model.z = Var(model.Z, domain=Binary, initialize=0)
                if z_dimension == 4:
                    model.D = Set(initialize=[1])
                    model.C = Set(initialize=["A"])
                    model.y = Var(model.P, model.D, model.C, domain=Binary, initialize=0)
                scheduler = SimpleNamespace(
                    model=model,
                    CHECK_LIST=("A",),
                    check_days={"A": None},
                    check_hrs={"A": 100 / 60},
                    check_dur={"A": 60},
                    init_check_hrs={"A": {0: 0}},
                    flight_data=flight_data,
                    MIN_TURN=10,
                    maint_airports=(),
                    station_cap={},
                    _x_aircrafts_for_flight=lambda _flight: [0],
                )

                model.z[trigger_index].set_value(1)
                if z_dimension == 4:
                    model.y[0, 1, "A"].set_value(1)
                self.assertEqual(validate_solved_model(scheduler), [])

                model.z[trigger_index].set_value(0)
                if z_dimension == 4:
                    model.y[0, 1, "A"].set_value(0)
                violations = validate_solved_model(scheduler)
                self.assertEqual(len(violations), 1)
                self.assertEqual(violations[0]["window_end_day"], 2)
                self.assertEqual(violations[0]["accumulated_min"], 110)

    def test_flexible_event_replay_detects_capacity_and_blocking_violations(self):
        model = ConcreteModel()
        model.F = Set(initialize=[1, 2, 3])
        model.P = Set(initialize=[0, 1])
        model.X = Set(dimen=2, initialize=[(1, 0), (2, 1), (3, 0)])
        model.Z = Set(dimen=3, initialize=[(1, 0, "A"), (2, 1, "A")])
        model.x = Var(model.X, domain=Binary, initialize=1)
        model.z = Var(model.Z, domain=Binary, initialize=1)
        model.s = Var(model.Z, domain=NonNegativeReals, initialize=120)
        scheduler = SimpleNamespace(
            model=model,
            CHECK_LIST=("A",),
            check_days={"A": None},
            check_hrs={"A": 100 / 60},
            check_dur={"A": 60},
            init_check_hrs={"A": {0: 0, 1: 0}},
            MAX_MAINT_DEFER=120,
            MAINTENANCE_TIME_GRID=1,
            MIN_TURN=10,
            maint_airports=("M",),
            station_cap={"M": 1},
            flight_data={
                1: {"origin": "M", "destination": "M", "departureTime": 0, "arrivalTime": 100, "duration": 30, "day_arrival": 1},
                2: {"origin": "M", "destination": "M", "departureTime": 20, "arrivalTime": 130, "duration": 30, "day_arrival": 1},
                3: {"origin": "M", "destination": "M", "departureTime": 200, "arrivalTime": 210, "duration": 10, "day_arrival": 1},
            },
            _x_aircrafts_for_flight=lambda flight: [
                aircraft for candidate_flight, aircraft in model.X
                if candidate_flight == flight
            ],
        )

        violations = validate_solved_model(scheduler)
        violation_types = {violation["type"] for violation in violations}
        self.assertIn("maintenance_capacity", violation_types)
        self.assertIn("flight_during_maintenance", violation_types)

    def test_consecutive_single_day_checks_are_charged_separately(self):
        scheduler = LegacyCorrectedStrengthenedMILPScheduler(
            str(SOURCE), enabled_checks=["A"]
        )
        model = scheduler.build_model()
        self.assertEqual(scheduler.check_dur_days["A"], 0)

        consecutive_days = [
            (day, day + 1)
            for day in sorted(model.D)
            if day + 1 in model.D
        ]
        self.assertTrue(consecutive_days)
        first_day, second_day = consecutive_days[0]
        aircraft = next(iter(model.P))

        for variable in model.x.values():
            variable.set_value(0)
        for variable in model.y.values():
            variable.set_value(0)
        for variable in model.maintenance_start.values():
            variable.set_value(0)

        model.y[aircraft, first_day, "A"].set_value(1)
        model.y[aircraft, second_day, "A"].set_value(1)
        model.maintenance_start[aircraft, first_day, "A"].set_value(1)

        self.assertEqual(value(model.obj.expr), 2 * 100)

    def test_tight_c13_m_is_opt_in_and_interval_bounded(self):
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

        self.assertEqual(len(list(baseline.c13)), len(list(tight.c13)))
        self.assertGreaterEqual(tight_scheduler._c13_big_m("A", 0, 1, 3), 0)
        self.assertIn("9999999", str(next(iter(baseline.c13.values())).expr))
        self.assertNotIn("9999999", str(next(iter(tight.c13.values())).expr))

    def test_paper_c13_is_opt_in_and_keeps_row_count(self):
        scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
        split = scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_paper_c13=False,
        )
        paper_scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
        paper = paper_scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_paper_c13=True,
        )

        # Split builds two rows per window; paper builds one.
        self.assertEqual(len(list(paper.c13)) * 2, len(list(split.c13)))

    def test_strict_hour_state_removes_endpoint_relaxation(self):
        scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
        strict = scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_strict_hour_state=True,
        )

        self.assertTrue(hasattr(strict, "c13_exact_state"))
        self.assertGreater(len(list(strict.c13_exact_state)), 0)
        self.assertFalse(hasattr(strict, "c13"))
        self.assertFalse(hasattr(strict, "c13b"))

    def test_strengthened_corrected_state_is_sparse_and_smaller(self):
        baseline_scheduler = LegacyCorrectedMILPScheduler(
            str(SOURCE), enabled_checks=["A"]
        )
        baseline = baseline_scheduler.build_model()
        strengthened_scheduler = LegacyCorrectedStrengthenedMILPScheduler(
            str(SOURCE), enabled_checks=["A"]
        )
        strengthened = strengthened_scheduler.build_model()

        self.assertEqual(len(strengthened.h), len(strengthened.P) * len(strengthened.D))
        sample = next(iter(strengthened.h.values()))
        self.assertEqual(sample.lb, 0.0)
        self.assertEqual(sample.ub, strengthened_scheduler.check_hrs["A"] * 60.0)
        self.assertLess(
            len(list(strengthened.c13_exact_state)),
            len(list(baseline.c13_exact_state)),
        )
        self.assertFalse(hasattr(strengthened, "c4_pairwise_overlap"))
        self.assertTrue(hasattr(strengthened, "c5_clique_overlap"))


if __name__ == "__main__":
    unittest.main()
