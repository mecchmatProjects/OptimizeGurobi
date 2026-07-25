from __future__ import annotations

import time
from typing import Any

from tap_bench.contracts.method import MethodConfig, SchedulerMethod
from tap_bench.contracts.types import ResultStatus
from tap_bench.domain.models import (
    Assignment,
    ObjectiveBreakdown,
    SchedulingInstance,
    Solution,
    SolutionTiming,
)


def _map_status(status: str) -> ResultStatus:
    s = (status or "").lower()
    if "optimal" in s:
        return ResultStatus.OPTIMAL
    if "infeasible" in s:
        return ResultStatus.INFEASIBLE
    if "time" in s or "max" in s:
        return ResultStatus.TIMEOUT
    if "feasible" in s:
        return ResultStatus.FEASIBLE
    return ResultStatus.ERROR


class MilpCompactMethodAdapter(SchedulerMethod):
    @property
    def method_id(self) -> str:
        return "milp_compact"

    def is_applicable(self, instance: SchedulingInstance, config: MethodConfig) -> bool:
        return True

    def solve(self, instance: SchedulingInstance, config: MethodConfig) -> Solution:
        from src.model import LegacyEndpointSplitMILPScheduler  # type: ignore

        data_path = instance.metadata.get("source_path")
        if not data_path:
            raise ValueError("Missing source_path metadata for adapter execution.")

        t0 = time.perf_counter()
        m = LegacyEndpointSplitMILPScheduler(data_path)
        m.build_model(use_maintenance=True)
        fallback_order = ["cplex_direct", "cplex_persistent", "cplex", "gurobi", "glpk", "cbc"]
        # Keep deterministic fallback order; if caller passes one of these solvers,
        # place it first while preserving the remaining fallback sequence.
        if config.solver_name in fallback_order:
            solver_order = [config.solver_name] + [s for s in fallback_order if s != config.solver_name]
        else:
            solver_order = fallback_order

        summary: dict[str, Any] | None = None
        selected_solver = ""
        solver_failures: dict[str, str] = {}
        for solver_name in solver_order:
            try:
                summary = m.solve(
                    solver_name=solver_name,
                    tee=False,
                    time_limit=config.time_limit_s,
                )
                selected_solver = solver_name
                break
            except Exception as exc:
                solver_failures[solver_name] = str(exc)

        if summary is None:
            wall = time.perf_counter() - t0
            flight_ids = getattr(m, "flights", getattr(m, "flight_ids", []))
            return Solution(
                method_id=self.method_id,
                status=ResultStatus.ERROR,
                assignment=Assignment(
                    aircraft_to_flights={},
                    unassigned_flights=[int(i) for i in flight_ids],
                ),
                objective=ObjectiveBreakdown(assignment_cost=0.0),
                timing=SolutionTiming(wall_s=wall),
                diagnostics={
                    "solver_error": "All fallback solvers failed",
                    "solver_attempt_order": ",".join(solver_order),
                    "solver_failures": " | ".join(
                        f"{name}: {msg}" for name, msg in solver_failures.items()
                    ),
                },
                metadata={
                    "adapter": "LegacyEndpointSplitMILPScheduler",
                    "solver": "",
                    "solver_attempt_order": ",".join(solver_order),
                    "num_vars": str(getattr(m, "_n_vars", "")),
                    "num_constraints": str(getattr(m, "_n_cons", "")),
                    "returncode": "1",
                },
            )
        wall = time.perf_counter() - t0

        aircraft_ids = getattr(m, "aircrafts", getattr(m, "aircraft_ids", []))
        flight_ids = getattr(m, "flights", getattr(m, "flight_ids", []))
        assignments = {int(a): [] for a in aircraft_ids}
        unassigned: list[int] = []

        try:
            x: Any = m.model.x  # type: ignore[attr-defined]
            for i in flight_ids:
                assigned = False
                for j in aircraft_ids:
                    try:
                        x_ij: Any = x[i, j]
                        x_val = x_ij.value
                    except Exception:
                        x_val = None
                    if x_val is not None and float(x_val) >= 0.5:
                        assignments[int(j)].append(int(i))
                        assigned = True
                if not assigned:
                    unassigned.append(int(i))
        except Exception:
            unassigned = [int(i) for i in flight_ids]

        objective = float(summary.get("obj") or summary.get("objective") or 0.0)
        gap_pct = summary.get("gap")
        cpu_s = summary.get("cpu")
        status = _map_status(str(summary.get("status", "")))

        return Solution(
            method_id=self.method_id,
            status=status,
            assignment=Assignment(aircraft_to_flights=assignments, unassigned_flights=unassigned),
            objective=ObjectiveBreakdown(assignment_cost=objective),
            timing=SolutionTiming(wall_s=wall, cpu_s=float(cpu_s) if cpu_s is not None else None),
            gap_pct=float(gap_pct) if gap_pct is not None else None,
            metadata={
                "adapter": "LegacyEndpointSplitMILPScheduler",
                "solver": selected_solver,
                "solver_attempt_order": ",".join(solver_order),
                "num_vars": str(summary.get("vars", "")),
                "num_constraints": str(summary.get("constraints", "")),
                "returncode": "0",
            },
        )
