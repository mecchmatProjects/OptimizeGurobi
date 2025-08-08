import os
import re
from collections import defaultdict


from pyomo.environ import *
from pyomo.opt import SolverFactory


DEBUG = False
CNT_FILE = True

USE_PAPER_HRS_CHECK = True  # Use check for maintenances as in paper
USE_UPDATED_HRS_CHECKS = False  # Use check updated version for maintenances
USE_EXISTING_HRS_CHECK = True  # Use hrs check counting of elapsed flight hrs

USE_DAYS_CHECKS = True  # Use check version for maintenances with days threshold
USE_EXISTING_DAYS_CHECKS = True   # Use check version for maintenances with days threshold with elapsed days

USE_CHECK_HIERARCHY = False  # If we use D check - we reload other checks too, C check - reloads A,B, B - reloads A

# Inputs ---

TEST_DIR = "TestsData"
OUT_DIR = "OUT2"

DayShift = 24  # Consider shift as day with 24 hrs

# Flying-Hours since last check
Acheck = {0: 50.0, 1: 55.0, 2: 59.0, 3: 20.0, 4: 20.0, 5: 20.0, 6: 20.0, 7: 20.0, 8: 20.0, 9: 20.0}
Bcheck = {0: 20.0, 1: 20.0, 2: 20.0, 3: 20.0, 4: 20.0, 5: 20.0, 6: 20.0, 7: 20.0, 8: 20.0, 9: 20.0}
Ccheck = {0: 20.0, 1: 20.0, 2: 20.0, 3: 20.0, 4: 20.0, 5: 20.0, 6: 20.0, 7: 20.0, 8: 20.0, 9: 20.0}
Dcheck = {0: 20.0, 1: 20.0, 2: 20.0, 3: 20.0, 4: 20.0, 5: 20.0, 6: 20.0, 7: 20.0, 8: 20.0, 9: 20.0}

#Elapsed days since last check
Acheck_days = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}
Bcheck_days = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}
Ccheck_days = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}
Dcheck_days = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}

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
A_check_hours = 10*6
B_check_hours = 30*6
C_check_hours = 540 * 8
D_check_hours = 1825 * 8

# Maintenance thresholds in elapsed days
# USE_DAYS_CHECKS
A_check_days = 10
B_check_days = 30
C_check_days = 540
D_check_days = 1825

# Maintenance durations in minutes
A_check_duration = 8 * 60
B_check_duration = 16 * 60
C_check_duration = 5 * 24 * 60
D_check_duration = 10 * 24 * 60

# Maintenance durations for days
A_check_duration_days = 1
B_check_duration_days = 1
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
    All_Check_List[0]: 5,
    All_Check_List[1]: 10,
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
    All_Check_List[0]: Acheck_days,
    All_Check_List[1]: Bcheck_days,
    All_Check_List[2]: Ccheck_days,
    All_Check_List[3]: Dcheck_days
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

All_Check_durations_days = {
    All_Check_List[0]: A_check_duration_days,
    All_Check_List[1]: B_check_duration_days,
    All_Check_List[2]: C_check_duration_days,
    All_Check_List[3]: D_check_duration_days
}


