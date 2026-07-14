from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class RouteEvaluation:
    feasible: bool
    cost: float


class LegacyScheduleOracle:
    def __init__(self, data_path: str) -> None:
        from src.model import Scheduler  # type: ignore

        self.scheduler = Scheduler(data_path)
        self.aircraft_ids = [int(a) for a in self.scheduler.aircrafts]
        self.flight_ids = [int(f) for f in self.scheduler.flights.keys()]

    def route_cost(self, aircraft_id: int, flights: Sequence[int]) -> RouteEvaluation:
        result = self.scheduler.get_timeline(aircraft_id, list(flights))
        if result is None:
            return RouteEvaluation(feasible=False, cost=float("inf"))
        return RouteEvaluation(feasible=True, cost=float(result["cost"]))

    def best_append(self, routes: dict[int, List[int]], flight_id: int) -> tuple[int | None, float]:
        best_aircraft: int | None = None
        best_cost = float("inf")
        for aircraft_id in self.aircraft_ids:
            trial = list(routes[aircraft_id]) + [flight_id]
            evaluation = self.route_cost(aircraft_id, trial)
            if evaluation.feasible and evaluation.cost < best_cost:
                best_aircraft = aircraft_id
                best_cost = evaluation.cost
        return best_aircraft, best_cost

    def best_insertion(self, routes: dict[int, List[int]], flight_id: int) -> tuple[int | None, int, float]:
        best_aircraft: int | None = None
        best_pos = 0
        best_cost = float("inf")
        for aircraft_id in self.aircraft_ids:
            route = routes[aircraft_id]
            for pos in range(len(route) + 1):
                trial = list(route[:pos]) + [flight_id] + list(route[pos:])
                evaluation = self.route_cost(aircraft_id, trial)
                if evaluation.feasible and evaluation.cost < best_cost:
                    best_aircraft = aircraft_id
                    best_pos = pos
                    best_cost = evaluation.cost
        return best_aircraft, best_pos, best_cost

    def route_successors(self, current_flight_id: int, remaining_flights: Iterable[int]) -> int:
        current = self.scheduler.flights[current_flight_id]
        current_dest = current["dest"]
        current_arr = float(current["arr"])
        count = 0
        for fid in remaining_flights:
            fl = self.scheduler.flights[fid]
            if fl["orig"] == current_dest and float(fl["dep"]) >= current_arr:
                count += 1
        return count


@dataclass(frozen=True)
class ExhaustiveSearchResult:
    feasible: bool
    cost: float
    routes: dict[int, List[int]]


def exact_route_search(oracle: LegacyScheduleOracle, flight_ids: Sequence[int] | None = None) -> ExhaustiveSearchResult:
    remaining = list(flight_ids if flight_ids is not None else oracle.flight_ids)
    routes = {aircraft_id: [] for aircraft_id in oracle.aircraft_ids}
    best_cost = float("inf")
    best_routes = {aircraft_id: [] for aircraft_id in oracle.aircraft_ids}

    def current_cost() -> float:
        total = 0.0
        for aircraft_id, route in routes.items():
            evaluation = oracle.route_cost(aircraft_id, route)
            if not evaluation.feasible:
                return float("inf")
            total += evaluation.cost
        return total

    def search(remaining_flights: list[int]) -> None:
        nonlocal best_cost, best_routes

        lower_bound = current_cost()
        if lower_bound >= best_cost:
            return

        if not remaining_flights:
            if lower_bound < best_cost:
                best_cost = lower_bound
                best_routes = {aid: list(route) for aid, route in routes.items()}
            return

        for idx, flight_id in enumerate(list(remaining_flights)):
            next_remaining = remaining_flights[:idx] + remaining_flights[idx + 1 :]
            for aircraft_id in oracle.aircraft_ids:
                route = routes[aircraft_id]
                for pos in range(len(route) + 1):
                    trial = route[:pos] + [flight_id] + route[pos:]
                    evaluation = oracle.route_cost(aircraft_id, trial)
                    if not evaluation.feasible:
                        continue
                    previous = list(route)
                    routes[aircraft_id] = trial
                    search(next_remaining)
                    routes[aircraft_id] = previous

    search(remaining)
    return ExhaustiveSearchResult(feasible=best_cost < float("inf"), cost=best_cost, routes=best_routes)
