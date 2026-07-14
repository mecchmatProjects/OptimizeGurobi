from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict

from tap_bench.domain.models import SchedulingInstance, Solution


@dataclass(frozen=True)
class MethodConfig:
    time_limit_s: int = 60
    solver_name: str = "cplex"
    random_seed: int = 0
    params: Dict[str, str] = field(default_factory=dict)


class SchedulerMethod(ABC):
    @property
    @abstractmethod
    def method_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_applicable(self, instance: SchedulingInstance, config: MethodConfig) -> bool:
        raise NotImplementedError

    @abstractmethod
    def solve(self, instance: SchedulingInstance, config: MethodConfig) -> Solution:
        raise NotImplementedError


class MethodRegistry:
    def __init__(self) -> None:
        self._methods: Dict[str, SchedulerMethod] = {}

    def register(self, method: SchedulerMethod) -> None:
        self._methods[method.method_id] = method

    def get(self, method_id: str) -> SchedulerMethod:
        if method_id not in self._methods:
            raise KeyError(f"Unknown method: {method_id}")
        return self._methods[method_id]

    def ids(self) -> list[str]:
        return sorted(self._methods.keys())
