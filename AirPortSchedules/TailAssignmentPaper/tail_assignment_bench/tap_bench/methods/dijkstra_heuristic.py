from __future__ import annotations

from heapq import heappop, heappush
from typing import List

from tap_bench.contracts.method import MethodConfig, SchedulerMethod
from tap_bench.contracts.types import ResultStatus
from tap_bench.domain.models import Assignment, ObjectiveBreakdown, SchedulingInstance, Solution, SolutionTiming
from tap_bench.methods.shared import LegacyScheduleOracle


class DijkstraSpaceTimeHeuristicMethod(SchedulerMethod):
    def __init__(self, repair_passes: int = 2) -> None:
        self.repair_passes = repair_passes

    @property
    def method_id(self) -> str:
        return "dijkstra_heuristic"

    def is_applicable(self, instance: SchedulingInstance, config: MethodConfig) -> bool:
        return instance.n_flights > 0 and instance.n_aircraft > 0

    def solve(self, instance: SchedulingInstance, config: MethodConfig) -> Solution:
        import time

        source_path = instance.metadata.get("source_path")
        if not source_path:
            raise ValueError("Missing source_path metadata for heuristic execution.")

        t0 = time.perf_counter()
        oracle = LegacyScheduleOracle(source_path)
        routes = {aircraft_id: [] for aircraft_id in oracle.aircraft_ids}
        unassigned = set(oracle.flight_ids)
        assigned = set()

        # Modified Dijkstra-style construction: at each step prefer flights that
        # preserve the largest future reachability (proxy for covering more arcs).
        while unassigned:
            heap: list[tuple[tuple[int, float, float, int], int, int]] = []
            for aircraft_id in oracle.aircraft_ids:
                for flight_id in list(unassigned):
                    trial = list(routes[aircraft_id]) + [flight_id]
                    evaluation = oracle.route_cost(aircraft_id, trial)
                    if not evaluation.feasible:
                        continue
                    reachability = oracle.route_successors(flight_id, unassigned - {flight_id})
                    flight = oracle.scheduler.flights[flight_id]
                    priority = (-reachability, evaluation.cost, float(flight["dep"]), flight_id)
                    heappush(heap, (priority, aircraft_id, flight_id))

            if not heap:
                break

            _, aircraft_id, flight_id = heappop(heap)
            routes[aircraft_id].append(flight_id)
            unassigned.remove(flight_id)
            assigned.add(flight_id)

        self._repair_unassigned(oracle, routes, unassigned)

        total_cost = self._total_cost(oracle, routes)
        wall = time.perf_counter() - t0
        return Solution(
            method_id=self.method_id,
            status=ResultStatus.FEASIBLE if len(unassigned) < len(oracle.flight_ids) else ResultStatus.ERROR,
            assignment=Assignment(aircraft_to_flights=routes, unassigned_flights=sorted(unassigned)),
            objective=ObjectiveBreakdown(assignment_cost=total_cost),
            timing=SolutionTiming(wall_s=wall),
            metadata={"construction": "modified_dijkstra", "repair_passes": str(self.repair_passes)},
        )

    def _repair_unassigned(self, oracle: LegacyScheduleOracle, routes: dict[int, List[int]], unassigned: set[int]) -> None:
        for _ in range(self.repair_passes):
            changed = False
            for flight_id in list(unassigned):
                aircraft_id, pos, _ = oracle.best_insertion(routes, flight_id)
                if aircraft_id is None:
                    continue
                routes[aircraft_id].insert(pos, flight_id)
                unassigned.remove(flight_id)
                changed = True
            if not changed:
                break

    @staticmethod
    def _total_cost(oracle: LegacyScheduleOracle, routes: dict[int, List[int]]) -> float:
        total = 0.0
        for aircraft_id, flights in routes.items():
            evaluation = oracle.route_cost(aircraft_id, flights)
            if evaluation.feasible:
                total += evaluation.cost
        return total
