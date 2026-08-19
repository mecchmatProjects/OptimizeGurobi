import json
from heu180h import MILP_Sheduler

opt = MILP_Sheduler('Inputs/DataCplex_density=1_p=10_h=15_test_0.json')
flights = opt.flight_data        # dict  fid -> {origin, destination, ...}
maint_airports = set(opt.maint_airports)
checks = opt.CHECK_LIST
n_days = len(opt.days)

print(f'Maintenance airports ({len(maint_airports)}): {sorted(maint_airports)}')
maint_flights = [k for k, v in flights.items() if v['destination'] in maint_airports]
print(f'Total flights:               {len(flights)}')
print(f'Arriving at maint airports:  {len(maint_flights)}')

n_aircraft = len(opt.aircraft_ids)
n_checks   = len(checks)

c9_current = len(flights) * n_aircraft * n_days * n_checks
c9_reduced = len(maint_flights) * n_aircraft * n_days * n_checks

print(f'\nC9 current:  {c9_current:,}')
print(f'C9 reduced:  {c9_reduced:,}')
print(f'Reduction:   {(1 - c9_reduced/c9_current)*100:.1f}%')
print(f'\nAlso reduces z vars from {c9_current//n_checks//n_days} to {len(maint_flights)} flights')
print(f'z var reduction: {c9_current:,} -> {c9_reduced:,} ({(1-c9_reduced/c9_current)*100:.1f}% fewer)')
