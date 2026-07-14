from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

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
    MilpCompactMethodAdapter,
)


def _build_registry() -> MethodRegistry:
    registry = MethodRegistry()
    registry.register(GreedyBaselineMethodAdapter())
    registry.register(DijkstraSpaceTimeHeuristicMethod())
    registry.register(AntColonyHeuristicMethod())
    registry.register(BruteForceExactMethod())
    registry.register(MilpCompactMethodAdapter())
    registry.register(DynamicProgrammingExactSmallMethod())
    return registry


def _load_profile(profile_path: str | None) -> CriteriaProfile:
    if not profile_path:
        return CriteriaProfile()
    raw = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    return CriteriaProfile(
        unassigned_penalty=float(raw.get("unassigned_penalty", 100000.0)),
        violation_penalty=float(raw.get("violation_penalty", 1000000.0)),
        runtime_weight=float(raw.get("runtime_weight", 0.0)),
    )


def _load_methods(methods: list[str], methods_config_path: str | None) -> list[str]:
    if not methods_config_path:
        return methods
    raw = json.loads(Path(methods_config_path).read_text(encoding="utf-8"))
    configured = raw.get("methods", [])
    if not isinstance(configured, list) or not all(isinstance(item, str) for item in configured):
        raise ValueError("methods config must contain a JSON array under 'methods'")
    return [method for method in configured if method in methods]


def main() -> None:
    parser = argparse.ArgumentParser(description="tail_assignment_bench runner")
    parser.add_argument("--instances", nargs="+", required=True, help="Instance JSON paths")
    parser.add_argument(
        "--methods",
        nargs="+",
        default=[
            "greedy_baseline",
            "dijkstra_heuristic",
            "aco_heuristic",
            "bruteforce_exact",
            "milp_compact",
            "dp_exact_small",
        ],
        help="Method IDs",
    )
    parser.add_argument("--out", required=True, help="Output CSV")
    parser.add_argument("--legacy-out", default=None, help="Legacy-compatible CSV output")
    parser.add_argument("--profile", default=None, help="Criteria profile JSON")
    parser.add_argument("--methods-config", default=None, help="JSON config with a 'methods' array")
    parser.add_argument(
        "--solver",
        default=os.environ.get("TAP_PYOMO_SOLVER", "cplex_direct"),
        help="MILP solver (default: TAP_PYOMO_SOLVER or cplex_direct)",
    )
    parser.add_argument("--time-limit", type=int, default=60, help="Time limit in seconds")
    args = parser.parse_args()

    registry = _build_registry()
    profile = _load_profile(args.profile)
    config = MethodConfig(time_limit_s=args.time_limit, solver_name=args.solver)

    instances = []
    for p in args.instances:
        inst = InstanceLoader.load(p)
        instances.append(inst)

    method_ids = _load_methods(args.methods, args.methods_config)

    runner = BenchmarkRunner(registry=registry, config=config, profile=profile)
    records = runner.run(instances=instances, method_ids=method_ids)
    runner.write_csv(records, args.out)
    if args.legacy_out:
        runner.write_legacy_csv(records, args.legacy_out)


if __name__ == "__main__":
    main()
