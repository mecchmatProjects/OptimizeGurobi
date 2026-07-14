from __future__ import annotations

import itertools
import time

from tap_bench.contracts.method import MethodConfig, SchedulerMethod
from tap_bench.contracts.types import ResultStatus
from tap_bench.domain.models import Assignment, ObjectiveBreakdown, SchedulingInstance, Solution, SolutionTiming
from tap_bench.methods.shared import LegacyScheduleOracle, exact_route_search


class DynamicProgrammingExactSmallMethod(SchedulerMethod):
    def __init__(self, max_flights: int = 12, max_aircraft: int = 4) -> None:
        self.max_flights = max_flights
        self.max_aircraft = max_aircraft

    @property
    def method_id(self) -> str:
        return "dp_exact_small"

    def is_applicable(self, instance: SchedulingInstance, config: MethodConfig) -> bool:
        return instance.n_flights <= self.max_flights and instance.n_aircraft <= self.max_aircraft

    def solve(self, instance: SchedulingInstance, config: MethodConfig) -> Solution:
        if not self.is_applicable(instance, config):
            return Solution(
                method_id=self.method_id,
                status=ResultStatus.NOT_APPLICABLE,
                assignment=Assignment(aircraft_to_flights={}, unassigned_flights=[f.id for f in instance.flights]),
                objective=ObjectiveBreakdown(assignment_cost=0.0),
                timing=SolutionTiming(wall_s=0.0),
                diagnostics={"reason": "instance too large for exact-small DP"},
            )

        t0 = time.perf_counter()
        oracle = LegacyScheduleOracle(instance.metadata.get("source_path", ""))
        result = exact_route_search(oracle, [f.id for f in instance.flights])
        wall = time.perf_counter() - t0
        if not result.feasible:
            return Solution(
                method_id=self.method_id,
                status=ResultStatus.INFEASIBLE,
                assignment=Assignment(aircraft_to_flights={}, unassigned_flights=[f.id for f in instance.flights]),
                objective=ObjectiveBreakdown(assignment_cost=0.0),
                timing=SolutionTiming(wall_s=wall),
                diagnostics={"reason": "no feasible assignment found by exact route search"},
            )

        return Solution(
            method_id=self.method_id,
            status=ResultStatus.OPTIMAL,
            assignment=Assignment(aircraft_to_flights=result.routes, unassigned_flights=[]),
            objective=ObjectiveBreakdown(assignment_cost=result.cost),
            timing=SolutionTiming(wall_s=wall),
            metadata={"exact": "true", "method": "exact_route_search"},
        )
