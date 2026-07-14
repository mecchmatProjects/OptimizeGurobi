from __future__ import annotations

from dataclasses import dataclass

from tap_bench.domain.models import Solution


@dataclass(frozen=True)
class CriteriaProfile:
    unassigned_penalty: float = 100000.0
    violation_penalty: float = 1000000.0
    runtime_weight: float = 0.0


class ScoreEngine:
    @staticmethod
    def weighted_score(solution: Solution, profile: CriteriaProfile) -> float:
        return (
            solution.objective.assignment_cost
            + profile.unassigned_penalty * len(solution.assignment.unassigned_flights)
            + profile.violation_penalty * float(solution.diagnostics.get("violations", "0"))
            + profile.runtime_weight * solution.timing.wall_s
        )
