"""
Diagnose why ABCD_all_checks_test.json is infeasible.

Key facts about the model:
  y[j,d,c] = sum_i z[i,j,d,c]         (C11)
  z[i,j,d,c] only exists for i in FM   (flights arriving at MA=C)
  z[i,j,d,c] <=  x[i,j]               (C9: must fly flight i to trigger check)
  C12b: mega[j, days[0], c] >= 1 when remaining <= 0  (overdue check)
  mega[j,d,c] = y[j,d,c] when --no-check-hierarchy    (hierarchy off)

  => For overdue AC j and check c, we need:
       y[j, day1, c] >= 1
       sum_i z[i,j,day1,c] >= 1
       x[i,j] >= z[i,j,day1,c] for one i in FM arriving on day 1

  => The ONLY way to schedule an overdue check for AC j is:
       * AC j must fly a maintenance-arriving flight on day 1
       * That flight must be the z-trigger

  => If multiple aircraft need overdue checks on day 1 but only ONE
     flight arrives at C on day 1, exactly ONE aircraft can be served.
"""
import json, math

fname = 'inpytABCD/ABCD_all_checks_test.json'
with open(fname) as f:
    d = json.load(f)

thresholds = d['Maintenance_Thresholds']   # A:27000, B:42000, C:600, D:2920
durations  = d['Maintenance_Durations']    # min
init       = d['Initial_Checks']
flights    = d['Flights']                  # [id, from, to, dep, arr]
aircrafts  = d['Aircrafts']
cap_C      = d['Station_Capacity']['C']
DAY_SHIFT  = 1440

print(f"Station capacity at C: {cap_C}")
print(f"Aircraft: {aircrafts}")
print()

# Which aircraft need an overdue check on day 1 (remaining <= 0)?
print("=== Aircraft with overdue checks (C12b forces mega[j,day1,c]>=1) ===")
overdue = {}   # {aircraft_id: [check_types]}
for c, thresh in thresholds.items():
    key = f'{c}_Days' if c in ('C', 'D') else c
    if key not in init:
        key = c
    for j in aircrafts:
        init_val = init.get(key, {}).get(str(j), 0)
        if c in ('C', 'D'):
            # stored as days
            init_days = init_val
        else:
            # stored as minutes -> convert to threshold units (same minutes)
            init_days = init_val  # for A/B this is minutes
        remaining = thresh - init_val
        if c in ('C', 'D') and remaining <= 0:
            overdue.setdefault(j, []).append(c)
            print(f"  AC{j}: {c}-check overdue  (init={init_val} days, thresh={thresh} days, remaining={remaining})")
        elif c in ('A', 'B') and remaining <= 0:
            overdue.setdefault(j, []).append(c)
            print(f"  AC{j}: {c}-check overdue  (init={init_val} min, thresh={thresh} min, remaining={remaining} min)")

print()

# Which flights arrive at C on day 1?
print("=== Flights arriving at maintenance airport C ===")
fm_day = {}   # {day: [flight_ids]}
for fl in flights:
    fid, frm, to_, dep, arr = fl
    if to_ == 'C':
        day = int(arr) // DAY_SHIFT + 1
        fm_day.setdefault(day, []).append(fid)
        
all_days = sorted(fm_day.keys())
for day in all_days[:10]:
    print(f"  Day {day}: flights {fm_day[day]}")

print()
print("=== Root cause analysis ===")
day1_flights = fm_day.get(1, [])
print(f"Flights arriving at C on day 1: {day1_flights}")
print()

# Count how many aircraft need triggers on day 1
need_day1 = []
for j, checks in overdue.items():
    # C12b forces mega[j, day1, c] >= 1
    # => y[j, day1, c] >= 1 (with hierarchy off)
    # => sum_i z[i,j,day1,c] >= 1
    # => x[i,j] = 1 for SOME i in FM arriving on day 1
    need_day1.append(j)

print(f"Aircraft needing check triggers on day 1: {need_day1}")
print(f"Available trigger flights on day 1: {day1_flights}")
print()

if len(need_day1) > len(day1_flights):
    print(f"!!! INFEASIBLE: {len(need_day1)} aircraft need a trigger flight on day 1")
    print(f"    but only {len(day1_flights)} flight(s) arrive at C on day 1.")
    print(f"    Each aircraft needs a DIFFERENT trigger flight (C9: x[i,j]=1 is exclusive).")
    print()
    print("--- SOLUTION OPTIONS ---")
    print("Option A: Add more flights arriving at C on day 1 (1 per overdue aircraft).")
    print(f"          Need {len(need_day1) - len(day1_flights)} additional C-arriving flights on day 1.")
    print()
    print("Option B: Separate overdue checks across different days.")
    print("          Make some checks near-threshold (not yet overdue) so they")
    print("          can use flights arriving later.")
    print()
    print("Option C: Run individual per-check-type test files instead of one combined file.")
    print("          Avoids the trigger-flight contention entirely.")
else:
    print(f"Enough trigger flights available. Infeasibility must come from a different constraint.")

print()
print("=== Concrete fix: how many C-arriving flights needed per day ===")
# For overdue checks: all need day-1 triggers
# For near-threshold (remaining R days): need triggers by day R
# Free aircraft (AC4, AC5): no check needed, don't need trigger flights
print(f"Aircraft needing triggers:")
for c, thresh in thresholds.items():
    key = f'{c}_Days' if c in ('C', 'D') else c
    if key not in init:
        key = c
    for j in aircrafts:
        init_val = init.get(key, {}).get(str(j), 0)
        remaining = thresh - init_val
        if remaining <= 0:
            print(f"  AC{j}: {c}-check overdue -> needs trigger on day 1")
        elif c in ('C', 'D'):
            horizon = 20  # days
            if remaining < horizon:
                print(f"  AC{j}: {c}-check remaining={remaining} days -> needs trigger by day {math.ceil(remaining)}")
