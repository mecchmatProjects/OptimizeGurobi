import os
import re
import argparse
from pathlib import Path


from collections import defaultdict

"""
Paper summary & developer notes (inserted):

This code implements a compact tail-assignment MILP inspired by the paper
"A compact optimization model for the tail assignment problem". Key modeling
decisions reflected in this repository:

- use binary assignment variables `x[i,p]` plus small auxiliary sets `z` and
    `y` to represent maintenance triggering and activation. This keeps the
    formulation compact compared to explicit arc/path variables.
- continuity (equipment-turn) constraints are implemented as conservative
    counting inequalities instead of enumerating all compatible flight arcs.
- maintenance is aggregated by day and check-type; blocking constraints use
    `z`/`y` to prevent conflicting flight assignments.

Implementation & testing notes:
- We provide flags at runtime to toggle `equipment_turn` and `maint_block`
    constraints to make unit testing and debugging easier.
- Tighten Big-M values where possible; large `Mbig` values harm LP relaxations.
- For CI or open-source tests prefer CBC/GLPK; CPLEX/Gurobi are recommended for
    production runs due to much better performance on larger instances.

See `improved_model.py` and `model_builder.py` for canonical builder and
lightweight test builder respectively.
"""


from pyomo.environ import *
from pyomo.opt import SolverFactory
from data_io import parse_airline_data
from improved_model import build_full_model
from model_params import Params


DEBUG = False  # True
DEBUG_15 = False
CNT_FILE = False

USE_PAPER_HRS_CHECK = True  # False  # Use check (PAPER) for maintenances as in paper
USE_UPDATED_HRS_CHECKS = False # True  # Use check(MY) updated version for maintenances
USE_EXISTING_HRS_CHECK = True  # Use hrs check counting of elapsed flight hrs

USE_DAYS_CHECKS = False  # Use check version for maintenances with days threshold
USE_EXISTING_DAYS_CHECKS = False   # Use check version for maintenances with days threshold with elapsed days

USE_CHECK_HIERARCHY = True  # If we use D check - we reload other checks too, C check - reloads A,B, B - reloads A

USE_CHECKS_SANITY = True
USE_OVERLAP_CHECKS = False

DPHT = None  #  # (0.5, 10, 15, 3)

# Inputs ---

TEST_DIR = "..//TestsData"
OUT_DIR = "OUT_TEST"

DayShift = 24  # Consider shift as day with 24 hrs

# Flying-Hours since last check
# Acheck = {0: 4.0, 1: 3.0, 2: 3.0, 3: 2.0, 4: 0.0, 5: 4.0, 6: 3.0, 7: 0.0, 8: 2.0, 9: 5.0}
# Bcheck = {0: 10.0, 1: 10.0, 2: 14.0, 3: 15.0, 4: 10.0, 5: 5.0, 6: 9.0, 7: 0.0, 8: 2.0, 9: 11.0}
# Ccheck = {0: 25.0, 1: 10.0, 2: 20.0, 3: 6.0, 4: 27.0, 5: 20.0, 6: 15.0, 7: 0.0, 8: 10.0, 9: 15.0}
# Dcheck = {0: 50.0, 1: 40.0, 2: 39.0, 3: 29.0, 4: 49.0, 5: 45.0, 6: 58.0, 7: 0.0, 8: 30.0, 9: 20.0}

Acheck ={0: 46.0, 1: 40.0, 2: 20.0, 3: 10.0, 4: 0.0, 5: 5.0, 6: 0.0, 7: 1.0, 8: 2.0, 9: 0.0}
Bcheck = {0: 1340.0, 1: 1200.0, 2: 1438.0, 3: 1100.0, 4: 1200.0, 5: 1100.0, 6: 1100.0, 7: 1100.0, 8: 1100.0, 9: 1100.0}
Ccheck = {0: 3000.0, 1: 2000.0, 2: 3538.0, 3: 3000.0, 4: 4315.0, 5: 20.0, 6: 20.0, 7: 20.0, 8: 20.0, 9: 20.0}
Dcheck = {0: 5000.0, 1: 6000.0, 2: 12000.0, 3: 10023.0, 4: 14593.0, 5: 20.0, 6: 14599.0, 7: 10020.0, 8: 10020.0, 9: 14580.0}


