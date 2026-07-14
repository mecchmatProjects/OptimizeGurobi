from __future__ import annotations

import time
from pathlib import Path

from tap_bench.contracts.method import MethodConfig, SchedulerMethod
from tap_bench.contracts.types import ResultStatus
from tap_bench.domain.models import Assignment, ObjectiveBreakdown, SchedulingInstance, Solution, SolutionTiming


class GreedyBaselineMethodAdapter(SchedulerMethod):
    @property
    def method_id(self) -> str:
        return "greedy_baseline"

    def is_applicable(self, instance: SchedulingInstance, config: MethodConfig) -> bool:
        return True

    def solve(self, instance: SchedulingInstance, config: MethodConfig) -> Solution:
        from src.model import Scheduler  # type: ignore

        data_path = instance.metadata.get("source_path")
        if not data_path:
            raise ValueError("Missing source_path metadata for adapter execution.")

        t0 = time.perf_counter()
        scheduler = Scheduler(data_path)
        aircraft_to_flights, unassigned = scheduler.optimize()
        wall = time.perf_counter() - t0

        total_cost = 0.0
        for aid, fids in aircraft_to_flights.items():
            timeline = scheduler.get_timeline(aid, fids)
            if timeline is None:
                continue
            total_cost += float(timeline.get("cost", 0.0))

        return Solution(
            method_id=self.method_id,
            status=ResultStatus.FEASIBLE,
            assignment=Assignment(
                aircraft_to_flights={int(k): list(v) for k, v in aircraft_to_flights.items()},
                unassigned_flights=list(unassigned),
            ),
            objective=ObjectiveBreakdown(assignment_cost=float(total_cost)),
            timing=SolutionTiming(wall_s=wall),
            metadata={"adapter": "Scheduler", "source": str(Path(data_path).name)},
        )
