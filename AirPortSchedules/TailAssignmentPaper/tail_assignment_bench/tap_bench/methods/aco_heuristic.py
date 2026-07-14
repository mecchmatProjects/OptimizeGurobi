from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import List

from tap_bench.contracts.method import MethodConfig, SchedulerMethod
from tap_bench.contracts.types import ResultStatus
from tap_bench.domain.models import Assignment, ObjectiveBreakdown, SchedulingInstance, Solution, SolutionTiming
from tap_bench.methods.shared import LegacyScheduleOracle


@dataclass(frozen=True)
class _AntSolution:
    routes: dict[int, List[int]]
    unassigned: set[int]
    cost: float


class AntColonyHeuristicMethod(SchedulerMethod):
    def __init__(
        self,
        iterations: int = 20,
        ants: int = 8,
        alpha: float = 0.18,
        beta: float = 1.1,
        exploration: float = 0.18,
    ) -> None:
        self.iterations = iterations
        self.ants = ants
        self.alpha = alpha
        self.beta = beta
        self.exploration = exploration

    @property
    def method_id(self) -> str:
        return "aco_heuristic"

    def is_applicable(self, instance: SchedulingInstance, config: MethodConfig) -> bool:
        return instance.n_flights > 0 and instance.n_aircraft > 0

    def solve(self, instance: SchedulingInstance, config: MethodConfig) -> Solution:
        source_path = instance.metadata.get("source_path")
        if not source_path:
            raise ValueError("Missing source_path metadata for heuristic execution.")

        rng = random.Random(config.random_seed)
        t0 = time.perf_counter()
        oracle = LegacyScheduleOracle(source_path)

        pheromone: dict[tuple[int, int], float] = {}
        for fid in oracle.flight_ids:
            for fid2 in oracle.flight_ids:
                if fid != fid2:
                    pheromone[(fid, fid2)] = 1.0

        best = self._construct_solution(oracle, pheromone, rng)
        best_cost = best.cost

        for _ in range(self.iterations):
            ants = [self._construct_solution(oracle, pheromone, rng) for _ in range(self.ants)]
            candidate = min(ants, key=lambda s: s.cost)
            if candidate.cost < best_cost:
                best = candidate
                best_cost = candidate.cost
            self._evaporate(pheromone)
            self._reinforce(pheromone, best.routes)

        wall = time.perf_counter() - t0
        return Solution(
            method_id=self.method_id,
            status=ResultStatus.FEASIBLE if best_cost < float("inf") else ResultStatus.ERROR,
            assignment=Assignment(aircraft_to_flights=best.routes, unassigned_flights=sorted(best.unassigned)),
            objective=ObjectiveBreakdown(assignment_cost=best_cost),
            timing=SolutionTiming(wall_s=wall),
            metadata={
                "construction": "aco",
                "iterations": str(self.iterations),
                "ants": str(self.ants),
                "exploration": str(self.exploration),
            },
        )

    def _construct_solution(
        self,
        oracle: LegacyScheduleOracle,
        pheromone: dict[tuple[int, int], float],
        rng: random.Random,
    ) -> _AntSolution:
        routes = {aircraft_id: [] for aircraft_id in oracle.aircraft_ids}
        unassigned = set(oracle.flight_ids)

        while unassigned:
            moves = []
            for aircraft_id in oracle.aircraft_ids:
                for flight_id in list(unassigned):
                    trial = list(routes[aircraft_id]) + [flight_id]
                    evaluation = oracle.route_cost(aircraft_id, trial)
                    if not evaluation.feasible:
                        continue
                    heur = 1.0
                    last_flight = routes[aircraft_id][-1] if routes[aircraft_id] else None
                    tau = pheromone.get((last_flight, flight_id), 1.0) if last_flight is not None else 1.0
                    moves.append((tau, aircraft_id, flight_id, evaluation.cost, heur))

            if not moves:
                break

            weighted_moves = self._rank_weight_moves(moves)
            aircraft_id, flight_id, _ = self._sample_move(weighted_moves, rng)
            routes[aircraft_id].append(flight_id)
            unassigned.remove(flight_id)

        cost = 0.0
        for aircraft_id, flights in routes.items():
            evaluation = oracle.route_cost(aircraft_id, flights)
            if evaluation.feasible:
                cost += evaluation.cost
            else:
                cost = float("inf")
                break
        return _AntSolution(routes=routes, unassigned=unassigned, cost=cost)

    def _evaporate(self, pheromone: dict[tuple[int, int], float]) -> None:
        for key in list(pheromone.keys()):
            pheromone[key] = max(0.05, (1.0 - self.alpha) * pheromone[key])

    def _reinforce(self, pheromone: dict[tuple[int, int], float], routes: dict[int, List[int]]) -> None:
        for flights in routes.values():
            for left, right in zip(flights, flights[1:]):
                pheromone[(left, right)] = pheromone.get((left, right), 1.0) + self.alpha

    def _rank_weight_moves(self, moves: list[tuple[float, int, int, float, float]]) -> list[tuple[float, int, int, float]]:
        ordered = sorted(moves, key=lambda item: (item[3], item[1], item[2]))
        scored: list[tuple[float, int, int, float]] = []
        for rank, (tau, aircraft_id, flight_id, cost, _) in enumerate(ordered, start=1):
            desirability = max(1e-9, tau) * ((1.0 / rank) ** self.beta)
            scored.append((desirability, aircraft_id, flight_id, cost))
        return scored

    def _sample_move(
        self,
        moves: list[tuple[float, int, int, float]],
        rng: random.Random,
    ) -> tuple[int, int, float]:
        if rng.random() < self.exploration:
            _, aircraft_id, flight_id, cost = rng.choice(moves)
            return aircraft_id, flight_id, cost

        total_weight = sum(weight for weight, _, _, _ in moves)
        pick = rng.random() * total_weight
        cumulative = 0.0
        chosen = moves[-1]
        for move in moves:
            cumulative += move[0]
            if cumulative >= pick:
                chosen = move
                break
        _, aircraft_id, flight_id, cost = chosen
        return aircraft_id, flight_id, cost
