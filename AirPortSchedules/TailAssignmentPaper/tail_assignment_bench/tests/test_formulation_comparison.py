from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from pyomo.opt import SolverFactory

THIS_FILE = Path(__file__).resolve()
PKG_ROOT = THIS_FILE.parents[1]
REPO_ROOT = THIS_FILE.parents[2]
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.compare_formulations import FORMULATIONS, build_scheduler
from src.event_model import EventMILPScheduler
from src.model import LegacyEndpointSplitMILPScheduler, MILP_Sheduler


class FormulationComparisonTests(unittest.TestCase):
    INSTANCE = REPO_ROOT / "data/instances/DataCplex_density=0.5_p=10_h=7_test_0.json"
    ALL_CHECKS_INSTANCE = REPO_ROOT / "data/instances/ABCD_all_checks_test.json"

    def test_legacy_name_preserves_existing_scheduler_api(self) -> None:
        self.assertTrue(issubclass(LegacyEndpointSplitMILPScheduler, MILP_Sheduler))
        self.assertEqual(
            LegacyEndpointSplitMILPScheduler.FORMULATION_ID,
            "legacy_endpoint_split",
        )

    def test_harness_builds_distinct_formulation_structures(self) -> None:
        legacy, _ = build_scheduler("legacy_endpoint_split", self.INSTANCE)
        exact, _ = build_scheduler("event_exact_state", self.INSTANCE)

        self.assertIsInstance(legacy, LegacyEndpointSplitMILPScheduler)
        self.assertIsInstance(exact, EventMILPScheduler)
        self.assertEqual(
            {legacy.FORMULATION_ID, exact.FORMULATION_ID},
            set(FORMULATIONS),
        )
        self.assertTrue(hasattr(legacy.model, "c13"))
        self.assertFalse(hasattr(legacy.model, "u"))
        self.assertTrue(hasattr(exact.model, "u"))
        self.assertTrue(hasattr(exact.model, "c12_hour_flow"))
        self.assertFalse(hasattr(exact.model, "c13"))

    def test_unknown_formulation_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown formulation"):
            build_scheduler("unknown", self.INSTANCE)

    @unittest.skipUnless(
        SolverFactory("cplex").available(exception_flag=False),
        "CPLEX is required for the four-day formulation regression",
    )
    def test_four_day_counterexample_separates_split_and_exact_state(self) -> None:
        data = {
            "Aircrafts": [0],
            "AIRCRAFT_INIT_POS": {"0": "A"},
            "Flights": [
                [1, "A", "A", 100.0, 101.0],
                [2, "A", "A", 1500.0, 1510.0],
                [3, "A", "A", 4380.0, 4390.0],
            ],
            "Maintenance_Thresholds": {
                "A": 10,
                "B": 1000,
                "C": 100,
                "D": 200,
            },
            "Maintenance_Durations": {"A": 1, "B": 1, "C": 1, "D": 1},
            "Station_Capacity": {"A": 1},
            "Initial_Checks": {
                "A": {"0": 0},
                "B": {"0": 0},
                "C_Days": {"0": 0},
                "D_Days": {"0": 0},
            },
            "Cost_Matrix": [[1], [1], [1]],
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            instance_path = Path(temporary_directory) / "four_day_c13.json"
            instance_path.write_text(json.dumps(data), encoding="utf-8")

            legacy, _ = build_scheduler("legacy_endpoint_split", instance_path)
            exact, _ = build_scheduler("event_exact_state", instance_path)

            legacy_checks = {(1, 0, 1, "A"), (3, 0, 4, "A")}
            for key in legacy.model.z:
                legacy.model.z[key].fix(1 if key in legacy_checks else 0)

            exact_checks = {(1, 0, "A"), (3, 0, "A")}
            for key in exact.model.z:
                exact.model.z[key].fix(1 if key in exact_checks else 0)

            legacy_summary = legacy.solve(
                solver_name="cplex",
                tee=False,
                time_limit=30,
            )
            exact_summary = exact.solve(
                solver_name="cplex",
                tee=False,
                time_limit=30,
            )

        self.assertEqual(legacy_summary["status"], "optimal")
        self.assertEqual(exact_summary["status"], "infeasible")

    @unittest.skipUnless(
        SolverFactory("cplex").available(exception_flag=False),
        "CPLEX is required for the exact-state boundary regression",
    )
    def test_exact_state_solves_all_checks_boundary(self) -> None:
        exact, _ = build_scheduler("event_exact_state", self.ALL_CHECKS_INSTANCE)
        summary = exact.solve(
            solver_name="cplex",
            tee=False,
            time_limit=30,
        )

        self.assertEqual(summary["status"], "optimal")
        self.assertEqual(summary["formulation"], "event_exact_state")
        self.assertAlmostEqual(summary["obj"], 9500.0)


if __name__ == "__main__":
    unittest.main()