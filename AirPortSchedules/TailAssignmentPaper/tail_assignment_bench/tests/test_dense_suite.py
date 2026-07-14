from __future__ import annotations

import sys
import unittest
from pathlib import Path

THIS_FILE = Path(__file__).resolve()
PKG_ROOT = THIS_FILE.parents[1]
REPO_ROOT = THIS_FILE.parents[2]
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def build_registry():
    from tap_bench.contracts.method import MethodRegistry
    from tap_bench.methods import (
        AntColonyHeuristicMethod,
        BruteForceExactMethod,
        DijkstraSpaceTimeHeuristicMethod,
        DynamicProgrammingExactSmallMethod,
        GreedyBaselineMethodAdapter,
        MilpCompactMethodAdapter,
    )

    registry = MethodRegistry()
    registry.register(GreedyBaselineMethodAdapter())
    registry.register(DijkstraSpaceTimeHeuristicMethod())
    registry.register(AntColonyHeuristicMethod(iterations=4, ants=3))
    registry.register(BruteForceExactMethod())
    registry.register(DynamicProgrammingExactSmallMethod())
    registry.register(MilpCompactMethodAdapter())
    return registry


class DenseSuiteTests(unittest.TestCase):
    def test_dense_suite_stress_cases(self) -> None:
        from tap_bench.benchmark.runner import BenchmarkRunner
        from tap_bench.contracts.method import MethodConfig
        from tap_bench.criteria.score import CriteriaProfile
        from tap_bench.io.instance_loader import InstanceLoader

        registry = build_registry()
        runner = BenchmarkRunner(
            registry=registry,
            config=MethodConfig(time_limit_s=60, solver_name="cplex", random_seed=7),
            profile=CriteriaProfile(),
        )

        instances = [
            InstanceLoader.load("data/instances/DataCplex_density=1_p=10_h=7_test_0.json"),
            InstanceLoader.load("data/instances/DataCplex_density=1_p=10_h=15_test_0.json"),
            InstanceLoader.load("data/instances/DataCplex_density=1_p=10_h=21_test_0.json"),
            InstanceLoader.load("data/instances/DataCplex_density=1_p=10_h=30_test_0.json"),
        ]
        records = runner.run(instances, registry.ids())

        observed = {(record.instance_stem, record.method_id): record for record in records}
        expected_exact = {
            ("DataCplex_density=1_p=10_h=7_test_0", "greedy_baseline"): ("feasible", 93),
            ("DataCplex_density=1_p=10_h=7_test_0", "dijkstra_heuristic"): ("feasible", 119),
            ("DataCplex_density=1_p=10_h=7_test_0", "bruteforce_exact"): ("not_applicable", 234),
            ("DataCplex_density=1_p=10_h=7_test_0", "dp_exact_small"): ("not_applicable", 234),
            ("DataCplex_density=1_p=10_h=7_test_0", "milp_compact"): ("infeasible", 234),
            ("DataCplex_density=1_p=10_h=15_test_0", "greedy_baseline"): ("feasible", 136),
            ("DataCplex_density=1_p=10_h=15_test_0", "dijkstra_heuristic"): ("feasible", 278),
            ("DataCplex_density=1_p=10_h=15_test_0", "bruteforce_exact"): ("not_applicable", 420),
            ("DataCplex_density=1_p=10_h=15_test_0", "dp_exact_small"): ("not_applicable", 420),
            ("DataCplex_density=1_p=10_h=15_test_0", "milp_compact"): ("error", 420),
            ("DataCplex_density=1_p=10_h=21_test_0", "greedy_baseline"): ("feasible", 149),
            ("DataCplex_density=1_p=10_h=21_test_0", "dijkstra_heuristic"): ("feasible", 318),
            ("DataCplex_density=1_p=10_h=21_test_0", "bruteforce_exact"): ("not_applicable", 498),
            ("DataCplex_density=1_p=10_h=21_test_0", "dp_exact_small"): ("not_applicable", 498),
            ("DataCplex_density=1_p=10_h=21_test_0", "milp_compact"): ("error", 498),
            ("DataCplex_density=1_p=10_h=30_test_0", "greedy_baseline"): ("feasible", 168),
            ("DataCplex_density=1_p=10_h=30_test_0", "dijkstra_heuristic"): ("feasible", 330),
            ("DataCplex_density=1_p=10_h=30_test_0", "bruteforce_exact"): ("not_applicable", 575),
            ("DataCplex_density=1_p=10_h=30_test_0", "dp_exact_small"): ("not_applicable", 575),
            ("DataCplex_density=1_p=10_h=30_test_0", "milp_compact"): ("error", 575),
        }

        # ACO is stochastic and may improve over the recorded baseline even with a fixed seed.
        # Treat baseline values as worst-acceptable regression bounds.
        expected_aco_max_unassigned = {
            ("DataCplex_density=1_p=10_h=7_test_0", "aco_heuristic"): ("feasible", 209),
            ("DataCplex_density=1_p=10_h=15_test_0", "aco_heuristic"): ("feasible", 388),
            ("DataCplex_density=1_p=10_h=21_test_0", "aco_heuristic"): ("feasible", 461),
            ("DataCplex_density=1_p=10_h=30_test_0", "aco_heuristic"): ("feasible", 538),
        }

        self.assertEqual(len(records), len(expected_exact) + len(expected_aco_max_unassigned))

        for key, (status, unassigned) in expected_exact.items():
            self.assertIn(key, observed)
            record = observed[key]
            self.assertEqual(record.status, status)
            self.assertEqual(record.unassigned, unassigned)

        for key, (status, max_unassigned) in expected_aco_max_unassigned.items():
            self.assertIn(key, observed)
            record = observed[key]
            self.assertEqual(record.status, status)
            self.assertLessEqual(record.unassigned, max_unassigned)


if __name__ == "__main__":
    unittest.main()