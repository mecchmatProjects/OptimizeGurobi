# # -----------------------------
# # Basic Sets and Parameters
# # -----------------------------
#
# Airports = {"JFK", "ATL", "ORD", "MIA"}
# Nbflight = 6
# Aircrafts = {1, 2}
# Flights = range(1, Nbflight + 1)
# nDays = 7
# Days = range(1, nDays + 1)
#
# # -----------------------------
# # Flight Information
# # -----------------------------
#
# from collections import namedtuple
#
# FlightInfo = namedtuple("FlightInfo", ["flight", "origin", "destination", "departureTime", "arrivalTime"])
#
# Flight = {
#     FlightInfo(1, "JFK", "ATL", 480.0, 600.0),     # Day 1 08:00–10:00
#     FlightInfo(2, "ATL", "ORD", 720.0, 840.0),     # Day 1 12:00–14:00
#     FlightInfo(3, "ORD", "JFK", 1020.0, 1140.0),   # Day 1 17:00–19:00
#     FlightInfo(4, "JFK", "MIA", 1980.0, 2130.0),   # Day 2 09:00–11:30
#     FlightInfo(5, "MIA", "ATL", 2400.0, 2580.0),   # Day 3 00:00–03:00
#     FlightInfo(6, "ATL", "JFK", 2940.0, 3120.0),   # Day 4 01:00–04:00
# }
#
# # -----------------------------
# # Aircraft Initial Locations
# # -----------------------------
#
# AircraftInitial = namedtuple("AircraftInitial", ["aircraftId", "initialAirport"])
#
# Aircraft = {
#     1: AircraftInitial(1, "JFK"),
#     2: AircraftInitial(2, "ATL"),
# }
#
# # -----------------------------
# # Initial Maintenance Counters
# # -----------------------------
#
# initialHoursSinceA = {
#     1: 120.0,
#     2: 240.0,
# }
#
# initialHoursSinceB = {
#     1: 300.0,
#     2: 100.0,
# }
#
# initialDaysSinceC = {
#     1: 180,
#     2: 270,
# }
#
# initialDaysSinceD = {
#     1: 700,
#     2: 1500,
# }
#
# # -----------------------------
# # Cost Matrix
# # -----------------------------
#
# Cost = {
#     1: {1: 100.0, 2: 105.0},
#     2: {1: 110.0, 2: 108.0},
#     3: {1: 115.0, 2: 120.0},
#     4: {1: 130.0, 2: 125.0},
#     5: {1: 140.0, 2: 138.0},
#     6: {1: 150.0, 2: 148.0},
# }
#
# # -----------------------------
# # Maintenance Parameters
# # -----------------------------
#
# MA = {"JFK", "ATL", "MIA"}  # Airports that can do maintenance
#
# dmax = 4
# Tmax = 64 * 60  # in minutes
# nu = 14
#
# mcap = {
#     "JFK": 5,
#     "ATL": 3,
#     "MIA": 4,
# }
#
# Mdd = 100000  # Big-M
# acmax = 6     # Max assignments
# atmax = 50    # Max total time (minutes or placeholder)
#
# # Maintenance thresholds
# A_check_hours = 400.0
# B_check_hours = 600.0
# C_check_days = 540
# D_check_days = 1825
#
# # Maintenance durations
# A_check_duration = 8 * 60
# B_check_duration = 16 * 60
# C_check_duration = 5
# D_check_duration = 10
#
# # -----------------------------
# # Pre-processing (Day, Duration)
# # -----------------------------
#
# CFlightInfo = namedtuple("CFlightInfo", ["flight", "origin", "destination", "departureTime", "arrivalTime", "day", "duration"])
# FlightData = {}
#
# for f in Flight:
#     day = int(f.arrivalTime // (24 * 60)) + 1
#     duration = f.arrivalTime - f.departureTime
#     FlightData[f.flight] = CFlightInfo(
#         flight=f.flight,
#         origin=f.origin,
#         destination=f.destination,
#         departureTime=f.departureTime,
#         arrivalTime=f.arrivalTime,
#         day=day,
#         duration=duration
#     )

