import json

with open('Inputs/DataCplex_density=1_p=10_h=15_test_0.json') as f:
    data = json.load(f)

maint_apts = [apt for apt, cap in data['Station_Capacity'].items() if cap > 0]
print('Maintenance airports:', maint_apts)
all_apts = list(set(fl[1] for fl in data['Flights']) | set(fl[2] for fl in data['Flights']))
print('All airports:', sorted(all_apts))
maint_flights = [fl for fl in data['Flights'] if fl[2] in maint_apts]
n_total = len(data['Flights'])
n_maint = len(maint_flights)
n_ac = len(data['Aircrafts'])
max_day = max(int(float(fl[4]) // 1440) + 1 for fl in data['Flights']) + 1
print(f'Total flights: {n_total}, landing at maintenance airports: {n_maint}')
print(f'Max day: {max_day}')
print(f'Aircraft: {n_ac}')
print(f'Total z vars (all flights): {n_total * n_ac * max_day * 4}')
print(f'Useful z vars (maint flights only): {n_maint * n_ac * max_day * 4}')
print(f'Waste factor: {n_total/n_maint:.2f}x')
