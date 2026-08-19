import json, glob

for fp in sorted(glob.glob('Inputs3/*.json')):
    raw = json.load(open(fp))
    thresh = raw['Maintenance_Thresholds']
    init = raw.get('Initial_Checks', {})
    A_init = {int(k): v for k,v in init.get('A',{}).items()}
    B_init = {int(k): v for k,v in init.get('B',{}).items()}
    C_init = {int(k): v for k,v in init.get('C_Days', init.get('C',{})).items()}
    D_init = {int(k): v for k,v in init.get('D_Days', init.get('D',{})).items()}
    max_arr = max(fl[4] for fl in raw['Flights'])
    print(f'\n=== {fp}  horizon={max_arr:.0f}min = {max_arr/1440:.1f} days ===')
    print(f'Thresholds:  A={thresh["A"]}min  B={thresh["B"]}min  C={thresh["C"]}days  D={thresh["D"]}days')
    print(f'  AC | A_remain(min) | B_remain(min) | C_remain(days) | D_remain(days) | needs check?')
    for aid in sorted(A_init.keys()):
        a_r = thresh['A'] - A_init.get(aid, 0)
        b_r = thresh['B'] - B_init.get(aid, 0)
        c_r = thresh['C'] - C_init.get(aid, 0)
        d_r = thresh['D'] - D_init.get(aid, 0)
        flags = []
        if a_r < max_arr:        flags.append(f'A(in {a_r:.0f}min)')
        if b_r < max_arr:        flags.append(f'B(in {b_r:.0f}min)')
        if c_r * 1440 < max_arr: flags.append(f'C(in {c_r:.0f}days)')
        if d_r * 1440 < max_arr: flags.append(f'D(in {d_r:.0f}days)')
        flag_str = '  << ' + ', '.join(flags) if flags else ''
        print(f'  {aid:2d} | {a_r:13.0f} | {b_r:13.0f} | {c_r:14.0f} | {d_r:14.0f}{flag_str}')
