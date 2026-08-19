import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model import Scheduler
from experiments.validate_semantic_alignment import validate


class HeuristicSelectorTests(unittest.TestCase):
    def setUp(self):
        self.data_path = ROOT / "data" / "instances" / "DataCplex_density=0.5_p=10_h=7_test_0.json"

    def test_greedy_strategy_runs(self):
        sc = Scheduler(str(self.data_path), heuristic="greedy")
        ac_fids, unassigned = sc.optimize()
        self.assertIsInstance(ac_fids, dict)
        self.assertEqual(len(ac_fids), len(sc.aircrafts))
        self.assertIsInstance(unassigned, list)

    def test_insertion_strategy_runs(self):
        sc = Scheduler(str(self.data_path), heuristic="insertion")
        ac_fids, unassigned = sc.optimize()
        self.assertIsInstance(ac_fids, dict)
        self.assertEqual(len(ac_fids), len(sc.aircrafts))
        self.assertIsInstance(unassigned, list)

    def test_repair_strategy_runs(self):
        sc = Scheduler(str(self.data_path), heuristic="repair")
        ac_fids, unassigned = sc.optimize()
        self.assertIsInstance(ac_fids, dict)
        self.assertEqual(len(ac_fids), len(sc.aircrafts))
        self.assertIsInstance(unassigned, list)

    def test_local_search_strategy_runs(self):
        sc = Scheduler(str(self.data_path), heuristic="local_search")
        ac_fids, unassigned = sc.optimize()
        self.assertIsInstance(ac_fids, dict)
        self.assertEqual(len(ac_fids), len(sc.aircrafts))
        self.assertIsInstance(unassigned, list)

    def test_dijkstra_strategy_runs(self):
        sc = Scheduler(str(self.data_path), heuristic="dijkstra")
        ac_fids, unassigned = sc.optimize()
        self.assertIsInstance(ac_fids, dict)
        self.assertEqual(len(ac_fids), len(sc.aircrafts))
        self.assertIsInstance(unassigned, list)

    def test_dijkstra_no_ferry_routes_are_feasible(self):
        sc = Scheduler(str(self.data_path), heuristic="dijkstra", allow_ferry=False)
        ac_fids, _ = sc.optimize()
        for aid, route in ac_fids.items():
            self.assertIsNotNone(sc.get_timeline(aid, route))

    def test_aco_strategy_runs(self):
        sc = Scheduler(
            str(self.data_path),
            heuristic="aco",
            aco_iterations=2,
            aco_ants=3,
            aco_seed=7,
        )
        ac_fids, unassigned = sc.optimize()
        self.assertIsInstance(ac_fids, dict)
        self.assertEqual(len(ac_fids), len(sc.aircrafts))
        self.assertIsInstance(unassigned, list)

    def test_aco_no_ferry_routes_are_feasible(self):
        sc = Scheduler(
            str(self.data_path),
            heuristic="aco",
            allow_ferry=False,
            aco_iterations=2,
            aco_ants=3,
            aco_seed=7,
        )
        ac_fids, _ = sc.optimize()
        for aid, route in ac_fids.items():
            self.assertIsNotNone(sc.get_timeline(aid, route))

    def test_milp_baseline_assignment_replays_in_timeline(self):
        data_path = ROOT / "data" / "instances" / "ABCD_no_maint_test.json"
        result = validate(data_path, solver_name="highs", time_limit=120)
        self.assertEqual(result["status"], "validated")
        self.assertTrue(result["route_valid"])



if __name__ == "__main__":
    unittest.main()