def parse_airline_data(file_path):
    with open(file_path, 'r') as f:
        content = f.read()

    # Helper function to parse sets
    def parse_set(s):
        return [x.strip() for x in re.findall(r'(\w+)', s)]

    # Helper function to parse tuples
    def parse_tuples(s):
        return [tuple(x.split(',')) for x in re.findall(r'<([^>]+)>', s)]

    # Helper function to parse matrix
    def parse_matrix(s):
        return [
            [float(x.strip()) for x in row.split(',') if x.strip()]
            for row in re.findall(r'\[([^\]]*)\][,\s]*', s)
        ]

    # Parse Airports
    airports_match = re.search(r'Airports\s*=\s*{([^}]+)};', content)
    Airports = parse_set(airports_match.group(1)) if airports_match else []

    # Parse Nbflight
    nbflight_match = re.search(r'Nbflight\s*=\s*(\d+);', content)
    Nbflight = int(nbflight_match.group(1)) if nbflight_match else 0
    Flights = list(range(1, Nbflight + 1))

    # Parse Aircrafts
    aircrafts_match = re.search(r'Aircrafts\s*=\s*{([^}]+)};', content)
    Aircrafts = parse_set(aircrafts_match.group(1)) if aircrafts_match else []
    Aircrafts = [int(x) for x in Aircrafts]

    # Parse Flight data
    flight_match = re.search(r'Flight\s*=\s*{([^}]+)};', content, re.DOTALL)
    flight_tuples = parse_tuples(flight_match.group(1)) if flight_match else []
    Flight = []
    for t in flight_tuples:
        parts = [x.strip() for x in t]
        if len(parts) >= 5:
            Flight.append({
                "flight": int(parts[0]),
                "origin": parts[1],
                "destination": parts[2],
                "departureTime": float(parts[3]),
                "arrivalTime": float(parts[4])
            })


    # Parse Cost matrix
    cost_match = re.search(r'Cost\s*=\s*\[(.*?)\]\s*;', content, re.DOTALL)
    cost = parse_matrix(cost_match.group(1)) if cost_match else []

    # Parse Aircraft initial positions
    aircraft_match = re.search(r'Aircraft\s*=\s*\[([^\]]+)\];', content)
    aircraft_tuples = parse_tuples(aircraft_match.group(1)) if aircraft_match else []
    a0 = {}
    for t in aircraft_tuples:
        parts = [x.strip() for x in t]
        if len(parts) >= 2:
            a0[int(parts[0])] = parts[1]

    # Parse checks

    return {
        "Airports": Airports,
        "Nbflight": Nbflight,
        "Flights": Flights,
        "Flight": Flight,
        "Aircrafts": Aircrafts,
        "cost": cost,
        "a0": a0,
    }


