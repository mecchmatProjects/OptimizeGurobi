from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
import sys

THIS_FILE = Path(__file__).resolve()
PKG_ROOT = THIS_FILE.parents[1]
REPO_ROOT = THIS_FILE.parents[2]
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tap_bench.benchmark.runner import BenchmarkRunner
from tap_bench.contracts.method import MethodConfig, MethodRegistry
from tap_bench.criteria.score import CriteriaProfile
from tap_bench.io.instance_loader import InstanceLoader
from tap_bench.methods import (
    AntColonyHeuristicMethod,
    BruteForceExactMethod,
    DijkstraSpaceTimeHeuristicMethod,
    DynamicProgrammingExactSmallMethod,
    GreedyBaselineMethodAdapter,
)
from tap_bench.cli.main import _load_methods


class NewMethodsAndLegacyCsvTests(unittest.TestCase):
    def test_new_methods_and_legacy_csv_schema(self) -> None:
        instance = InstanceLoader.load("data/instances/ABCD_no_maint_test.json")

        registry = MethodRegistry()
        registry.register(GreedyBaselineMethodAdapter())
        registry.register(DijkstraSpaceTimeHeuristicMethod())
        registry.register(AntColonyHeuristicMethod(iterations=4, ants=3))
        registry.register(BruteForceExactMethod())
        registry.register(DynamicProgrammingExactSmallMethod())

        runner = BenchmarkRunner(
            registry=registry,
            config=MethodConfig(time_limit_s=30, random_seed=7),
            profile=CriteriaProfile(),
        )

        method_ids = ["greedy_baseline", "dijkstra_heuristic", "aco_heuristic", "bruteforce_exact", "dp_exact_small"]
        records = runner.run([instance], method_ids)
        self.assertEqual(len(records), len(method_ids))
        self.assertIn("dijkstra_heuristic", {record.method_id for record in records})
        self.assertIn("aco_heuristic", {record.method_id for record in records})
        self.assertIn("bruteforce_exact", {record.method_id for record in records})

        with tempfile.TemporaryDirectory() as tmp:
            legacy_csv = Path(tmp) / "legacy.csv"
            runner.write_legacy_csv(records, str(legacy_csv))
            self.assertTrue(legacy_csv.exists())

            with legacy_csv.open(newline="", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                header = next(reader)

        self.assertEqual(
            header,
            [
                "stem",
                "mode",
                "flights",
                "assigned",
                "unassigned",
                "status",
                "objective",
                "gap_pct",
                "cpu_s",
                "wall_s",
                "num_vars",
                "num_constraints",
                "returncode",
            ],
        )

    def test_methods_subset_config_loader(self) -> None:
        subset = _load_methods(
            ["greedy_baseline", "dijkstra_heuristic", "aco_heuristic", "milp_compact"],
            "tail_assignment_bench/configs/methods_subset.json",
        )
        self.assertEqual(subset, ["greedy_baseline", "dijkstra_heuristic", "aco_heuristic"])


if __name__ == "__main__":
    unittest.main()
