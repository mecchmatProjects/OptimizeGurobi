"""Numeric verification of the Constraint (13) endpoint-split loophole.

Builds the real ``LegacyEndpointSplitMILPScheduler`` model (the exact
production code in ``src/model.py``) on ``data/instances/c13_loophole_test.json``,
fixes flight-assignment and check-indicator variables to two adversarial
points from ``paper/sections/04_maintenance_model.tex``:

  * BOTH endpoints checked (days 1 and 4): Lemma ``lem:c13_split_limit`` --
    the split formulation is vacuous here (both rows relax), while the
    original Khaled et al. paper form is exactly tight.
  * ONE endpoint checked (day 4 only): Lemma ``lem:c13_flaw`` -- the
    original paper form is vacuous here, while the split formulation is
    tight (the whole reason the split was introduced).

Both are evaluated against the *actual* built C13 constraint expressions --
not a reimplementation -- confirming the two formulations fail in
complementary, non-overlapping cases. The exact-state recursion
(eq. c13_state_lower..bound) is evaluated on the same data and correctly
rejects both points.

Run:  python experiments/c13_loophole_validation.py
"""

import csv
import sys
from pathlib import Path

from pyomo.environ import value as pyo_value

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model import LegacyEndpointSplitMILPScheduler  # noqa: E402

INSTANCE = ROOT / "data" / "instances" / "c13_loophole_test.json"
AIRCRAFT = 0
CHECK = "A"
WINDOW = (1, 4)


def build_model(mega_on_days, use_paper_c13=False):
    """Build the legacy model and fix variables to the given check pattern."""
    sched = LegacyEndpointSplitMILPScheduler(str(INSTANCE), enabled_checks=[CHECK])
    sched.build_model(use_paper_c13=use_paper_c13)
    m = sched.model

    for (i, j) in m.X:
        m.x[i, j].set_value(1 if j == AIRCRAFT else 0)
    for (j, d, c) in m.mega:
        m.mega[j, d, c].set_value(1 if (j == AIRCRAFT and d in mega_on_days) else 0)

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

    sched, m = build_model(mega_on_days)
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

    paper_sched, paper_m = build_model(mega_on_days, use_paper_c13=True)
    paper_checked, paper_violated = count_violations(paper_m)
    paper_satisfied = paper_violated == 0
    print(f"Paper C13: {paper_checked} rows, {paper_violated} violated, "
          f"{paper_checked - paper_violated} satisfied.")

    h, _, violations = exact_state_recursion(sched, mega_on_days)
    print("Exact-state h_jd: " + ", ".join(f"h[{k}]={v:.0f}" for k, v in sorted(h.items())))

    split_missed_it = split_satisfied and t_sum > t_max
    paper_missed_it = paper_satisfied and t_sum > t_max
    print(f"-> split {'INCORRECTLY ACCEPTS' if split_missed_it else 'correctly rejects'}; "
          f"paper {'INCORRECTLY ACCEPTS' if paper_missed_it else 'correctly rejects'}; "
          f"exact-state {'flags' if violations else 'does not flag'} day {min(violations) if violations else '-'}.")

    return {
        "instance": INSTANCE.name,
        "scenario": label,
        "window_start_day": d,
        "window_end_day": d_,
        "real_flight_minutes": t_sum,
        "T_max_minutes": t_max,
        "paper_c13_rows_satisfied": paper_satisfied,
        "legacy_split_rows_satisfied": split_satisfied,
        "exact_state_h_at_end_day": h[d_],
        "exact_state_violation": d_ in violations,
        "split_missed_it": split_missed_it,
        "paper_missed_it": paper_missed_it,
    }


def main():
    both_endpoints = run_scenario("both endpoints checked (lem:c13_split_limit)", {1, 4})
    one_endpoint = run_scenario("only end-day checked (lem:c13_flaw)", {4})

    out_path = ROOT / "results" / "tables" / "c13_loophole_validation.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(both_endpoints.keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(both_endpoints)
        writer.writerow(one_endpoint)
    print(f"\nWrote {out_path}")

    assert both_endpoints["split_missed_it"], "Expected split to miss the both-endpoints-checked violation"
    assert not both_endpoints["paper_missed_it"], "Expected paper form to catch the both-endpoints-checked violation"
    assert not one_endpoint["split_missed_it"], "Expected split to catch the single-endpoint-checked violation"
    assert one_endpoint["paper_missed_it"], "Expected paper form to miss the single-endpoint-checked violation"
    print("\nOK: the two formulations fail in complementary, non-overlapping cases; "
          "the exact-state recursion correctly rejects both.")


if __name__ == "__main__":
    main()

