import json
import math
import random
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import matplotlib.patches as mpatches
import pandas as pd

# ----------------------------
# CORE SCHEDULER ENGINE
# ----------------------------

class Scheduler:
    def __init__(self, data_path):
        with open(data_path, 'r') as f:
            self.data = json.load(f)
        
        self.flights = {f[0]: {'fid': f[0], 'orig': f[1], 'dest': f[2], 'dep': f[3], 'arr': f[4], 'dur': f[4]-f[3]} 
                        for f in self.data['Flights']}
        self.aircrafts = self.data['Aircrafts']
        self.init_pos = self.data['AIRCRAFT_INIT_POS']
        self.init_checks = self.data['Initial_Checks']
        self.thresholds = self.data['Maintenance_Thresholds']
        self.durations = self.data['Maintenance_Durations']
        self.station_cap = self.data['Station_Capacity']
        self.cost_matrix = self.data['Cost_Matrix']
        
        self.ferry_time = 60
        self.ferry_cost = 6000 # High cost helps the optimizer minimize these

    def get_timeline(self, aid, fids):
        curr_apt = self.init_pos[str(aid)]
        curr_time = 0.0
        a = float(self.init_checks['A'].get(str(aid), 0))
        b = float(self.init_checks['B'].get(str(aid), 0))
        c_init = float(self.init_checks.get('C_Days', {}).get(str(aid), 0))
        d_init = float(self.init_checks.get('D_Days', {}).get(str(aid), 0))
        
        events = []
        total_cost = 0

        for fid in fids:
            fl = self.flights[fid]
            
            # 1. Repositioning (Ferry) - Minimization logic happens via cost
            if curr_apt != fl['orig']:
                if curr_time + self.ferry_time > fl['dep']: return None
                events.append({'kind': 'FERRY', 'start': curr_time, 'end': curr_time + self.ferry_time, 
                               'orig': curr_apt, 'dest': fl['orig'], 'cost': self.ferry_cost})
                curr_time += self.ferry_time
                curr_apt = fl['orig']
                total_cost += self.ferry_cost
            
            # 2. Maintenance Logic
            days_now = curr_time / 1440.0
            needed = None
            if d_init + days_now > self.thresholds['D']: needed = 'D'
            elif c_init + days_now > self.thresholds['C']: needed = 'C'
            elif b + fl['dur'] > self.thresholds['B']: needed = 'B'
            elif a + fl['dur'] > self.thresholds['A']: needed = 'A'
            
            if needed:
                m_dur = self.durations[needed]
                if curr_time + m_dur > fl['dep']: return None
                if self.station_cap.get(fl['orig'], 0) == 0: return None
                
                events.append({'kind': 'MAINT', 'start': curr_time, 'end': curr_time + m_dur, 
                               'orig': fl['orig'], 'dest': fl['orig'], 'check': needed})
                curr_time += m_dur
                
                if needed == 'D': a=0; b=0; c_init = -(curr_time/1440.0); d_init = -(curr_time/1440.0)
                elif needed == 'C': a=0; b=0; c_init = -(curr_time/1440.0)
                elif needed == 'B': a=0; b=0
                elif needed == 'A': a=0

            # 3. Flight Execution
            if curr_time > fl['dep']: return None
            
            snap = {'rem_a': self.thresholds['A'] - a, 'rem_b': self.thresholds['B'] - b,
                    'rem_c': self.thresholds['C'] - (c_init + fl['dep']/1440.0),
                    'rem_d': self.thresholds['D'] - (d_init + fl['dep']/1440.0)}
            
            events.append({'kind': 'FLIGHT', 'fid': fid, 'start': fl['dep'], 'end': fl['arr'], 
                           'orig': fl['orig'], 'dest': fl['dest'], 'cost': self.cost_matrix[fid-1][aid], 
                           'dur': fl['dur'], **snap})
            
            curr_time, curr_apt = fl['arr'], fl['dest']
            a += fl['dur']; b += fl['dur']
            total_cost += self.cost_matrix[fid-1][aid]

        return {'events': events, 'cost': total_cost}

    def optimize(self):
        ac_fids = {aid: [] for aid in self.aircrafts}
        assigned = set()
        sorted_fids = sorted(self.flights.keys(), key=lambda x: self.flights[x]['dep'])
        
        for fid in sorted_fids:
            best_opt = None
            for aid in self.aircrafts:
                res = self.get_timeline(aid, ac_fids[aid] + [fid])
                if res and (best_opt is None or res['cost'] < best_opt[0]):
                    best_opt = (res['cost'], aid)
            if best_opt:
                ac_fids[best_opt[1]].append(fid)
                assigned.add(fid)

        for _ in range(5): 
            still_unassigned = [fid for fid in self.flights if fid not in assigned]
            for fid in still_unassigned:
                best_ins = None
                for aid in self.aircrafts:
                    for i in range(len(ac_fids[aid]) + 1):
                        trial = ac_fids[aid][:i] + [fid] + ac_fids[aid][i:]
                        res = self.get_timeline(aid, trial)
                        if res and (best_ins is None or res['cost'] < best_ins[2]):
                            best_ins = (aid, i, res['cost'])
                if best_ins:
                    aid, idx, _ = best_ins
                    ac_fids[aid].insert(idx, fid)
                    assigned.add(fid)

        return ac_fids, [fid for fid in self.flights if fid not in assigned]

