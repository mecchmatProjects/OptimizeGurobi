from __future__ import annotations

from enum import Enum


class ResultStatus(str, Enum):
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    TIMEOUT = "timeout"
    ERROR = "error"
    NOT_APPLICABLE = "not_applicable"
