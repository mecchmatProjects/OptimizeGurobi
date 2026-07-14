from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from tap_bench.contracts.method import MethodConfig, MethodRegistry
from tap_bench.criteria.score import CriteriaProfile, ScoreEngine
from tap_bench.domain.models import SchedulingInstance, Solution
from tap_bench.validation.solution_validator import SolutionValidator


@dataclass(frozen=True)
class RunRecord:
    method_id: str
    instance_stem: str
    n_flights: int
    assigned: int
    status: str
    objective: float
    score: float
    unassigned: int
    gap_pct: str
    wall_s: float
    cpu_s: str
    violations: int
    solver: str
    solver_attempt_order: str
    num_vars: str
    num_constraints: str
    returncode: str


class BenchmarkRunner:
    def __init__(
        self,
        registry: MethodRegistry,
        config: MethodConfig,
        profile: CriteriaProfile,
    ) -> None:
        self.registry = registry
        self.config = config
        self.profile = profile

    def run(self, instances: Iterable[SchedulingInstance], method_ids: List[str]) -> List[RunRecord]:
        records: List[RunRecord] = []
        for instance in instances:
            for method_id in method_ids:
                method = self.registry.get(method_id)
                solution: Solution = method.solve(instance, self.config)
                violations = SolutionValidator.count_violations(instance, solution)
                score = ScoreEngine.weighted_score(solution, self.profile)
                records.append(
                    RunRecord(
                        method_id=method_id,
                        instance_stem=instance.stem,
                        n_flights=instance.n_flights,
                        assigned=instance.n_flights - len(solution.assignment.unassigned_flights),
                        status=solution.status.value,
                        objective=solution.objective.total,
                        score=score,
                        unassigned=len(solution.assignment.unassigned_flights),
                        gap_pct="" if solution.gap_pct is None else f"{solution.gap_pct:.6f}",
                        wall_s=solution.timing.wall_s,
                        cpu_s="" if solution.timing.cpu_s is None else f"{solution.timing.cpu_s:.6f}",
                        violations=violations,
                        solver=solution.metadata.get("solver", ""),
                        solver_attempt_order=solution.metadata.get("solver_attempt_order", ""),
                        num_vars=solution.metadata.get("num_vars", ""),
                        num_constraints=solution.metadata.get("num_constraints", ""),
                        returncode=solution.metadata.get("returncode", "0"),
                    )
                )
        return records

    @staticmethod
    def write_csv(records: List[RunRecord], out_csv: str) -> None:
        Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "stem",
                    "method",
                    "status",
                    "objective",
                    "score",
                    "flights",
                    "assigned",
                    "unassigned",
                    "gap_pct",
                    "wall_s",
                    "cpu_s",
                    "violations",
                    "solver",
                    "solver_attempt_order",
                    "num_vars",
                    "num_constraints",
                    "returncode",
                ]
            )
            for r in records:
                w.writerow(
                    [
                        r.instance_stem,
                        r.method_id,
                        r.status,
                        f"{r.objective:.6f}",
                        f"{r.score:.6f}",
                        r.n_flights,
                        r.assigned,
                        r.unassigned,
                        r.gap_pct,
                        f"{r.wall_s:.6f}",
                        r.cpu_s,
                        r.violations,
                        r.solver,
                        r.solver_attempt_order,
                        r.num_vars,
                        r.num_constraints,
                        r.returncode,
                    ]
                )

    @staticmethod
    def write_legacy_csv(records: List[RunRecord], out_csv: str) -> None:
        Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "stem",
                    "mode",
                    "flights",
                    "assigned",
                    "unassigned",
                    "status",
                    "objective",
                    "gap_pct",
                    "cpu_s",
                    "wall_s",
                    "num_vars",
                    "num_constraints",
                    "returncode",
                ]
            )
            for r in records:
                mode = "milp" if "milp" in r.method_id else "heuristic"
                w.writerow(
                    [
                        r.instance_stem,
                        mode,
                        r.n_flights,
                        r.assigned,
                        r.unassigned,
                        r.status,
                        f"{r.objective:.6f}",
                        r.gap_pct,
                        r.cpu_s,
                        f"{r.wall_s:.6f}",
                        r.num_vars,
                        r.num_constraints,
                        r.returncode,
                    ]
                )