#Elapsed days since last check
#Acheck_days = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}
#Bcheck_days = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}
#Ccheck_days = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}
#Dcheck_days = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}


#flying hours since last check
#Acheck ={0: 394.0, 1: 200.0, 2: 250.0, 3: 250.0, 4: 350.0, 5: 340.0, 6: 380.0, 7: 385.0, 8: 395.0, 9: 250.0}
#Bcheck = {0: 1340.0, 1: 1200.0, 2: 1395.0, 3: 1100.0, 4: 1200.0, 5: 1100.0, 6: 1100.0, 7: 1100.0, 8: 1100.0, 9: 1100.0}
#Ccheck = {0: 3000.0, 1: 2000.0, 2: 3538.0, 3: 3000.0, 4: 4310.0, 5: 20.0, 6: 20.0, 7: 20.0, 8: 20.0, 9: 20.0}
#Dcheck = {0: 5000.0, 1: 6000.0, 2: 12000.0, 3: 10023.0, 4: 14593.0, 5: 20.0, 6: 14595.0, 7: 10020.0, 8: 10020.0, 9: 14580.0}



#elapsed days since last check
#Acheck_days ={0: 49.0, 1: 25.0, 2: 32.0, 3: 20.0, 4: 40.0, 5: 24.0, 6: 28.0, 7: 25.0, 8: 49.0, 9: 29.0}
#Bcheck_days = {0: 50.0, 1: 50.0, 2: 179.0, 3: 140.0, 4: 140.0, 5: 140.0, 6: 140.0, 7: 140.0, 8: 140.0, 9: 140.0}
#Ccheck_days = {0: 500.0, 1: 270.0, 2: 510.0, 3: 500.0, 4: 537.0, 5: 20.0, 6: 20.0, 7: 20.0, 8: 20.0, 9: 20.0}
#Dcheck_days = {0: 600.0, 1: 800.0, 2: 1600, 3: 100.0, 4: 1800.0, 5: 20.0, 6: 1823.0, 7: 20.0, 8: 20.0, 9: 20.0}

#
# Acheck = {0: 390.0, 1: 360.0, 2: 350.0, 3: 380.0, 4: 395.0, 5: 340.0, 6: 380.0, 7: 385.0, 8: 375.0, 9: 390.0}
# Bcheck = {0: 590.0, 1: 594.0, 2: 580.0, 3: 570.0, 4: 575.0, 5: 585.0, 6: 591.0, 7: 595.0, 8: 500.0, 9: 520.0}

# Tmax = 8 * 60  # in minutes
# nu = 15
# dmax = 3

Mbig = 9999999

min_turn = 30  # in minutes

# Maintenance thresholds for flying hours
# USE_HRS_CHECKS
#A_check_hours = 400
#B_check_hours = 1440
#C_check_hours = 4320
#D_check_hours = 14600
A_check_hours = 6
B_check_hours = 15
C_check_hours = 30
D_check_hours = 60

A_check_hours = 48
B_check_hours = 1440
C_check_hours = 4320
D_check_hours = 14600

# Maintenance thresholds in elapsed days
# USE_DAYS_CHECKS
A_check_days = 50
B_check_days = 180
C_check_days = 540
D_check_days = 1825

# Maintenance durations in minutes
A_check_duration = 8 * 60
B_check_duration = 48 * 60
C_check_duration = 5 * 24 * 60
D_check_duration = 10 * 24 * 60

# Maintenance durations for days
A_check_duration_days = 1
B_check_duration_days = 2
C_check_duration_days = 5
D_check_duration_days = 10

# Generalized lists
NUM_Checks = 4
# All_Check_List = list(range(1, NUM_Checks+1))
All_Check_List = ["Acheck", "Bcheck", "Ccheck", "Dcheck"]
All_Checks = {
    All_Check_List[0]: Acheck,
    All_Check_List[1]: Bcheck,
    All_Check_List[2]: Ccheck,
    All_Check_List[3]: Dcheck
}