from pyomo.environ import *
from datetime import datetime
import math

# ----------- INPUT DATA (CP style in Python) -----------

Airports = {"JFK", "ATL", "ORD", "MIA"}
Nbflight = 6
Aircrafts = {1, 2}
Flights = range(1, Nbflight + 1)
nDays = 7
Days = range(1, nDays + 1)

Flight = {
    1: ("JFK", "ATL", 480.0, 600.0),
    2: ("ATL", "ORD", 720.0, 840.0),
    3: ("ORD", "JFK", 1020.0, 1140.0),
    4: ("JFK", "MIA", 1980.0, 2130.0),
    5: ("MIA", "ATL", 2400.0, 2580.0),
    6: ("ATL", "JFK", 2940.0, 3120.0)
}

Aircraft = {
    1: "JFK",
    2: "ATL"
}

Cost = {
    1: {1: 100, 2: 105},
    2: {1: 110, 2: 108},
    3: {1: 115, 2: 120},
    4: {1: 130, 2: 125},
    5: {1: 140, 2: 138},
    6: {1: 150, 2: 148}
}

MA = {"JFK", "ATL", "MIA"}

mcap = {
    ("JFK", 1): 2, ("JFK", 2): 1,
    ("ATL", 1): 1, ("ATL", 2): 1,
    ("MIA", 2): 2
}

Tmax = 8 * 60  # minutes
nu = 15
dmax = 3
Mbig = 9999
min_turn = 30.0  # minutes

# ----------- Derived flight info -----------

