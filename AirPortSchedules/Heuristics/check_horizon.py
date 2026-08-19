import json
data = json.load(open('inputsABCD/ABCD_multi_check_test.json'))

flights = data['Flights']
last_dep = max(float(f[3]) for f in flights)
import math
n_days = int(last_dep / 1440) + 1
print(f'Last dep={last_dep}, horizon days n={n_days}')

thresh = {'C': 10, 'D': 14}
ic = data['Initial_Checks']

for c, t in thresh.items():
    key_cd = f'{c}_Days'
    init_dict = ic.get(key_cd, ic.get(c, {}))
    print(f'\nCheck {c} (thresh={t}): n={n_days}')
    for j in data['Aircrafts']:
        sid = str(j)
        d_init = float(init_dict.get(sid, 0))
        rem = t - d_init
        needs = rem < n_days
        print(f'  AC{j}: D_init={d_init}, remaining={rem}, needs_check_in_horizon={needs}')