All_Check_days = {
    All_Check_List[0]: A_check_days,
    All_Check_List[1]: B_check_days,
    All_Check_List[2]: C_check_days,
    All_Check_List[3]: D_check_days
}

Premature_Check_penalty = {
    All_Check_List[0]: {0: 0, 1: 10, 2: 20, 3: 40, 4: 60},
    All_Check_List[1]: {0: 0, 1: 10, 2: 20, 3: 40, 4: 60},
    All_Check_List[2]: {0: 0, 1: 10, 2: 20, 3: 40, 4: 60},
    All_Check_List[3]: {0: 0, 1: 10, 2: 20, 3: 40, 4: 60}
}

All_Checks_Done_Days = {
    All_Check_List[0]: A_check_days,
    All_Check_List[1]: B_check_days,
    All_Check_List[2]: C_check_days,
    All_Check_List[3]: D_check_days
}

All_Check_Done_hours = {
    All_Check_List[0]: A_check_hours,
    All_Check_List[1]: B_check_hours,
    All_Check_List[2]: C_check_hours,
    All_Check_List[3]: D_check_hours
}

All_Check_durations = {
    All_Check_List[0]: A_check_duration,
    All_Check_List[1]: B_check_duration,
    All_Check_List[2]: C_check_duration,
    All_Check_List[3]: D_check_duration
}


def _resolve_dict_for_check(mapping, check, default=None):
    """Safely get mapping[check] trying a few fallbacks to avoid KeyError.

    Returns default if nothing found.
    """
    if mapping is None:
        return default
    if check in mapping:
        return mapping[check]
    s = str(check)
    if s in mapping:
        return mapping[s]
    # try common pattern: if check looks like ('A',) or ('A',1)
    try:
        if hasattr(check, '__getitem__'):
            maybe = ''.join([str(x) for x in check])
            if maybe in mapping:
                return mapping[maybe]
    except Exception:
        pass
    return default


def get_premature_penalty(check, d):
    """Return resolved premature penalty for a given check and day d.

    Falls back to 0 if mapping/keys are unavailable.
    """
    try:
        pen_map = _resolve_dict_for_check(Premature_Check_penalty, check, default=Premature_Check_penalty.get(All_Check_List[0], {}))
        days_map_val = _resolve_dict_for_check(All_Check_days, check, default=All_Check_days.get(All_Check_List[0], 0))

        # days_map_val should be an int (All_Check_days), pen_map a dict
        idx = 0
        try:
            idx = (int(days_map_val) - int(d)) % 5
        except Exception:
            idx = 0

        if isinstance(pen_map, dict):
            return pen_map.get(idx, 0)
        return 0
    except Exception:
        return 0

All_Check_durations_days = {
    All_Check_List[0]: A_check_duration_days,
    All_Check_List[1]: B_check_duration_days,
    All_Check_List[2]: C_check_duration_days,
    All_Check_List[3]: D_check_duration_days
}


def write_text_report(model, results, FlightData, output_file_txt):
    """Write textual report of assignment and maintenance to a file."""
    with open(output_file_txt, "w") as file_out:
        print("File", output_file_txt)

        print("\nAircraft Assignment and Maintenance Report:\n", file=file_out)

        print("\n# # # Residual Gap at CPU # # Residual Gap at CPU", file=file_out)
        print("Var\tConst\tNodes\tgap (%)\troot (%)\t(sec)", file=file_out)
        stats = get_solver_stats(results, model)
        if stats:
            try:
                print(f"{stats['nVar']:8}\t{stats['nConst']:10}\t{stats['nodes']}\t{stats['gap_str']}\t-\t{stats['cpu_time']:.2f}", file=file_out)
            except Exception:
                print(f"{stats['nVar']:8}\t{stats['nConst']:10}\t{stats['nodes']}\t{stats['gap_str']}\t-\t{stats['cpu_time']}", file=file_out)
        else:
            print("-\t-\t-\t-\t-\t-  (Solver statistics not available)", file=file_out)

        # Reuse event gathering helper to avoid duplicated logic
        events = gather_events(model, FlightData, All_Check_durations)
        # group by aircraft and print
        events_by_ac = defaultdict(list)
        for e in events:
            events_by_ac[e['aircraft']].append(e)

        for j in model.P:
            evs = sorted(events_by_ac.get(j, []), key=lambda x: x['start'])
            events2_str = ", ".join(e['label'] for e in evs)
            print(f"Aircraft {j}: {events2_str}", file=file_out)


