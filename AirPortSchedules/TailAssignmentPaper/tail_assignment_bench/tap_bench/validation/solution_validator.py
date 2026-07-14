from __future__ import annotations

from tap_bench.domain.models import SchedulingInstance, Solution


class SolutionValidator:
    @staticmethod
    def count_violations(instance: SchedulingInstance, solution: Solution) -> int:
        assigned = []
        for fids in solution.assignment.aircraft_to_flights.values():
            assigned.extend(fids)

        assigned_set = set(assigned)
        expected_set = {f.id for f in instance.flights}

        missing = len(expected_set - assigned_set)
        duplicate = len(assigned) - len(assigned_set)
        inconsistent_unassigned = len(set(solution.assignment.unassigned_flights) - (expected_set - assigned_set))

        return missing + duplicate + inconsistent_unassigned
