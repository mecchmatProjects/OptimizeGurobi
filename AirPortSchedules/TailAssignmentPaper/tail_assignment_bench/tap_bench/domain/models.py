from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from tap_bench.contracts.types import ResultStatus


@dataclass(frozen=True)
class Flight:
    id: int
    origin: str
    destination: str
    dep_min: float
    arr_min: float

    def duration_min(self) -> float:
        return self.arr_min - self.dep_min


@dataclass(frozen=True)
class Aircraft:
    id: int
    initial_airport: str
    init_a_min: float
    init_b_min: float
    init_c_days: float
    init_d_days: float


@dataclass(frozen=True)
class StationCapacity:
    by_airport: Dict[str, int]


@dataclass(frozen=True)
class SchedulingInstance:
    stem: str
    flights: List[Flight]
    aircraft: List[Aircraft]
    station_capacity: StationCapacity
    maintenance_thresholds: Dict[str, float]
    maintenance_durations: Dict[str, float]
    cost_matrix: List[List[float]]
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def n_flights(self) -> int:
        return len(self.flights)

    @property
    def n_aircraft(self) -> int:
        return len(self.aircraft)


@dataclass(frozen=True)
class Assignment:
    aircraft_to_flights: Dict[int, List[int]]
    unassigned_flights: List[int]


@dataclass(frozen=True)
class ObjectiveBreakdown:
    assignment_cost: float
    unassigned_penalty: float = 0.0
    violation_penalty: float = 0.0

    @property
    def total(self) -> float:
        return self.assignment_cost + self.unassigned_penalty + self.violation_penalty


@dataclass(frozen=True)
class SolutionTiming:
    wall_s: float
    cpu_s: Optional[float] = None


@dataclass(frozen=True)
class Solution:
    method_id: str
    status: ResultStatus
    assignment: Assignment
    objective: ObjectiveBreakdown
    timing: SolutionTiming
    gap_pct: Optional[float] = None
    diagnostics: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)
