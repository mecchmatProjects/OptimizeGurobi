import json
import sys
import unittest
from pathlib import Path
from pyomo.environ import Var

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from benchmark_validation import (
    validate_benchmark_certificate,
    verify_milp_certificate,
)
from experiments.run_khaled_30day import build_routing_start
import fore_benchgen
from model import MILP_Sheduler, Scheduler
from experiments.run_khaled_30day import validated_bounds


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

    scheduler = MILP_Sheduler(str(fixture), max_hour_check_deferral_days=3)
    scheduler.build_model(
        use_sparse_maint_aircraft_domain=True,
        use_day_specific_maintenance_bounds=True,
        use_aircraft_routing_reachability=True,
        use_tight_c13_m=True,
    )
    milp_report = verify_milp_certificate(scheduler, certificate)
    assert milp_report["status"] == "PASS"
    assert milp_report["checked_constraints"] > 0

    global_scheduler = MILP_Sheduler(str(fixture), max_hour_check_deferral_days=3)
    global_report = verify_milp_certificate(
        global_scheduler,
        certificate,
        use_sparse_maint_aircraft_domain=True,
        use_day_specific_maintenance_bounds=True,
        use_aircraft_routing_reachability=True,
        use_tight_c13_m=True,
        use_global_maint_trigger=True,
    )
    assert global_report["status"] == "PASS"
    assert global_report["checked_constraints"] > 0


def test_p20_h39_regression_instance_has_valid_complete_certificate():
    fixture = ROOT / "data" / "feasible_p20_h39" / "med3_p20_h39_r1.json"
    certificate_path = fixture.with_name("med3_p20_h39_r1.solution.json")
    instance = json.loads(fixture.read_text(encoding="utf-8"))
    certificate = json.loads(
        certificate_path.read_text(encoding="utf-8")
    )

    report = validate_benchmark_certificate(instance, certificate)

    assert len(instance["Aircrafts"]) == 20
    assert instance["Parameters"]["Target_Horizon_Days"] == 39
    assert report["status"] == "PASS"
    assert report["milp_representable"]


class P20H39RegressionTests(unittest.TestCase):
    def test_saved_instance_is_certified_for_39_day_milp(self):
        fixture = ROOT / "data" / "feasible_p20_h39" / "med3_p20_h39_r1.json"
        certificate_path = fixture.with_name("med3_p20_h39_r1.solution.json")
        instance = json.loads(fixture.read_text(encoding="utf-8"))
        certificate = json.loads(certificate_path.read_text(encoding="utf-8"))

        report = validate_benchmark_certificate(instance, certificate)

        self.assertEqual(len(instance["Aircrafts"]), 20)
        self.assertEqual(instance["Parameters"]["Target_Horizon_Days"], 39)
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["milp_representable"])


class ZeroBasedCostIndexTests(unittest.TestCase):
    def test_long_family_cost_rows_follow_flight_array_order(self):
        fixture = ROOT / "data" / "Long_family" / "md30_p20_h30_r1.json"
        instance = json.loads(fixture.read_text(encoding="utf-8"))
        heuristic = Scheduler(str(fixture), allow_ferry=False)
        milp = MILP_Sheduler(fixture, enabled_checks=["A"])

        self.assertEqual(instance["Flights"][0][0], 0)
        for row, flight in enumerate(instance["Flights"]):
            fid = flight[0]
            for column, aircraft in enumerate(instance["Aircrafts"]):
                expected = instance["Cost_Matrix"][row][column]
                self.assertEqual(heuristic._flight_cost(fid, aircraft), expected)
                self.assertEqual(milp._flight_cost(fid, aircraft), expected)


