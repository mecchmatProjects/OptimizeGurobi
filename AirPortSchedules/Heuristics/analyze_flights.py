import json
from collections import defaultdict

for fname in ['inpytABCD/ABCD_all_checks_test.json', 'inpytABCD/ABCD_near_threshold_test.json']:
    print(f'\n=== {fname} ===')
    with open(fname) as f:
        d = json.load(f)
    flights = d['Flights']
    print('Flight schedule:')
    for k, v in flights.items():
        dep_day = v['departure_time'] // 1440 + 1
        arr_day = v['arrival_time'] // 1440 + 1
        print(f"  {k}: dep={v['departure_time']:5d}  arr={v['arrival_time']:5d}  from={v['departure_airport']}  to={v['arrival_airport']}  dep_day={dep_day}  arr_day={arr_day}")

    print('\nFlights arriving at C (MA) per day:')
    by_day = defaultdict(list)
    for k, v in flights.items():
        if v['arrival_airport'] == 'C':
            day = v['arrival_time'] // 1440 + 1
            by_day[day].append(k)
    for day in sorted(by_day):
        print(f'  Day {day}: {by_day[day]}')
