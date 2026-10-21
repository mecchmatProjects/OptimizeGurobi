"""Row-level diagnostics for conditional C13 and opening-hour coverage.

Builds the real ``LegacyEndpointSplitMILPScheduler`` model (the exact
production code in ``src/model.py``) on ``data/instances/c13_loophole_test.json``,
fixes flight-assignment and check-indicator variables to two adversarial
points from ``paper/sections/04_maintenance_model.tex``:

  * BOTH endpoints checked (days 1 and 4): Lemma ``lem:c13_split_limit`` --
    the split formulation is vacuous here (both rows relax), while the
    original Khaled et al. paper form is exactly tight.
    * ONE endpoint checked (day 4 only): original C13 is inactive by design.
        This scenario tests whether the separate opening-hour companion protects
        pre-check exposure; it is not a defect in C13's conditional deactivation.

The patterns are evaluated against actual built C13 and C13b rows. The
both-endpoints pattern is a counterexample to the split. The one-endpoint
pattern checks opening protection when original C13 is intentionally inactive.
The exact-state recursion is evaluated on the same assignments.

Run:  python experiments/c13_loophole_validation.py
"""

import csv
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from pyomo.environ import value as pyo_value

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model import LegacyEndpointSplitMILPScheduler
from src.validate_maintenance import validate_solved_model

INSTANCE = ROOT / "data" / "instances" / "c13_loophole_test.json"
AIRCRAFT = 0
CHECK = "A"
WINDOW = (1, 4)


def build_model(mega_on_days, use_paper_c13=False, instance=INSTANCE):
    """Build the legacy model and fix variables to the given check pattern."""
    sched = LegacyEndpointSplitMILPScheduler(str(instance), enabled_checks=[CHECK])
    sched.build_model(use_paper_c13=use_paper_c13)
    m = sched.model

    for (i, j) in m.X:
        m.x[i, j].set_value(1 if j == AIRCRAFT else 0)
    for variable in m.z.values():
        variable.set_value(0)
    for variable in m.y.values():
        variable.set_value(0)
    for (j, d, c) in m.mega:
        m.mega[j, d, c].set_value(1 if (j == AIRCRAFT and d in mega_on_days) else 0)
    for day in mega_on_days:
        triggers = [
            flight for flight in m.F
            if sched.flight_data[flight]["day_arrival"] == day
            and sched.flight_data[flight]["destination"] in sched.maint_airports
        ]
        if not triggers:
            raise ValueError(f"No maintenance trigger flight exists on day {day}")
        trigger = max(triggers, key=lambda flight: sched.flight_data[flight]["arrivalTime"])
        m.y[AIRCRAFT, day, CHECK].set_value(1)
        m.z[trigger, AIRCRAFT, day, CHECK].set_value(1)

    return sched, m


def count_violations(m):
    """Check satisfaction of every real ``m.c13`` row (RHS carries variables,
    so Pyomo folds it into the constraint body). Returns (n_checked, n_violated)."""
    checked, violated = 0, 0
    for idx in m.c13:
        con = m.c13[idx]
        body_val = pyo_value(con.body)
        lb = pyo_value(con.lower) if con.lower is not None else None
        ub = pyo_value(con.upper) if con.upper is not None else None
        checked += 1
        if (lb is not None and body_val < lb - 1e-6) or (
            ub is not None and body_val > ub + 1e-6
        ):
            violated += 1
    return checked, violated


def count_violations_on(family):
    checked, violated = 0, 0
    for con in family.values():
        body = pyo_value(con.body)
        lower = pyo_value(con.lower) if con.lower is not None else None
        upper = pyo_value(con.upper) if con.upper is not None else None
        checked += 1
        if (lower is not None and body < lower - 1e-6) or (
            upper is not None and body > upper + 1e-6
        ):
            violated += 1
    return checked, violated


def exact_state_recursion(sched, mega_on_days):
    """Independently recompute h_{jd} per eq. c13_state_lower..bound."""
    days = sorted(sched.days)
    t_max = sched.check_hrs[CHECK] * 60.0  # minutes
    h = {0: 0.0}
    for d in days:
        v_d = sum(
            sched.flight_data[i]["duration"]
            for i in sched._f_dep_between_days(d - 1, d)
        )
        y_d_minus_1 = 1 if (d - 1) in mega_on_days else 0
        h[d] = v_d if y_d_minus_1 else h[d - 1] + v_d
    violations = {d: h[d] for d in days if h[d] > t_max + 1e-9}
    return h, t_max, violations


