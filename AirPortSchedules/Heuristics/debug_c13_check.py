import json

with open('inputsABCD/ABCD_multi_check_test.json') as f:
    d = json.load(f)

DAY_SHIFT = 1440
flights = {}
for fl in d['Flights']:
    fid, orig, dest, dep, arr = fl
    day_dep = int(dep // DAY_SHIFT) + 1
    flights[fid] = {'orig': orig, 'dest': dest, 'dep': dep, 'arr': arr, 'dur': arr-dep, 'day': day_dep}

# AC0 flights: 1-8
ac0_flights = list(range(1, 9))
thresh = 1200  # minutes
init_min = 1000  # minutes
days = [1, 2, 3, 4]
n = 4

print('c13b constraints (for AC0, check A):')
for ei in range(1, n):
    d_ = days[ei]
    t_sum = sum(flights[i]['dur'] for i in ac0_flights if 0 < flights[i]['day'] <= d_)
    rhs = thresh - init_min
    print(f'  d_={d_}: t_sum={t_sum}, RHS={rhs}, violated_without_check={t_sum > rhs}')

print()
print('c13 pairs for AC0, check A:')
for si in range(n - 1):
    for ei in range(si + 2, n):
        d, d_ = days[si], days[ei]
        t_sum = sum(flights[i]['dur'] for i in ac0_flights if d < flights[i]['day'] <= d_)
        print(f'  ({d},{d_}]: t_sum={t_sum}, thresh={thresh}, EXCEEDS={t_sum > thresh}')
