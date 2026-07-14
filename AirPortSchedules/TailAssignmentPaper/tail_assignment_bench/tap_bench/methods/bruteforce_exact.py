from __future__ import annotations

import time

from tap_bench.contracts.method import MethodConfig, SchedulerMethod
from tap_bench.contracts.types import ResultStatus
from tap_bench.domain.models import Assignment, ObjectiveBreakdown, SchedulingInstance, Solution, SolutionTiming
from tap_bench.methods.shared import LegacyScheduleOracle, exact_route_search


class BruteForceExactMethod(SchedulerMethod):
    def __init__(self, max_flights: int = 8, max_aircraft: int = 4) -> None:
        self.max_flights = max_flights
        self.max_aircraft = max_aircraft

    @property
    def method_id(self) -> str:
        return "bruteforce_exact"

    def is_applicable(self, instance: SchedulingInstance, config: MethodConfig) -> bool:
        return instance.n_flights <= self.max_flights and instance.n_aircraft <= self.max_aircraft

    def solve(self, instance: SchedulingInstance, config: MethodConfig) -> Solution:
        source_path = instance.metadata.get("source_path")
        if not source_path:
            raise ValueError("Missing source_path metadata for brute-force execution.")

        if not self.is_applicable(instance, config):
            return Solution(
                method_id=self.method_id,
                status=ResultStatus.NOT_APPLICABLE,
                assignment=Assignment(aircraft_to_flights={}, unassigned_flights=[f.id for f in instance.flights]),
                objective=ObjectiveBreakdown(assignment_cost=0.0),
                timing=SolutionTiming(wall_s=0.0),
                diagnostics={"reason": "instance too large for brute-force exact search"},
            )

        t0 = time.perf_counter()
        oracle = LegacyScheduleOracle(source_path)
        result = exact_route_search(oracle, [int(f.id) for f in instance.flights])
        wall = time.perf_counter() - t0

        if not result.feasible:
            return Solution(
                method_id=self.method_id,
                status=ResultStatus.INFEASIBLE,
                assignment=Assignment(aircraft_to_flights={}, unassigned_flights=[f.id for f in instance.flights]),
                objective=ObjectiveBreakdown(assignment_cost=0.0),
                timing=SolutionTiming(wall_s=wall),
                diagnostics={"reason": "no feasible assignment found by brute force"},
            )

        return Solution(
            method_id=self.method_id,
            status=ResultStatus.OPTIMAL,
            assignment=Assignment(aircraft_to_flights=result.routes, unassigned_flights=[]),
            objective=ObjectiveBreakdown(assignment_cost=result.cost),
            timing=SolutionTiming(wall_s=wall),
            metadata={"exact": "true", "method": "brute_force_search"},
        )
