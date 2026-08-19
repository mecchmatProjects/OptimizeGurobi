"""
Inspect specific constraints for overdue aircraft to identify the conflict.
Focuses on: C12b (forces mega[j,day1,c] >= 1), C11 (y=sum(z)), C9 (z<=x), C1 (sum(x)=1).

For AC2 (C-check overdue):
  C12b: mega[AC2, day1, C] >= 1
  hierarchy=off: mega[j,d,c] = y[j,d,c]
  C11: y[AC2, day1, C] = sum_i z[i, AC2, day1, C]
  C9:  z[i, AC2, day1, C] <= x[i, AC2] for each i in FM
  C1:  sum_j x[i, AC2] = 1 for each i (can give flight i to at most 1 aircraft)

  => Need z[i, AC2, day1, C] = 1 for some i in FM arriving on day1
     AND z[i, AC0, day1, A] = 1 for some i in FM arriving on day1
     => Two different aircraft need TWO different flights arriving at C on day1

Same for AC0 (A-check), AC1 (B-check), AC3 (D-check).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logging
logging.disable(logging.CRITICAL)

from heu180h import MILP_Sheduler
import json

DATA = 'inpytABCD/ABCD_all_checks_test.json'

print("=== Constraint trace for ABCD_all_checks_test.json ===\n")

sch = MILP_Sheduler(DATA)

print(f"Aircraft: {sch.aircraft_ids}")
print(f"Maintenance airports: {sch.maint_airports}")
print(f"FM (flights arriving at MA C): {sch.maint_flight_ids}")
print()

# Which flights arrive at C per day?
from collections import defaultdict
fm_by_day = defaultdict(list)
for i in sch.maint_flight_ids:
    fd = sch.flight_data[i]
    fm_by_day[fd['day_arrival']].append(i)

print("FM flights arriving at C per day:")
for day in sorted(fm_by_day.keys())[:6]:
    print(f"  Day {day}: flights {fm_by_day[day]}")
print()

# What does C12b require?
print("=== C12b constraints (forced checks) ===")
days = sorted(sch.days)
n = len(days)
for c in sch.CHECK_LIST:
    thresh_days = sch.check_days[c]
    if thresh_days is None:
        print(f"  Check {c}: flight-hour type (C13b applies, not C12b)")
        continue
    for j in sch.aircraft_ids:
        init_days = sch.init_check_hrs[c].get(j, 0.0) / 24.0
        remaining = thresh_days - init_days
        if remaining <= 0:
            print(f"  AC{j} {c}-check: OVERDUE (remaining={remaining}) -> mega[{j}, day1={days[0]}, {c}] >= 1")
            print(f"       => y[{j},{days[0]},{c}] >= 1 (hierarchy off)")
            print(f"       => sum_i z[i,{j},{days[0]},{c}] >= 1")
            print(f"       => need some i in FM arriving on day {days[0]} with x[i,{j}]=1")
            day1_fm = fm_by_day.get(days[0], [])
            print(f"       FM day {days[0]}: {day1_fm}")
            print()
        elif remaining < n:
            import math
            cutoff = int(math.ceil(remaining))
            window = [d for d in days if d <= cutoff]
            print(f"  AC{j} {c}-check: remaining={remaining:.1f} days -> need check in days {window}")
            available = []
            for d in window:
                available.extend([(d, i) for i in fm_by_day.get(d, [])])
            print(f"       Available trigger flights: {available}")
            print()

print("=== C13b constraints (A/B accumulated hours) ===")
for c in ['A', 'B']:
    hr_limit = sch.check_hrs[c]
    for j in sch.aircraft_ids:
        prior_hrs = sch.init_check_hrs[c].get(j, 0.0)
        remaining_min = (hr_limit - prior_hrs) * 60
        if remaining_min < 0:
            print(f"  AC{j} {c}-check: OVERDUE by {-remaining_min:.0f} min -> must check ASAP")
            # Which day must the check happen?
            # C13b: for ei=1 (d_=day2): t_sum_day2 <= remaining_min + M*mega[j,day1,c] + M*mega[j,day2,c]
            # If AC flies flights on day1: t_sum_day2 = total_dur_day1_flights * x[i,j]
            day1_flights = sch._f_dep_between_days(0, days[1])
            total_day1 = sum(sch.flight_data[i]['duration'] for i in day1_flights)
            print(f"       Max day1 flight minutes if flying all: {total_day1}")
            print(f"       Remaining threshold: {remaining_min}")
            if total_day1 > remaining_min:
                print(f"       => If flying all day1 flights, check must be on day1 or day2")
                day1_fm = fm_by_day.get(1, [])
                day2_fm = fm_by_day.get(2, [])
                print(f"       FM day1: {day1_fm}, FM day2: {day2_fm}")
            print()
        elif remaining_min < 5000:
            print(f"  AC{j} {c}-check: remaining={remaining_min:.0f} min (near threshold)")

print("=== Summary: trigger flights needed ===")
print("Each aircraft needing a check trigger must FLY a maintenance-arriving flight.")
print("Two aircraft CANNOT share the same trigger flight (C1: sum x[i,j]=1).")
print()
print("Aircraft that need triggers and their available options:")
needed = {}
for c in ['C', 'D']:
    thresh_days = sch.check_days[c]
    for j in sch.aircraft_ids:
        init_days = sch.init_check_hrs[c].get(j, 0.0) / 24.0
        remaining = thresh_days - init_days
        if remaining <= 0:
            day1_fm = fm_by_day.get(days[0], [])
            needed[f'AC{j}({c})'] = day1_fm
            print(f"  AC{j} needs {c} trigger on day1. Available: {day1_fm}")

for c in ['A', 'B']:
    hr_limit = sch.check_hrs[c]
    for j in sch.aircraft_ids:
        prior_hrs = sch.init_check_hrs[c].get(j, 0.0)
        remaining_min = (hr_limit - prior_hrs) * 60
        if remaining_min < 0:
            # How soon must check happen?
            day1_fm = fm_by_day.get(1, [])
            day2_fm = fm_by_day.get(2, [])
            needed[f'AC{j}({c})'] = day1_fm + day2_fm
            print(f"  AC{j} needs {c} trigger by day2. Available: {day1_fm + day2_fm}")

print()
print(f"Total aircraft needing triggers: {len(needed)}")
print(f"Unique trigger flights across first 2 days: {list(set(f for fl in needed.values() for f in fl))}")

# Count unique flights needed vs available
all_options = set(f for fl in needed.values() for f in fl)
print(f"Total unique trigger options: {len(all_options)}")
if len(all_options) < len(needed):
    print(f"!!! INFEASIBLE: only {len(all_options)} distinct trigger flights for {len(needed)} aircraft")
else:
    print(f"Potentially feasible: {len(all_options)} options for {len(needed)} aircraft")
    print("But may still be infeasible due to routing constraints (C23 turnaround).")