# Example usage
if __name__ == "__main__":

    TEST_DIR = "TestsData"
    OUT_DIR = "OUT"
    os.makedirs(OUT_DIR, exist_ok=True)  # Create folder if is not exist

    for root, dirs, files in os.walk(TEST_DIR):
        for fname in files:
            if len(fname) > 3 and fname.endswith(".dat"):
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
                F_d_i = lambda d, i: [i2 for i2 in Flights if FlightData[i]["day_departure"] == d and FlightData[i2]["departureTime"] > FlightData[i]["arrivalTime"]]


                # Define model
                model = ConcreteModel()

                # Define indices
                model.F = Set(initialize=Flights)
                model.P = Set(initialize=sorted(Aircrafts))
                model.A = Set(initialize=sorted(Airports))
                # model.A = Set(initialize=list(set(f['origin'] for f in FlightData.values()).union(set(f['destination'] for f in FlightData.values()))))
                # print(model.A)

                model.D = Set(initialize=sorted(Days))
                model.MA = Set(initialize=sorted(MA))
                model.C = Set(initialize=sorted(All_Check_List))

                # print([j for j in model.P])

                # Define variables
                model.x = Var(model.F, model.P, domain=Binary, initialize=0)
                model.z = Var(model.F, model.P, model.D, model.C, domain=Binary, initialize=0)
                model.y = Var(model.P, model.D, model.C, domain=Binary, initialize=0)
                model.mega_check = Var(model.P, model.D, model.C, domain=Binary, initialize=0)

                # Define objective (7)
                model.obj = Objective(
                    expr=sum(cost[i-1][j-1] * model.x[i, j] for i in model.F for j in model.P) +
                         sum((mc[i, j, d] + Premature_Check_penalty[check][(All_Check_days[check] - d)%5]) * model.z[i, j, d, check]
                             for m in model.MA for i in F_m[m] for j in model.P for d in model.D for check in model.C)
                    ,
                    sense=minimize
                )

                # Constraint C1  (1)
                model.c1 = ConstraintList()
                for i in model.F:
                    model.c1.add(sum(model.x[i, j] for j in model.P) == 1)

                # Replacing c23 with corrected equipment_turn_constraints
                turn_time = min_turn
                flight_data = FlightData
                flight_arr = {k: [i for i in model.F if FlightData[i]['destination'] == k] for k in model.A}

                # Constraints (2)-(3)
                model.equipment_turn_constraints = ConstraintList()
                for j in model.P:
                    for k in model.A:
                        for i in F_dep_k[k]:
                            t_dep = flight_data[i]['departureTime']
                            lhs_geq = sum(model.x[i1, j] for i1 in F_arr_t(k, t_dep, turn_time))
                            lhs_lt = sum(model.x[i1, j] for i1 in F_dep_t(k, t_dep))

                            #
                            if DEBUG:
                                print("ijk", i, j, k, end=":")
                                print(t_dep, end="\t")
                                print(F_arr_t(k, t_dep, turn_time), lhs_geq, end="\t")
                                print(F_dep_t(k, t_dep), lhs_lt)

                            if k != AircraftInit[j]:
                                model.equipment_turn_constraints.add(lhs_geq - lhs_lt >= model.x[i, j])
                            else:
                                model.equipment_turn_constraints.add(lhs_geq - lhs_lt >= model.x[i, j] - 1)


                # Constraint (8)
                # Maintenance blocks flights
                model.maint_last = ConstraintList()
                for check in model.C:
                    for i in model.F:
                        for j in model.P:
                            for d in model.D:
                                for i2 in F_d_i(d, i):
                                    model.maint_last.add(model.z[i, j, d, check] + model.x[i2, j] <= 1)

                # Constraint (9)
                # Activation for flights: we have to fly for check
                model.maint_assignment = ConstraintList()
                for check in model.C:
                    for i in model.F:
                        for j in model.P:
                            for d in model.D:
                                model.maint_assignment.add(model.x[i, j] >= model.z[i, j, d, check])

                # Constraint (10)
                # Capacity limits for maintenances
                model.maint_capacity = ConstraintList()
                for check in model.C:
                    for d in model.D:
                        for m in model.MA:
                            relevant_flights = F_m.get(m, [])
                            if relevant_flights:
                                model.maint_capacity.add(
                                    sum(model.z[i, j, d, check] for i in relevant_flights for j in model.P) <= mcap[m, d]
                                )

                # Constraint (11)
                # Activation for maintenances checks
                model.maint_link = ConstraintList()
                for check in model.C:
                    for d in model.D:
                        #for m in model.MA:
                        for j in model.P:
                            # print(j, d, m, F_m[m])
                            model.maint_link.add(sum(model.z[i, j, d, check] for i in Flights if FlightData[i]["destination"] in MA) == model.y[j, d, check])


                model.maint_hierarchy = ConstraintList()

                CHECK_HIERARCHY ={
                    "Acheck": ["Acheck", "Bcheck", "Ccheck", "Dcheck"],
                    "Bcheck": ["Bcheck", "Ccheck", "Dcheck"],
                    "Ccheck": ["Ccheck", "Dcheck"],
                    "Dcheck": ["Dcheck"]
                }

                if USE_CHECK_HIERARCHY:
                    for j in model.P:
                        for d in model.D:
                            for c in model.C:
                                model.maint_hierarchy.add(model.mega_check[j, d, c] ==
                                                          sum(model.y[j, d, check] for check in CHECK_HIERARCHY[c]))
                else:
                    for j in model.P:
                        for d in model.D:
                            for c in model.C:
                                model.maint_hierarchy.add(model.mega_check[j, d, c] == model.y[j, d, c])


                # Constraint (12)
                # We have checks in All_Check_days interval
                if USE_DAYS_CHECKS:
                    model.maint_spacing = ConstraintList()
                    for check in All_Check_List:
                        for j in model.P:
                            # print("j=",j, All_Check_days[check], len(Days) -1)
                            for start in range(0, len(Days)- All_Check_days[check]-1):
                                if DEBUG:
                                    print("checks", start, min(start + All_Check_days[check], len(Days)-1), Days[start:start + All_Check_days[check]])
                                model.maint_spacing.add(sum(model.mega_check[j, r, check] for r in Days[start:start + All_Check_days[check]]) >= 1)

                # Constraint (12 and 14 for C-D checks) we check regarding previous unchecked days
                # We need checks regarding our check days remained
                if USE_EXISTING_DAYS_CHECKS:
                    model.maint_spacing2 = ConstraintList()
                    for check in All_Check_List:
                        for j in model.P:
                            days_without_checks = int(All_Check_days[check] - All_Checks_Done_Days[check][j])
                            if days_without_checks >= len(model.D):
                                continue
                            if DEBUG:
                                print("days check", days_without_checks)
                            model.maint_spacing2.add(sum(model.mega_check[j, r, check] for r in Days[:days_without_checks]) >= 1)


                # Constraint (13)
                # Planes could not fly without checks for All_Check_Done_hours
                model.maint_cumulative = ConstraintList()
                for check in All_Check_List:
                    for j in model.P:
                        for start in range(len(Days) - 1):
                            for end in range(start + 2, min(start + All_Check_days[check], len(Days))):
                                d = Days[start]
                                d_ = Days[end]
                                t_sum = sum(FlightData[i]['duration'] * model.x[i, j] for i in F_d_next(d, d_))
                                y_sum = sum(model.mega_check[j, r, check] for r in Days[start+1:end])
                                if USE_PAPER_HRS_CHECK:
                                    # This is paper constraint (13) - however, it seems to be Wrong???!!!
                                    model.maint_cumulative.add(t_sum <= All_Check_Done_hours[check]*60 + Mbig * y_sum +
                                                                Mbig*(2 - model.mega_check[j, d, check] - model.mega_check[j, d_, check]) )
                                elif USE_UPDATED_HRS_CHECKS:
                                    # Corrected version:: either y_sum or y[j,start] and y[j,end]
                                    model.maint_cumulative.add(t_sum <= All_Check_Done_hours[check] * 60 + Mbig * y_sum + Mbig * model.mega_check[j, d, check])
                                    model.maint_cumulative.add(t_sum <= All_Check_Done_hours[check] * 60 + Mbig * y_sum + Mbig * model.mega_check[j, d_, check])


                # Constraint 13-1
                # Constraint for counting previous flight hours before start - my version
                # Planes could not fly without checks for All_Check_Done_hours - Previous flight hours without checks
                if USE_EXISTING_HRS_CHECK:
                    model.maint_cumulative_start = ConstraintList()
                    for check in All_Check_List:
                        for j in model.P:
                            for end in range(1, min(len(Days)-1, All_Check_days[check])):
                                d = Days[0]
                                d_ = Days[end]
                                t_sum = sum(FlightData[i]['duration'] * model.x[i, j] for i in F_d_next(0, d_))
                                y_sum = sum(model.mega_check[j, r, check] for r in Days[:end])
                                if DEBUG:
                                    print("Plane ", j, "unchecked hrs", All_Check_Done_hours[check], All_Checks[check][j], "start/end days",d, d_)
                                # Flight minutes is small or we have either y_sum or y[j,end]
                                model.maint_cumulative_start.add(t_sum <= (All_Check_Done_hours[check] - All_Checks[check][j]) * 60 +
                                                                 Mbig * y_sum +
                                                                 Mbig * model.mega_check[j, d_, check])

                # Constraint 14??
                # Constraint - my version of no double check
                # We can have only one check simultenuosly per one day
                model.maint_block_checks = ConstraintList()
                for j in model.P:
                    for d in model.D:
                        model.maint_block_checks.add(sum(model.y[j, d, check] for check in All_Check_List) <= 1)


                # Constraint 14-1
                # Constraint - my version of check length
                # C-D checks last for All_Check_durations_days
                model.maint_checks_days = ConstraintList()
                for j in model.P:
                    for check in All_Check_List:
                        if All_Check_durations_days[check] == 0:
                            continue

                        for d in range(len(Days)):
                            K = min(d + All_Check_durations_days[check], len(Days))
                            if DEBUG:
                                print([Days[x] for x in range(d + 1, K)])
                            if d==0:
                                model.maint_checks_days.add(
                                    sum(model.mega_check[j, Days[d1], check] for d1 in range(1, K)) +
                                    Mbig * (1 - model.mega_check[j, Days[0], check]) >= K-1)
                                continue
                            if d>=K:
                                 continue

                            model.maint_checks_days.add(sum(model.mega_check[j, Days[d1], check] for d1 in range(d + 1, K)) +
                                                        Mbig * model.mega_check[j, Days[d - 1], check] +
                                                        Mbig * (1 - model.mega_check[j, Days[d], check]) >= K - d - 1)

                # Version of CPLEX sent - not sure they are correct
                # Constraint no flight during checks
                # for j in model.P:
                #     for d in model.D:
                #         for k in model.A:
                #             for i in F_dep_k[k]:
                #                 if flight_data[i]['day'] !=d:
                #                     continue
                #
                #                 t_dep = flight_data[i]['departureTime']
                #
                #                 for check in All_Check_List:
                #                     lhs_lt = sum(model.x[i1, j] for i1 in F_dep_t_t1(k,t_dep, t_dep + All_Check_durations[check]))
                #                     model.maint_block_flights.add(lhs_lt <= Mbig * model.y[j, d, check])

                # for j in model.P:
                #     for d in model.D:
                #         for i in model.F:
                #             t_dep = flight_data[i]['departureTime']
                #             if flight_data[i]['day'] < d:
                #                 continue
                #
                #             for check in model.C:
                #                 if t_dep < d * 24 * 60 + All_Check_durations[check]:
                #                     print(j,i,d,check)
                #                     model.maint_block_flights.add(model.x[i, j] + model.y[j, d, check] <=1)

                # Constraint (15)
                # Constraint no flight during checks - my version\
                # For checks A-B hours
                model.maint_block_flights = ConstraintList()
                for check in model.C:
                    for i in model.F:
                        t_arr = flight_data[i]['arrivalTime']
                        day = flight_data[i]['day_arrival']
                        airport = flight_data[i]['destination']
                        if airport not in MA:
                            continue

                        for j in model.P:
                            if DEBUG:  # or check=="Bcheck" and j==0:
                                print("figths", i, "plane", j, "port", airport, "day", day, "t:", t_arr, t_arr + All_Check_durations[check],
                                      F_dep_t_t1(airport, t_arr, t_arr + All_Check_durations[check]))
                            for i2 in F_dep_t_t1(airport, t_arr, t_arr + All_Check_durations[check]):
                                if DEBUG:
                                    print(i,j,day,check,i2,j)
                                #for d in range(day, min(day + 2, Days[-1])):
                                day2 = flight_data[i2]['day_departure']

                                model.maint_block_flights.add(model.z[i, j, day, check] + model.x[i2, j] <= 1)
                                # if day == 1 and All_Check_durations_days[check] > 1:
                                #     model.maint_block_flights.add(model.y[j, day, check] + model.x[i2, j] <= 1)

                    t_arr = 0
                    day = Days[0]

                    for airport in AircraftInit.values():

                        if airport not in MA:
                            continue

                        for j in model.P:
                            if DEBUG: #  or check == "Bcheck" and j == 0
                                print("figths", i, "plane", j, "port", airport, "day", day, "t:", t_arr, t_arr + All_Check_durations[check],
                                      F_dep_t_t1(airport, t_arr, t_arr + All_Check_durations[check]))
                            for i2 in F_dep_t_t1(airport, 0, All_Check_durations[check]):
                                if DEBUG:
                                    print(i, j, day, check, i2, j)
                                # for d in range(day, min(day + 1, Days[-1])):
                                model.maint_block_flights.add(model.mega_check[j, day, check] + model.x[i2, j] <= 1)


                # Constraint (15-1)
                # Constraint no flight during checks - my version
                # For checks C-D days
                model.maint_block_flights_days = ConstraintList()
                for check in model.C:
                    if All_Check_durations_days[check] <= 1:
                        continue
                    for i in model.F:
                        day = flight_data[i]['day_departure']
                        if DEBUG:
                            print("day", day)

                        airport = flight_data[i]['origin']
                        if airport not in MA:
                            continue

                        for j in model.P:
                            if DEBUG:
                                print("Check fligths", i, "plane", j, "port", airport, "day", day, "t:", t_arr, t_arr +
                                      All_Check_durations[check], F_dep_t_t1(airport, t_arr, t_arr + All_Check_durations[check]))
                            if day>Days[0]:
                                # model.maint_block_flights_days.add(model.y[j, day-1, check] + model.y[j, day, check] + model.x[i, j] <= 2)
                                model.maint_block_flights_days.add(
                                    model.y[j, day, check] + model.x[i, j] <= 1)



                # Solve
                solver = SolverFactory('cplex')  # Or 'cbc', 'glpk', etc.
                # solver.set_executable('D:/CPLEX/cplex/bin/x64_win64/cplex.exe')
                results = solver.solve(model)
                # Extract and print solver statistics

                print("\n# # # Residual Gap at CPU # # Residual Gap at CPU")
                print("Var\tConst\tNodes\tgap (%)\troot (%)\t(sec)")

                if hasattr(results, 'solver') and results.solver:
                    # Extract basic statistics
                    nVar = len(list(model.component_data_objects(ctype=Var)))
                    nConst = len(list(model.component_data_objects(ctype=Constraint)))

                    # Extract solver-specific statistics
                    nodes = getattr(results.solver, 'num_nodes', '-')

                    cpu_time = getattr(results.solver, 'time', '-')

                    # Extract and format gap
                    gap = getattr(results.solver, 'gap', None)
                    gap_str = f"{gap * 100:.4f}%" if gap is not None else '-'

                    # Manually calculate gap if attribute not available
                    best_integer = results.problem.lower_bound
                    best_bound = results.problem.upper_bound
                    if best_integer is not None and best_bound is not None:
                        gap = abs(best_integer - best_bound) / abs(best_integer)
                        gap_str = f"{gap * 100:.4f}%" if gap is not None else '-'

                    # Print statistics row
                    print(f"{nVar}\t{nConst}\t{nodes}\t{gap_str}\t-\t{cpu_time:.2f}")
                else:
                    print("-\t-\t-\t-\t-\t-  (Solver statistics not available)")
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



                with open(output_file_txt,"w") as file_out:
                    print("File", output_file_txt)

                    print("\nAircraft Assignment and Maintenance Report:\n", file=file_out)

                    print("\n# # # Residual Gap at CPU # # Residual Gap at CPU", file=file_out)
                    print("Var\tConst\tNodes\tgap (%)\troot (%)\t(sec)", file=file_out)

                    if hasattr(results, 'solver') and results.solver:
                        # Extract basic statistics
                        nVar = len(list(model.component_data_objects(ctype=Var)))
                        nConst = len(list(model.component_data_objects(ctype=Constraint)))

                        # Extract solver-specific statistics
                        nodes = getattr(results.solver, 'num_nodes', '---')
                        cpu_time = getattr(results.solver, 'time', '---')

                        # # Extract and format gap
                        # gap = getattr(results.solver, 'gap', None)
                        # gap_str = f"{gap * 100:.4f}%" if gap is not None else '-'

                        # Manually calculate gap if attribute not available
                        best_integer = results.problem.lower_bound
                        best_bound = results.problem.upper_bound
                        if best_integer is not None and best_bound is not None:
                            gap = abs(best_integer - best_bound) / abs(best_integer)
                            gap_str = f"{gap * 100:.4f}%" if gap is not None else '----'

                        # Print statistics row
                        print(f"{nVar:8}\t{nConst:10}\t{nodes}\t{gap_str}\t-\t{cpu_time:.2f}", file=file_out)
                    else:
                        print("-\t-\t-\t-\t-\t-  (Solver statistics not available)", file=file_out)

                    for j in model.P:
                        events = []
                        events2 = []
                        # Gather all assigned flights for this aircraft (use departure time for sorting)
                        for i in model.F:
                            if value(model.x[i, j]) > 0.5:
                                events.append((FlightData[i]['departureTime'],
                                               f"F{i}_d{FlightData[i]['day_departure']}_{FlightData[i]['departureTime']}_{FlightData[i]['arrivalTime']}"))
                                events2.append((FlightData[i]['departureTime'],
                                               f"F{i}_d{FlightData[i]['day_departure']}_{FlightData[i]['departureTime']}_{FlightData[i]['arrivalTime']}"))
                        # Gather all maintenance events for this aircraft (use day for sorting, ensure it follows flights on the same day)
                        for d in model.D:
                            for c in model.C:
                                if value(model.y[j, d, c]) > 0.5:
                                    dt = 0
                                    for i in model.F:

                                        # day = flight_data[i]['day_arrival']
                                        # if day != d:
                                        #     continue
                                        # airport = flight_data[i]['destination']
                                        # if airport not in MA:
                                        #     continue

                                        if value(model.z[i, j, d, c])>0.5:
                                            t_arr = flight_data[i]['arrivalTime']
                                            dt = t_arr
                                            break

                                    # Use a large offset to sort maintenance after all flights on the same day
                                    events.append((d * 1e6, f"M{c[0]}{d}_{dt}_{dt + All_Check_durations[c]}"))
                                    events2.append((dt, f"M{c[0]}{d}_{dt}_{dt + All_Check_durations[c]}"))
                        # Sort all events chronologically
                        events.sort()
                        # Format output
                        events_str = ", ".join([e[1] for e in events])
                        print(f"Aircraft {j}: {events_str}")

                        events2.sort()
                        # Format output
                        events2_str = ", ".join([e[1] for e in events2])
                        print(f"Aircraft {j}: {events2_str}", file=file_out)

                    import matplotlib.pyplot as plt
                    import matplotlib.patches as mpatches

                    # Prepare data (replace with your actual solution extraction)
                    events = []
                    for j in model.P:
                        # Flights
                        for i in model.F:
                            if value(model.x[i, j]) > 0.5:
                                events.append({
                                    'aircraft': j,
                                    'type': 'flight',
                                    'label': f'F{i}',
                                    'start': FlightData[i]['departureTime'],
                                    'end': FlightData[i]['arrivalTime'],
                                    'day': FlightData[i]['day_departure']
                                })
                        # Maintenance
                        for d in model.D:
                            for c in model.C:
                                if value(model.y[j, d, c]) > 0.5:
                                    duration = All_Check_durations[c]
                                    dt = 0
                                    for i in model.F:

                                        # day = flight_data[i]['day_arrival']
                                        # if day != d:
                                        #     continue
                                        # airport = flight_data[i]['destination']
                                        # if airport not in MA:
                                        #     continue

                                        if value(model.z[i, j, d, c])>0.5:
                                            t_arr = flight_data[i]['arrivalTime']
                                            dt = t_arr
                                            break

                                    # if All_Check_durations_days[c] <= 1:
                                    #     dt += 24*60

                                    events.append({
                                        'aircraft': j,
                                        'type': 'maintenance',
                                        'label': f'M{c[0]}{d}_{(d-1) * 24 * 60 + dt}',
                                        'start': dt,
                                        'end':  dt + duration,
                                        'day':  d
                                    })

                    # Sort by aircraft and start time
                    events.sort(key=lambda x: (x['aircraft'], x['start']))

                    # Plotting
                    fig, ax = plt.subplots(figsize=(15, 8))
                    flight_color = 'tab:blue'
                    maintenance_colors = {'A': 'tab:orange', 'B': 'tab:green', 'C': 'tab:red', 'D': 'tab:purple'}
                    aircraft_positions = {j: idx for idx, j in enumerate(sorted(set(e['aircraft'] for e in events)))}

                    for e in events:
                        y = aircraft_positions[e['aircraft']]
                        color = flight_color if e['type'] == 'flight' else maintenance_colors[e['label'][1]]
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
                        print("save to ", output_file_pic)
                        plt.savefig(output_file_pic)
                    else:
                        plt.show()

                # if CNT_FILE > 0:
                #     input()

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