class ClassicalModelSizeTests(unittest.TestCase):
    def test_maintenance_off_model_contains_only_assignment_variables(self):
        fixture = ROOT / "data" / "Long_family" / "md30_p20_h30_r1.json"
        scheduler = MILP_Sheduler(fixture)
        model = scheduler.build_model(
            use_maintenance=False,
            use_overlap=False,
        )

        variable_names = {
            variable.name
            for variable in model.component_data_objects(ctype=Var)
        }

        self.assertEqual(len(variable_names), scheduler.x_var_count)
        self.assertFalse(hasattr(model, "z"))
        self.assertFalse(hasattr(model, "y"))
        self.assertFalse(hasattr(model, "mega"))
        self.assertFalse(hasattr(model, "maintenance_start"))
        self.assertEqual(scheduler.z_var_count, 0)

    def test_aircraft_reachability_prunes_and_rebuild_restores_arcs(self):
        fixture = ROOT / "data" / "Long_family" / "md30_p20_h30_r1.json"
        scheduler = MILP_Sheduler(fixture)
        original_arcs = set(scheduler.x_arcs_set)

        scheduler.build_model(
            use_maintenance=False,
            use_overlap=False,
            use_aircraft_routing_reachability=True,
        )
        reachable_arc_count = scheduler.x_var_count
        self.assertLess(reachable_arc_count, len(original_arcs))

        scheduler.build_model(use_maintenance=False, use_overlap=False)
        self.assertEqual(scheduler.x_arcs_set, original_arcs)

    def test_day_state_bounds_match_trigger_domain(self):
        fixture = ROOT / "data" / "instances" / "ABCD_all_checks_test.json"
        scheduler = MILP_Sheduler(fixture, max_hour_check_deferral_days=3)
        model = scheduler.build_model(
            use_sparse_maint_aircraft_domain=True,
            use_day_specific_maintenance_bounds=True,
        )
        possible_y = {
            (aircraft, day, check)
            for _, aircraft, day, check in model.Z
        }

        for aircraft in model.P:
            for day in model.D:
                for check in model.C:
                    should_be_possible = (aircraft, day, check) in possible_y
                    self.assertEqual(
                        model.y[aircraft, day, check].ub,
                        1 if should_be_possible else 0,
                    )

        expected_c11_rows = len(possible_y)
        self.assertEqual(len(model.c11), expected_c11_rows)


class KhaledRunBoundTests(unittest.TestCase):
    def test_solver_dual_below_assignment_floor_is_rejected(self):
        lower, consistent, gap = validated_bounds(
            raw_dual=18_689.4,
            primal=1_150_533.1,
            assignment_floor=1_014_693.0,
        )
        self.assertFalse(consistent)
        self.assertEqual(lower, 1_014_693.0)
        self.assertIsNotNone(gap)

    def test_valid_solver_dual_is_used(self):
        lower, consistent, _ = validated_bounds(
            raw_dual=1_637_103.0,
            primal=1_735_942.0,
            assignment_floor=1_511_232.3,
        )
        self.assertTrue(consistent)
        self.assertEqual(lower, 1_637_103.0)

    def test_missing_solver_dual_falls_back_to_assignment_floor(self):
        lower, consistent, _ = validated_bounds(
            raw_dual=None,
            primal=2_296_130.8,
            assignment_floor=2_010_885.6,
        )
        self.assertFalse(consistent)
        self.assertEqual(lower, 2_010_885.6)


class CliqueOverlapTests(unittest.TestCase):
    def test_interval_cliques_cover_pairwise_conflicts(self):
        fixture = ROOT / "data" / "Long_family" / "md30_p20_h30_r1.json"
        scheduler = MILP_Sheduler(fixture)
        cliques = scheduler._maximal_overlap_cliques()
        covered_pairs = set()
        for clique in cliques:
            members = list(clique)
            for left_index, left in enumerate(members):
                left_flight = scheduler.flight_data[left]
                for right in members[left_index + 1:]:
                    right_flight = scheduler.flight_data[right]
                    self.assertLess(
                        left_flight["departureTime"],
                        right_flight["arrivalTime"] + scheduler.min_turn,
                    )
                    self.assertLess(
                        right_flight["departureTime"],
                        left_flight["arrivalTime"] + scheduler.min_turn,
                    )
                    covered_pairs.add(frozenset((left, right)))

        expected_pairs = set()
        flights = scheduler.flight_ids
        for position, left in enumerate(flights):
            left_flight = scheduler.flight_data[left]
            for right in flights[position + 1:]:
                right_flight = scheduler.flight_data[right]
                if (left_flight["departureTime"]
                        < right_flight["arrivalTime"] + scheduler.min_turn
                        and right_flight["departureTime"]
                        < left_flight["arrivalTime"] + scheduler.min_turn):
                    expected_pairs.add(frozenset((left, right)))

        self.assertEqual(covered_pairs, expected_pairs)

    def test_m20_path_cover_is_complete_and_classical_feasible(self):
        fixture = ROOT / "data" / "Long_family" / "md30_p20_h30_r1.json"
        scheduler = MILP_Sheduler(fixture)
        model = scheduler.build_model(
            use_maintenance=False,
            use_overlap=False,
            use_aircraft_routing_reachability=True,
        )
        assignment = build_routing_start(scheduler, model)

        self.assertEqual(len(assignment), len(scheduler.flight_ids))
        self.assertEqual(scheduler.z_var_count, 0)