# ----------------------------
# EXECUTION
# ----------------------------

sc = Scheduler('data18h.json')
final_ac_fids, unassigned = sc.optimize()

# Calculate and Print Free Time
print("\n--- Aircraft Utilization Summary ---")
max_horizon = max([f['arr'] for f in sc.flights.values()])
for aid in sorted(sc.aircrafts):
    res = sc.get_timeline(aid, final_ac_fids[aid])
    if res:
        busy_time = sum((e['end'] - e['start']) for e in res['events'])
        # Free time is horizon minus the time actually spent doing things
        free_time = max_horizon - busy_time
        print(f"AC {aid}: Free Time = {free_time:.2f} mins")
    else:
        print(f"AC {aid}: Free Time = {max_horizon:.2f} mins (No flights assigned)")
print("------------------------------------\n")

# Generate Table
rows = []
for aid in sorted(sc.aircrafts):
    res = sc.get_timeline(aid, final_ac_fids[aid])
    if res:
        for e in res['events']:
            label = f"F{e['fid']}" if e['kind'] == 'FLIGHT' else e.get('check', 'FERRY')
            row = [aid, e['kind'], label, e['orig'], e['dest'], e['start'], 
                   e.get('dur', '-'), e.get('rem_a', '-'), e.get('rem_b', '-'), 
                   e.get('rem_c', '-'), e.get('rem_d', '-')]
            rows.append(row)

df = pd.DataFrame(rows, columns=['AID', 'Type', 'ID', 'From', 'To', 'Dep', 'Dur', 'Rem A', 'Rem B', 'Rem C(d)', 'Rem D(d)'])
print(df.to_string())
df.to_csv('final_schedule.csv', index=False)

# Plotting
colors = {"FLIGHT": "#3498db", "FERRY": "#9b59b6", "A": "#2ecc71", "B": "#f1c40f", "C": "#e67e22", "D": "#c0392b", "UN": "#e74c3c"}
fig, ax = plt.subplots(figsize=(15, 8))
for i, aid in enumerate(sorted(sc.aircrafts)):
    res = sc.get_timeline(aid, final_ac_fids[aid])
    if res:
        for e in res['events']:
            c = colors.get(e.get('check', e['kind']), colors['FLIGHT'])
            ax.broken_barh([(e['start'], e['end']-e['start'])], (i*10, 8), facecolors=c, edgecolor='white', linewidth=0.5)

un_y = len(sc.aircrafts) * 10
for fid in unassigned:
    fl = sc.flights[fid]
    ax.broken_barh([(fl['dep'], fl['dur'])], (un_y, 8), facecolors=colors["UN"], alpha=0.3, hatch='//')

legend_patches = [mpatches.Patch(color=color, label=label) for label, color in colors.items()]
ax.legend(handles=legend_patches, title="Event Types", loc='upper left', bbox_to_anchor=(1, 1))

ax.set_yticks([i*10+4 for i in range(len(sc.aircrafts)+1)])
ax.set_yticklabels([f"AC {a}" for a in sorted(sc.aircrafts)] + ["UNASSIGNED"])
plt.title(f"Optimized Fleet Schedule (Assigned: {len(sc.flights)-len(unassigned)})")
plt.tight_layout()
plt.show()