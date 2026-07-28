import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model import Scheduler


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


if __name__ == "__main__":
    unittest.main()
