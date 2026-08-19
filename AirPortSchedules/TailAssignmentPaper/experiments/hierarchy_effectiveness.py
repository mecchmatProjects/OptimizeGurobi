"""Per-check-type computational proof for the full A/B/C/D hierarchy model.

For each check type in isolation (A, B, C, D) and the full mixed hierarchy,
solves the legacy endpoint-split MILP (``src/model.py``) with the full,
unrestricted CPLEX-for-AMPL build at
``F:/Progs/IBM.ILOG.CPLEX.for.AMPL.v12.6-EAT`` (the CPLEX copy already on
PATH is a size-restricted Community/Preview edition capped at 1000
variables/constraints and cannot solve any instance here), then
independently re-verifies the returned solution by replaying its maintenance
counters from scratch: hour-triggered checks (A, B) via the exact-state
recursion of ``experiments/c13_loophole_validation.py``; calendar-triggered
checks (C, D) via a day-gap recursion of the same shape. A solution is
"validated_ok" only if the independent replay finds zero threshold
violations, regardless of what the model itself reports.

Run:  python experiments/hierarchy_effectiveness.py
"""

import csv
import sys
import time
from pathlib import Path

from pyomo.environ import value as pyo_value

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model import LegacyEndpointSplitMILPScheduler  # noqa: E402

INSTANCES = {
    "A": ROOT / "data" / "instances" / "ABCD_near_threshold_test.json",
    "B": ROOT / "data" / "instances" / "ABCD_near_threshold_test.json",
    "C": ROOT / "data" / "instances" / "ABCD_near_threshold_test.json",
    "D": ROOT / "data" / "instances" / "ABCD_near_threshold_test.json",
    "ABCD": ROOT / "data" / "instances" / "ABCD_check_hierarchy_test.json",
}
SOLVER = "cplexamp"
SOLVER_EXECUTABLE = r"F:\Progs\IBM.ILOG.CPLEX.for.AMPL.v12.6-EAT\CPLEXamp.exe"
TIME_LIMIT = 300


def replay_hour_check(sched, aircraft, check):
    """Recompute h_jd for an hour-triggered check (A/B) from solved x/mega.

    Returns a list of (day, h_value, preexisting_overdue) tuples where
    ``preexisting_overdue`` flags violations caused entirely by an initial
    condition that already exceeds the threshold (Phi_j0 > T_max), which is
    a data precondition violation rather than a legacy-vs-exact-state gap.
    """
    days = sorted(sched.days)
    m = sched.model
    t_max = sched.check_hrs[check] * 60.0
    prior_hrs = sched.init_check_hrs[check].get(aircraft, 0.0) * 60.0
    preexisting_overdue = prior_hrs > t_max + 1e-6
    h_prev = prior_hrs
    violations = []
    for d in days:
        v_d = sum(
            sched.flight_data[i]["duration"] * round(pyo_value(m.x[i, aircraft]))
            for i in sched._f_dep_between_days(d - 1, d)
            if sched._x_has_arc(i, aircraft)
        )
        checked_prev_day = round(pyo_value(m.mega[aircraft, d - 1, check])) if d - 1 in days else 0
        h_d = v_d if checked_prev_day else h_prev + v_d
        if h_d > t_max + 1e-6:
            violations.append((d, h_d, preexisting_overdue))
        h_prev = h_d
    return violations


def replay_day_check(sched, aircraft, check):
    """Recompute the calendar-day gap for a day-triggered check (C/D)."""
    days = sorted(sched.days)
    m = sched.model
    d_max = sched.check_days[check]
    gap = sched.init_check_hrs[check].get(aircraft, 0.0) / 24.0
    preexisting_overdue = gap > d_max + 1e-6
    violations = []
    for d in days:
        gap += 1
        if gap > d_max + 1e-6:
            violations.append((d, gap, preexisting_overdue))
        if round(pyo_value(m.mega[aircraft, d, check])) == 1:
            gap = 0.0
    return violations


def validate_solution(sched, checks):
    """Independently re-verify every aircraft/check pair; return violations."""
    all_violations = {}
    for check in checks:
        if sched.check_days[check] is None:
            replay = replay_hour_check
        else:
            replay = replay_day_check
        for aircraft in sched.aircraft_ids:
            violations = replay(sched, aircraft, check)
            if violations:
                all_violations[(aircraft, check)] = violations
    return all_violations


def run_one(check_group, instance_path):
    checks = list(check_group) if check_group != "ABCD" else ["A", "B", "C", "D"]
    row = {
        "check_type": check_group,
        "instance": instance_path.name,
        "status": "",
        "objective": "",
        "vars": "",
        "constraints": "",
        "wall_s": "",
        "validated_ok": "",
        "n_violations": "",
        "n_genuine_violations": "",
        "violation_detail": "",
        "error": "",
    }
    try:
        sched = LegacyEndpointSplitMILPScheduler(str(instance_path), enabled_checks=checks)
        sched.build_model()
        n_vars = len(list(sched.model.component_data_objects(ctype=type(sched.model.x))))
        started = time.perf_counter()
        summary = sched.solve(solver_name=SOLVER, time_limit=TIME_LIMIT, executable=SOLVER_EXECUTABLE)
        wall = time.perf_counter() - started
        row.update({
            "status": summary["status"],
            "objective": summary.get("obj"),
            "vars": summary.get("n_vars"),
            "constraints": summary.get("n_cons"),
            "wall_s": round(wall, 3),
        })
        if summary["status"] == "optimal":
            violations = validate_solution(sched, checks)
            genuine = {
                k: v for k, v in violations.items()
                if any(not preexisting for (_, __, preexisting) in v)
            }
            row["validated_ok"] = len(violations) == 0
            row["n_violations"] = len(violations)
            row["n_genuine_violations"] = len(genuine)
            row["violation_detail"] = "; ".join(
                f"aircraft{aid}-{check}:{vs}" for (aid, check), vs in violations.items()
            )
        else:
            row["validated_ok"] = ""
    except Exception as error:  # noqa: BLE001 - report and continue
        row["status"] = "ERROR"
        row["error"] = f"{type(error).__name__}: {error}"
    return row


def main():
    rows = [run_one(check_group, path) for check_group, path in INSTANCES.items()]
    out_path = ROOT / "results" / "tables" / "hierarchy_effectiveness.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(row)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
