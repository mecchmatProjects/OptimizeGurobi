import json, math

fp = 'inpytABCD/ABCD_all_checks_test.json'
data = json.load(open(fp))
thresh  = data['Maintenance_Thresholds']
init    = data['Initial_Checks']
horizon_min  = max(f[4] for f in data['Flights'])
horizon_days = horizon_min / 1440.0

print(f'=== {fp}  horizon={horizon_min:.0f}min = {horizon_days:.1f} days ===')
print(f'Thresholds:  A={thresh["A"]}min  B={thresh["B"]}min  C={thresh["C"]}days  D={thresh["D"]}days')
print(f'  AC | A_remain(min) | B_remain(min) | C_remain(days) | D_remain(days) | needs check?')
for ac in data['Aircrafts']:
    s = str(ac)
    a_rem = thresh['A'] - init.get('A', {}).get(s, 0)
    b_rem = thresh['B'] - init.get('B', {}).get(s, 0)
    c_rem = thresh['C'] - init.get('C_Days', {}).get(s, 0)
    d_rem = thresh['D'] - init.get('D_Days', {}).get(s, 0)
    flags = []
    if a_rem <= horizon_min:  flags.append(f'A(in {a_rem:.0f}min)')
    if b_rem <= horizon_min:  flags.append(f'B(in {b_rem:.0f}min)')
    if c_rem <= horizon_days: flags.append(f'C(in {c_rem:.1f}days)')
    if d_rem <= horizon_days: flags.append(f'D(in {d_rem:.1f}days)')
    marker = '<<' if flags else '  '
    print(f'  {ac:2d} | {a_rem:13.0f} | {b_rem:13.0f} | {c_rem:14.1f} | {d_rem:14.1f}  {marker} {", ".join(flags)}')
