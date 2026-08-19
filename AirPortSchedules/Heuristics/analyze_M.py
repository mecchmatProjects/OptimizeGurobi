import json

for h in ['7', '15', '21', '30']:
    try:
        with open(f'Inputs/DataCplex_density=1_p=10_h={h}_test_0.json') as f:
            data = json.load(f)
        total_dur = sum(float(fl[4]) - float(fl[3]) for fl in data['Flights'])
        max_dur = max(float(fl[4]) - float(fl[3]) for fl in data['Flights'])
        max_arr = max(float(fl[4]) for fl in data['Flights'])
        thresholds = data['Maintenance_Thresholds']
        n_days = max(int(float(fl[4]) // 1440) + 1 for fl in data['Flights']) + 1
        print(f'h={h}: F={len(data["Flights"])}, P={len(data["Aircrafts"])}, D={n_days}')
        print(f'  total_dur={total_dur:.0f}min ({total_dur/60:.0f}hrs)')
        print(f'  max single flight dur={max_dur:.0f}min')
        print(f'  Thresholds: A={thresholds["A"]}hr, B={thresholds["B"]}hr')
        print(f'  Thresholds: C={thresholds["C"]}days, D={thresholds["D"]}days')
        # For C13: M needs to be > total flight duration per aircraft
        # Total per aircraft = total_dur / n_aircraft (rough)
        n_ac = len(data['Aircrafts'])
        print(f'  Avg dur per aircraft: {total_dur/n_ac:.0f}min ({total_dur/n_ac/60:.0f}hrs)')
        print(f'  Tight M for C13: {total_dur:.0f} (total all flights)')
        print()
    except FileNotFoundError:
        print(f'h={h}: file not found')