def plot_schedule_from_model(model, FlightData, output_file_pic=None):
    """Create and save a Gantt-like schedule plot for the model solution.

    Returns the events list used for plotting (useful for tests).
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except Exception:
        # matplotlib not available — return empty events
        return []

    # Reuse event gathering helper to avoid duplicating logic
    events = gather_events(model, FlightData, All_Check_durations)
    events.sort(key=lambda x: (x['aircraft'], x['start']))

    if not events:
        return events

    fig, ax = plt.subplots(figsize=(15, 8))
    flight_color = 'tab:blue'
    maintenance_colors = {'A': 'tab:orange', 'B': 'tab:green', 'C': 'tab:red', 'D': 'tab:purple'}
    aircraft_positions = {j: idx for idx, j in enumerate(sorted(set(e['aircraft'] for e in events)))}

    for e in events:
        y = aircraft_positions[e['aircraft']]
        color = flight_color if e['type'] == 'flight' else maintenance_colors.get(e['label'][1], 'grey')
        ax.barh(y, e['end'] - e['start'], left=e['start'], height=0.4, color=color, edgecolor='black')
        ax.text(e['start'] + (e['end'] - e['start']) / 2, y, e['label'], ha='center', va='center', color='white', fontsize=8)

    ax.set_yticks(list(aircraft_positions.values()))
    ax.set_yticklabels([f'Aircraft {j}' for j in sorted(aircraft_positions.keys())])
    ax.set_xlabel('Time (minutes)')
    ax.set_title('Aircraft Flight and Maintenance Timeline')

    flight_patch = mpatches.Patch(color=flight_color, label='Flight')
    maintenance_patches = [mpatches.Patch(color=clr, label=f'Maintenance {typ}') for typ, clr in maintenance_colors.items()]
    ax.legend(handles=[flight_patch] + maintenance_patches, loc='upper right')

    plt.tight_layout()
    if output_file_pic:
        plt.savefig(output_file_pic)

    return events


def solve_model(model, solver_name='cplex'):
    """Solve the Pyomo model using the specified solver and return results."""
    solver = SolverFactory(solver_name)
    # solver.set_executable(...)  # customize if needed
    results = solver.solve(model)
    return results


def print_solver_summary(model, results):
    """Print a short solver/model summary to stdout."""
    print("\n# # # Residual Gap at CPU # # Residual Gap at CPU")
    print("Var\tConst\tNodes\tgap (%)\troot (%)\t(sec)")
    stats = get_solver_stats(results, model)
    if stats:
        try:
            print(f"{stats['nVar']}\t{stats['nConst']}\t{stats['nodes']}\t{stats['gap_str']}\t-\t{stats['cpu_time']:.2f}")
        except Exception:
            print(f"{stats['nVar']}\t{stats['nConst']}\t{stats['nodes']}\t{stats['gap_str']}\t-\t{stats['cpu_time']}")
    else:
        print("-\t-\t-\t-\t-\t-  (Solver statistics not available)")


def get_solver_stats(results, model):
    """Extract solver statistics and return a dict or None if unavailable."""
    try:
        if not (hasattr(results, 'solver') and results.solver):
            return None

        nVar = len(list(model.component_data_objects(ctype=Var)))
        nConst = len(list(model.component_data_objects(ctype=Constraint)))

        nodes = getattr(results.solver, 'num_nodes', '-')
        cpu_time = getattr(results.solver, 'time', '-')

        gap = getattr(results.solver, 'gap', None)
        gap_str = f"{gap * 100:.4f}%" if gap is not None else '-'

        best_integer = getattr(results.problem, 'lower_bound', None)
        best_bound = getattr(results.problem, 'upper_bound', None)
        if best_integer is not None and best_bound is not None and best_integer != 0:
            gap = abs(best_integer - best_bound) / abs(best_integer)
            gap_str = f"{gap * 100:.4f}%"

        return {
            'nVar': nVar,
            'nConst': nConst,
            'nodes': nodes,
            'cpu_time': cpu_time,
            'gap_str': gap_str,
        }
    except Exception:
        return None


def gather_events(model, FlightData, All_Check_durations):
    """Collect flight and maintenance events from model into a standardized list.

    Returns list of dicts: {'aircraft','type','label','start','end','day'}
    """
    events = []
    for j in model.P:
        # Flights
        for i in model.F:
            try:
                if value(model.x[i, j]) > 0.5:
                    events.append({
                        'aircraft': j,
                        'type': 'flight',
                        'label': f'F{i}_d{FlightData[i]["day_departure"]}_{FlightData[i]["departureTime"]}_{FlightData[i]["arrivalTime"]}',
                        'start': FlightData[i]['departureTime'],
                        'end': FlightData[i]['arrivalTime'],
                        'day': FlightData[i]['day_departure']
                    })
            except Exception:
                # ignore failures to read values (unassigned vars etc.)
                continue

        # Maintenance
        for d in model.D:
            for c in model.C:
                try:
                    if value(model.y[j, d, c]) > 0.5:
                        duration = All_Check_durations[c]
                        dt = 0
                        for i in model.F:
                            if value(model.z[i, j, d, c]) > 0.5:
                                dt = FlightData[i]['arrivalTime']
                                break

                        events.append({
                            'aircraft': j,
                            'type': 'maintenance',
                            'label': f'M{c[0]}{d}_{dt}_{dt + All_Check_durations[c]}',
                            'start': dt,
                            'end': dt + duration,
                            'day': d
                        })
                except Exception:
                    continue

    return events



# parse_airline_data moved to data_io.py for testing/import reuse


# Example usage
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run tail assignment model over .dat files')
    parser.add_argument('--no-equipment-turn', action='store_true', help='Disable equipment turn (continuity) constraints')
    parser.add_argument('--no-maint-block', action='store_true', help='Disable maintenance blocking constraints')
    parser.add_argument('--solver', default='cplex', help='Solver name to use (default: cplex)')
    args = parser.parse_args()

    ADD_EQUIPMENT_TURN = not args.no_equipment_turn
    ADD_MAINT_BLOCK = not args.no_maint_block

    # TEST_DIR = "TestsData"
    # os.makedirs(OUT_DIR, exist_ok=True)  # Create folder if is not exist
    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)


    for root, dirs, files in os.walk(TEST_DIR):
        for fname in files:
            if len(fname) > 3 and fname.endswith(".dat"):
                print("\nProcessing file:", fname)
                data = parse_airline_data(os.path.join(root,fname))

                output_file_txt = os.path.join(OUT_DIR, fname[:-4] + "_result.txt")
                output_file_pic = os.path.join(OUT_DIR, fname[:-4] + "_result.png")

                params = {}
                for part in fname.split('_'):
                    if '=' in part:
                        key, val = part.split('=', 1)
                        params[key] = val

                density = float(params.get('density', 0))
                p = int(params.get('p', 0))
                h = int(params.get('h', 0))

                test_index = int(fname[-5])

                if DPHT is not None:
                    if density != DPHT[0] or p != DPHT[1] or h != DPHT[2] or test_index != DPHT[3]:
                        continue


                Airports = data["Airports"]
                Nbflight = data["Nbflight"]
                Aircrafts = data["Aircrafts"]

                # Access parsed data
                if DEBUG:
                    print("Airports:", data["Airports"])
                    print("Number of flights:", data["Nbflight"])
                    print("Flight details:")
                    for val in data["Flight"]:
                        print(val, ",")
                    print("Cost matrix sample:", data["cost"])
                    print("Initial aircraft positions:", data["a0"])
                    print("Aircrafts", Aircrafts)

                Flights = list(range(1, Nbflight + 1))

                MA = sorted(Airports)  # Consider Maintenance everywhere

                # Flight Information
                Flight = data["Flight"]

                if DEBUG:
                    for f in Flight:
                        print(f)

                # Derived FlightData
                FlightData = {
                    f["flight"]: {
                        "origin": f["origin"],
                        "destination": f["destination"],
                        "departureTime": f["departureTime"],
                        "arrivalTime": f["arrivalTime"],
                        "duration": f["arrivalTime"] - f["departureTime"],
                        "day_departure": int(f["departureTime"] // (DayShift * 60)) + 1,
                        "day_arrival": int(f["arrivalTime"] // (DayShift * 60)) + 1,
                    } for f in Flight
                }

                if DEBUG:
                    for i,it in FlightData.items():
                        print(i, it)
                    # input()

                cost = data["cost"]
                AircraftInit = data["a0"]

                MAX_DAYS = max([y["day_arrival"] for x,y in FlightData.items()]) + 1

                MAX_DAYS = max(8, MAX_DAYS)

                Days = list(range(1, MAX_DAYS * int(24.1 / DayShift)))

                if DEBUG:
                    print("MAx  days:", MAX_DAYS)
                    print("COST:")
                    print(cost[:2])
                    print("Initial positions")
                    print(AircraftInit)

                # All_Check_List = ["Acheck"]

                mc = {(i, j, d): 100 for i in Flights for j in Aircrafts for d in Days}  # dummy maintenance cost

                # Maintenance capacity
                mcap = {(m, d): 2 for m in MA for d in Days}  # dummy capacity

                # Helper functions
                F_m = {m: [i for i in Flights if FlightData[i]["destination"] == m] for m in MA}  # The set of flights which departs from airport m

                F_arr_k = {k: [i for i in Flights if FlightData[i]["destination"] == k] for k in sorted(Airports)}  # The set of flights which land in airport k
                F_dep_k = {k: [i for i in Flights if FlightData[i]["origin"] == k] for k in sorted(Airports)}  # The set of flights which departs from airport k

                # The set of flights which land in airport k before time t
                F_arr_t = lambda k, t, delta: [i for i in F_arr_k[k] if FlightData[i]["arrivalTime"] <= t - delta]
                # The set of flights which land in airport k before time t
                F_dep_t = lambda k, t: [i for i in F_dep_k[k] if FlightData[i]["departureTime"] < t]
                # The set of flights which land in airport k after t and before time t1
                F_dep_t_t1 = lambda k, t, t1: [i for i in F_dep_k[k] if FlightData[i]["departureTime"] > t and FlightData[i]["departureTime"] <= t1]

                # The set of flights for a given day
                F_d = {d: [i for i in Flights if FlightData[i]["day_departure"] == d] for d in Days}
                # The set of flights for a given day interval
                F_d_next = lambda d1, d2: [i for i in Flights if d1 < FlightData[i]["day_departure"] <= d2]
                # The set of flights for a given day when departureTime greater than arrivalTime of given flight
                F_d_i = lambda d, i: [i2 for i2 in Flights if FlightData[i2]["day_departure"] == d and FlightData[i2]["departureTime"] > FlightData[i]["arrivalTime"]]

                # Build full model using canonical builder
                # Consolidate parameters into a single Params object and pass it to the builder
                params_obj = Params(
                    All_Check_List=All_Check_List,
                    All_Checks=All_Checks,
                    All_Check_days=All_Check_days,
                    All_Check_Done_hours=All_Check_Done_hours,
                    All_Check_durations=All_Check_durations,
                    All_Check_durations_days=All_Check_durations_days,
                    All_Checks_Done_Days=All_Checks_Done_Days,
                    Mbig=Mbig,
                    mcap=mcap,
                )

                # Build the canonical model in improved_model.py and request the
                # specific maintenance/equipment constraint groups according to
                # the flags set at the top of this script. This avoids
                # duplicating the same constraint-building logic here.
                model, FlightData, Days, AircraftInit = build_full_model(
                    data,
                    min_turn=min_turn,
                    add_equipment_turn=ADD_EQUIPMENT_TURN,
                    add_maint_block=ADD_MAINT_BLOCK,
                    params=params_obj,
                    # map local boolean flags to the builder's feature toggles
                    enable_z_check=USE_CHECKS_SANITY,
                    enable_maint_spacing=USE_DAYS_CHECKS,
                    enable_maint_spacing2=USE_EXISTING_DAYS_CHECKS,
                    enable_maint_cumulative=(USE_PAPER_HRS_CHECK or USE_UPDATED_HRS_CHECKS),
                    enable_maint_cumulative_start=USE_EXISTING_HRS_CHECK,
                    enable_maint_block_checks=True,
                    enable_maint_checks_days=True,
                    enable_maint_capacity=True,
                    enable_maint_link=True,
                    enable_maint_hierarchy=USE_CHECK_HIERARCHY,
                    enable_overlap_checks=USE_OVERLAP_CHECKS,
                )

                # Recompute helper structures (F_m etc.) since builder returns its own FlightData/Days
                cost = data.get("cost", [])
                Flights = list(range(1, data["Nbflight"] + 1))
                MA = sorted(Airports)
                F_m = {m: [i for i in Flights if FlightData[i]["destination"] == m] for m in MA}

                # keep local aliases used by the rest of the script
                turn_time = min_turn
                flight_data = FlightData
                flight_arr = {k: [i for i in model.F if FlightData[i]['destination'] == k] for k in model.A}

                # Override/define the full objective (assignment + maintenance cost)
                model.obj = Objective(
                    expr=sum(cost[i-1][j-1] * model.x[i, j] for i in model.F for j in model.P) +
                         sum((mc[i, j, d] + get_premature_penalty(check, d)) * model.z[i, j, d, check]
                             for m in model.MA for i in F_m[m] for j in model.P for d in model.D for check in model.C)
                    ,
                    sense=minimize
                )


                # Solve and print summary (encapsulated for testing)
                results = solve_model(model, solver_name='cplex')
                print_solver_summary(model, results)
                print(model)
                print(results)


                def parse_root_gap(log_text):
                    # Pattern for root node gap report
                    pattern = r"Root node solution \(.*?\): ([\d.]+) \(gap = ([\d.]+)%\)"
                    match = re.search(pattern, log_text)
                    if match:
                        root_obj = float(match.group(1))
                        root_gap = float(match.group(2))
                        return root_gap
                    return None


                # Print termination status
                term_cond = results.solver.termination_condition
                print(f"\nTermination Condition: {term_cond}")
                if term_cond != TerminationCondition.optimal:
                    print("Warning: Solution is not optimal!")

                print("\nAssignment Results:")
                for i in model.F:
                    for j in model.P:
                        if value(model.x[i, j]) > 0.5:
                            print(f"Flight {i} assigned to Plane {j}")

                        for d in model.D:
                            for c in model.C:
                                if value(model.z[i, j, d, c]) > 0.5:
                                    print(f"In this flight Plane {j} goes to check {c[0]} on day {d}")
                                # (value(model.y[j, d, c]),end=",")
                            # print("\t",end="")

                print(f"Total Cost: {value(model.obj)}")



                # Use helper functions to write report and plot schedule
                write_text_report(model, results, FlightData, output_file_txt)
                events = plot_schedule_from_model(model, FlightData, output_file_pic)

                if CNT_FILE > 0:
                    input()

#             if CNT_FILE > 0:
#                 break
# #
# # Capture solver log
# with open('cplex.log', 'w') as log_file:
#     results = solver.solve(model, tee=True, logfile='cplex.log')
#
# # Parse log
# with open('cplex.log', 'r') as f:
#     log_text = f.read()
#     root_gap = parse_root_gap(log_text)
#     print("Root gap", root_gap)