def run_scenario(label, mega_on_days):
    d, d_ = WINDOW
    print(f"\n{'=' * 70}\nScenario: {label}  (checks on days {sorted(mega_on_days)})\n{'=' * 70}")

    temporary_directory = None
    scenario_instance = INSTANCE
    transformed_input = None
    if mega_on_days == {4}:
        data = json.loads(INSTANCE.read_text(encoding="utf-8"))
        data["Flights"][1][4] = 2040.0  # 590 minutes on day 2
        data["Flights"][2][4] = 4350.0  # 20 minutes on day 4; total is 610
        transformed_input = json.dumps(data, sort_keys=True).encode("utf-8")
        temporary_directory = tempfile.TemporaryDirectory()
        scenario_instance = Path(temporary_directory.name) / "opening_gap.json"
        scenario_instance.write_text(json.dumps(data), encoding="utf-8")

    sched, m = build_model(mega_on_days, instance=scenario_instance)
    t_sum = sum(
        sched.flight_data[i]["duration"]
        for i in sched._f_dep_between_days(d, d_)
    )
    t_max = sched.check_hrs[CHECK] * 60.0
    print(f"Window ({d}, {d_}]: real flying time = {t_sum:.0f} min, T_max = {t_max:.0f} min "
          f"-> physically {'VIOLATES' if t_sum > t_max else 'within'} the limit")

    checked, violated = count_violations(m)
    split_satisfied = violated == 0
    print(f"Split C13: {checked} rows, {violated} violated, {checked - violated} satisfied.")
    c13b_checked, c13b_violated = count_violations_on(m.c13b)
    print(f"Split C13b: {c13b_checked} rows, {c13b_violated} violated.")

    _paper_sched, paper_m = build_model(
        mega_on_days, use_paper_c13=True, instance=scenario_instance
    )
    paper_checked, paper_violated = count_violations(paper_m)
    paper_satisfied = paper_violated == 0
    print(f"Paper C13: {paper_checked} rows, {paper_violated} violated, "
          f"{paper_checked - paper_violated} satisfied.")
    paper_c13b_checked, paper_c13b_violated = count_violations_on(paper_m.c13b)
    print(f"Paper C13b: {paper_c13b_checked} rows, {paper_c13b_violated} violated.")

    h, _, violations = exact_state_recursion(sched, mega_on_days)
    print("Exact-state h_jd: " + ", ".join(f"h[{k}]={v:.0f}" for k, v in sorted(h.items())))

    split_missed_it = split_satisfied and t_sum > t_max
    paper_row_inactive = not ({1, 4} <= mega_on_days)
    opening_gap = paper_satisfied and paper_c13b_violated == 0 and bool(violations)
    replay_violations = validate_solved_model(sched)
    print(
        f"-> split {'misses' if split_missed_it else 'does not miss'} the interval; "
        f"paper C13 is {'inactive by design' if paper_row_inactive else 'active'}; "
        f"opening-family gap={'yes' if opening_gap else 'no'}; "
        f"independent replay violations={len(replay_violations)}; "
        f"exact-state {'flags' if violations else 'does not flag'} the schedule."
    )

    result = {
        "instance": INSTANCE.name,
        "scenario": label,
        "window_start_day": d,
        "window_end_day": d_,
        "real_flight_minutes": t_sum,
        "T_max_minutes": t_max,
        "paper_c13_rows_satisfied": paper_satisfied,
        "paper_c13b_rows_violated": paper_c13b_violated,
        "legacy_split_c13b_rows_violated": c13b_violated,
        "legacy_split_rows_satisfied": split_satisfied,
        "exact_state_h_at_end_day": h[d_],
        "exact_state_violation": d_ in violations,
        "split_missed_it": split_missed_it,
        "paper_c13_inactive_by_design": paper_row_inactive,
        "opening_gap_detected": opening_gap,
        "independent_replay_violations": len(replay_violations),
        "input_sha256": hashlib.sha256(
            transformed_input if transformed_input is not None else INSTANCE.read_bytes()
        ).hexdigest(),
    }
    if temporary_directory is not None:
        temporary_directory.cleanup()
    return result


def main():
    both_endpoints = run_scenario("both endpoints checked (lem:c13_split_limit)", {1, 4})
    one_endpoint = run_scenario("ending check; opening interval (lem:c13_opening_gap)", {4})

    out_path = ROOT / "results" / "tables" / "c13_conditional_rows_20261021.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(both_endpoints.keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(both_endpoints)
        writer.writerow(one_endpoint)
    print(f"\nWrote {out_path}")

    assert both_endpoints["split_missed_it"], "Expected split to miss the both-endpoints-checked violation"
    assert not one_endpoint["split_missed_it"], "Expected split to enforce the one-endpoint interval"
    assert both_endpoints["exact_state_violation"] and one_endpoint["exact_state_violation"]
    assert one_endpoint["paper_c13_inactive_by_design"]
    assert one_endpoint["opening_gap_detected"]
    assert one_endpoint["independent_replay_violations"] > 0
    print(
        "\nOK: split misses the both-endpoints interval; one-endpoint C13 relaxation is intentional, "
        "and the legacy opening rows miss pre-check exposure."
    )


if __name__ == "__main__":
    main()

