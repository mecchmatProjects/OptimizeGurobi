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


class BoundarySuiteTests(unittest.TestCase):
    def test_boundary_suite_runs_all_methods(self) -> None:
        from tap_bench.benchmark.runner import BenchmarkRunner
        from tap_bench.contracts.method import MethodConfig
        from tap_bench.criteria.score import CriteriaProfile
        from tap_bench.io.instance_loader import InstanceLoader

        registry = build_registry()
        runner = BenchmarkRunner(
            registry=registry,
            config=MethodConfig(time_limit_s=45, solver_name="cplex_direct", random_seed=7),
            profile=CriteriaProfile(),
        )

        instances = [
            InstanceLoader.load("data/instances/ABCD_capacity_bottleneck_test.json"),
            InstanceLoader.load("data/instances/ABCD_check_hierarchy_test.json"),
            InstanceLoader.load("data/instances/ABCD_near_threshold_test.json"),
            InstanceLoader.load("data/instances/ABCD_two_b_one_c_test.json"),
        ]
        records = runner.run(instances, registry.ids())

        observed = {(record.instance_stem, record.method_id): record for record in records}
        expected = {
            ("ABCD_capacity_bottleneck_test", "greedy_baseline"): ("feasible", 1),
            ("ABCD_capacity_bottleneck_test", "dijkstra_heuristic"): ("feasible", 1),
            ("ABCD_capacity_bottleneck_test", "aco_heuristic"): ("feasible", 3),
            ("ABCD_capacity_bottleneck_test", "bruteforce_exact"): ("infeasible", 8),
            ("ABCD_capacity_bottleneck_test", "dp_exact_small"): ("infeasible", 8),
            ("ABCD_capacity_bottleneck_test", "milp_compact"): ("optimal", 0),
            ("ABCD_check_hierarchy_test", "greedy_baseline"): ("feasible", 2),
            ("ABCD_check_hierarchy_test", "dijkstra_heuristic"): ("feasible", 2),
            ("ABCD_check_hierarchy_test", "aco_heuristic"): ("feasible", 9),
            ("ABCD_check_hierarchy_test", "bruteforce_exact"): ("not_applicable", 13),
            ("ABCD_check_hierarchy_test", "dp_exact_small"): ("not_applicable", 13),
            ("ABCD_check_hierarchy_test", "milp_compact"): ("optimal", 0),
            ("ABCD_near_threshold_test", "greedy_baseline"): ("feasible", 0),
            ("ABCD_near_threshold_test", "dijkstra_heuristic"): ("feasible", 0),
            ("ABCD_near_threshold_test", "aco_heuristic"): ("feasible", 5),
            ("ABCD_near_threshold_test", "bruteforce_exact"): ("not_applicable", 20),
            ("ABCD_near_threshold_test", "dp_exact_small"): ("not_applicable", 20),
            ("ABCD_near_threshold_test", "milp_compact"): ("optimal", 0),
            ("ABCD_two_b_one_c_test", "greedy_baseline"): ("feasible", 1),
            ("ABCD_two_b_one_c_test", "dijkstra_heuristic"): ("feasible", 1),
            ("ABCD_two_b_one_c_test", "aco_heuristic"): ("feasible", 7),
            ("ABCD_two_b_one_c_test", "bruteforce_exact"): ("not_applicable", 14),
            ("ABCD_two_b_one_c_test", "dp_exact_small"): ("not_applicable", 14),
            ("ABCD_two_b_one_c_test", "milp_compact"): ("infeasible", 14),
        }

        self.assertEqual(len(records), len(expected))
        for key, (status, unassigned) in expected.items():
            self.assertIn(key, observed)
            record = observed[key]
            self.assertEqual(record.status, status)
            self.assertEqual(record.unassigned, unassigned)


if __name__ == "__main__":
    unittest.main()