t_dep = {i: Flight[i][2] for i in Flights}
t_arr = {i: Flight[i][3] for i in Flights}
a_dep = {i: Flight[i][0] for i in Flights}
a_arr = {i: Flight[i][1] for i in Flights}
day = {i: int(Flight[i][3] // (24 * 60)) + 1 for i in Flights}
duration = {i: Flight[i][3] - Flight[i][2] for i in Flights}

# Sets needed for continuity constraints
F_arr_k = {k: [i for i in Flights if a_arr[i] == k] for k in Airports}
F_ge_k = lambda k, t: [i for i in Flights if a_dep[i] == k and t_dep[i] <= t + min_turn]
F_lt_k = lambda k, t: [i for i in Flights if a_arr[i] == k and t_arr[i] < t]
F_m = {m: [i for i in Flights if a_arr[i] == m] for m in MA}
F_d = {d: [i for i in Flights if day[i] == d] for d in Days}
F_d_next = lambda d1, d2: [i for i in Flights if d1 < day[i] <= d2]
F_d_i = lambda d, i: [i2 for i2 in Flights if day[i2] == d and t_arr[i2] > t_arr[i]]


# ----------- Pyomo Model -----------

model = ConcreteModel()

model.F = Set(initialize=Flights)
model.P = Set(initialize=Aircrafts)
model.A = Set(initialize=range(1,7))
model.D = Set(initialize=Days)
model.MA = Set(initialize=MA)

model.x = Var(model.F, model.P, domain=Binary)
model.z = Var(model.F, model.P, model.D, domain=Binary)
model.y = Var(model.P, model.D, domain=Binary)


mc = {(i, j, d): 100 for i in model.F for j in model.P for d in model.D}  # example uniform cost

# Objective
model.obj = Objective(
    expr=sum(Cost[i][j] * model.x[i, j] for i in Flights for j in Aircrafts) +
         sum(mc[(i, j, d)] * model.z[i, j, d] for m in MA for i in F_m[m] for j in Aircrafts for d in Days),
    sense=minimize
)

# Helper functions for constraints (4) and (5)
# def F_geq_k(k, t):
#     # print(flight_data,t)
#     return [i for i, f in flight_data.items() if f['a2'] == k and f['t2'] <= t + turn_time]
#
# def F_lt_k(k, t):
#     return [i for i, f in flight_data.items() if f['a1'] == k and f['t1'] < t]

# C1: Flight assignment
model.c1 = ConstraintList()
for i in Flights:
    model.c1.add(sum(model.x[i, j] for j in Aircrafts) == 1)

# C2 & C3: Continuity + Initial location
model.c23 = ConstraintList()
for j in Aircrafts:
    for k in Airports:
        for i in F_arr_k[k]:
            # lhs = sum(model.x[i2, j] for i2 in F_ge_k(k, t_dep[i])) - sum(
            #     model.x[i2, j] for i2 in F_lt_k(k, t_arr[i]))
            # if k == Aircraft[j]:
            #     model.c23.add(lhs >= model.x[i, j] - 1)
            # else:
            #     model.c23.add(lhs >= model.x[i, j])
            #

            lhs_geq = sum(model.x[i2, j] for i2 in F_ge_k(k, t_dep[i]))
            lhs_lt = sum(model.x[i2, j] for i2 in F_lt_k(k, t_arr[i]))

            print("ijk", i, j, k, end=":")
            print(t_arr[i], end="\t")
            print(lhs_geq, end="\t")
            print(lhs_lt, end="\n")

            if k != Aircraft[j]:
                model.c23.add(lhs_geq - lhs_lt >= model.x[i, j])
            else:
                model.c23.add(lhs_geq - lhs_lt >= model.x[i, j] - 1)


# C4: Turn time constraint
model.turn_time = ConstraintList()
for j in Aircrafts:
    for i in Flights:
        for i2 in Flights:
            if i != i2 and a_arr[i] == a_dep[i2] and t_arr[i] + min_turn > t_dep[i2]:
                model.turn_time.add(model.x[i, j] + model.x[i2, j] <= 1)


# Maintenance Constraints
#
# # Last flight + night maintenance
# model.maint_last = ConstraintList()
# for i in Flights:
#     for j in Aircrafts:
#         for d in Days:
#             for i2 in F_d_i(d, i):
#                 model.maint_last.add(model.z[i, j, d] + model.x[i2, j] <= 1)
#
# # Link z and x
# model.maint_assignment = ConstraintList()
# for i in Flights:
#     for j in Aircrafts:
#         for d in Days:
#             model.maint_assignment.add(model.x[i, j] >= model.z[i, j, d])
#
# # Maintenance capacity
# model.maint_capacity = ConstraintList()
# for d in Days:
#     for m in MA:
#         if (m, d) in mcap:
#             model.maint_capacity.add(
#                 sum(model.z[i, j, d] for i in F_m[m] for j in Aircrafts) <= mcap[m, d]
#             )
#
# # Maintenance occurrence links
# model.maint_link = ConstraintList()
# for d in Days:
#     for m in MA:
#         for j in Aircrafts:
#             model.maint_link.add(
#                 sum(model.z[i, j, d] for i in F_m[m]) == model.y[j, d]
#             )
#
# # Max spacing constraint
# model.maint_spacing = ConstraintList()
# for j in Aircrafts:
#     for start in range(0, len(Days) - dmax + 1):
#         d_range = list(Days)[start:start + dmax]
#         model.maint_spacing.add(sum(model.y[j, r] for r in d_range) >= 1)
#
# # Cumulative flight time constraint
# model.maint_cumulative = ConstraintList()
# for j in Aircrafts:
#     for start in range(len(Days) - 1):
#         for end in range(start + 2, min(start + dmax, len(Days))):
#             d = list(Days)[start]
#             d_ = list(Days)[end]
#             t_sum = sum(duration[i] * model.x[i, j] for i in F_d_next(d, d_))
#             y_sum = model.y[j, d] + model.y[j, d_] + sum(model.y[j, r] for r in list(Days)[start + 1:end])
#             model.maint_cumulative.add(t_sum <= Tmax + Mbig * (3 - y_sum))

# Solve
solver = SolverFactory('cplex')  # Or 'cplex', 'glpk', etc.
solver.solve(model)


print("\nAssignment Results:")
for i in model.F:
    for j in model.P:
        if value(model.x[i, j]) > 0.5:
            print(f"Flight {i} assigned to Plane {j}")

print(f"Total Cost: {value(model.obj)}")

