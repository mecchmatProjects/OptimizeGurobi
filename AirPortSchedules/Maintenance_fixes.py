from pyomo.environ import *
from pyomo.opt import SolverFactory

# --- CP-style Inputs ---
Airports = ["A", "B"]
Aircrafts = [1, 2]
Nbflight = 6
Flights = list(range(1, Nbflight + 1))
Days = list(range(1, 8))
MA = sorted(["A", "B", "C"])  # Maintenance airports

# Flight Information
Flight = [
    {"flight": 1, "origin": "A", "destination": "B", "departureTime": 540, "arrivalTime": 660},
    {"flight": 2, "origin": "B", "destination": "A", "departureTime": 690, "arrivalTime": 810},
    {"flight": 3, "origin": "A", "destination": "B", "departureTime": 840, "arrivalTime": 960},
    {"flight": 4, "origin": "B", "destination": "A", "departureTime": 570, "arrivalTime": 690},
    {"flight": 5, "origin": "A", "destination": "B", "departureTime": 720, "arrivalTime": 840},
    {"flight": 6, "origin": "B", "destination": "A", "departureTime": 870, "arrivalTime": 990}
]

# Derived FlightData
FlightData = {
    f["flight"]: {
        "origin": f["origin"],
        "destination": f["destination"],
        "departureTime": f["departureTime"],
        "arrivalTime": f["arrivalTime"],
        "duration": f["arrivalTime"] - f["departureTime"],
        "day": int(f["arrivalTime"] // (24 * 60)) + 1
    } for f in Flight
}

# Initial aircraft locations
a0 = {1: "A", 2: "B"}

# Cost matrix
c = {(i, j): 1000 + i * 10 + j * 5 for i in Flights for j in Aircrafts}  # dummy values
mc = {(i, j, d): 100 for i in Flights for j in Aircrafts for d in Days}  # dummy maintenance cost

# Maintenance capacity
mcap = {(m, d): 2 for m in MA for d in Days}  # dummy capacity

# Helper functions
F_m = {m: [i for i in Flights if FlightData[i]["origin"] == m] for m in MA}  # The set of flights which land in airport m

F_arr_k = {k: [i for i in Flights if FlightData[i]["destination"] == k] for k in sorted(Airports)}  # The set of flights which land in airport k
F_dep_k = {k: [i for i in Flights if FlightData[i]["origin"] == k] for k in sorted(Airports)}  # The set of flights which land in airport k

# The set of flights which land in airport k before time t
# def F_gkt(k, t, delta):
#     return [i for i in Flights if FlightData[i]["destination"] == k and FlightData[i]["departureTime"] <= t - delta]
F_arr_t = lambda k, t, delta: [i for i in F_arr_k[k] if FlightData[i]["arrivalTime"] <= t - delta]

# The set of flights which land in airport k before time t
def F_lkt(k,t):
    return [i for i in Flights if FlightData[i]["origin"] == k and FlightData[i]["departureTime"] < t]

F_dep_t = lambda k, t: [i for i in F_dep_k[k] if FlightData[i]["departureTime"] < t]


F_d = {d: [i for i in Flights if FlightData[i]["day"] == d] for d in Days}
F_d_next = lambda d1, d2: [i for i in Flights if d1 < FlightData[i]["day"] <= d2]
F_d_i = lambda d, i: [i2 for i2 in Flights if FlightData[i2]["day"] == d and FlightData[i2]["arrivalTime"] > FlightData[i]["arrivalTime"]]

Tmax = 8 * 60  # in minutes
nu = 15
dmax = 3
Mbig = 9999
min_turn = 30  # in minutes

model = ConcreteModel()

model.F = Set(initialize=Flights)
model.P = Set(initialize=sorted(Aircrafts))
model.A = Set(initialize=sorted(Airports))
model.D = Set(initialize=sorted(Days))
model.MA = Set(initialize=sorted(MA))

print([j for j in model.P])

model.x = Var(model.F, model.P, domain=Binary)
model.z = Var(model.F, model.P, model.D, domain=Binary)
model.y = Var(model.P, model.D, domain=Binary)

model.obj = Objective(
    expr=sum(c[i, j] * model.x[i, j] for i in model.F for j in model.P) +
         sum(mc[i, j, d] * model.z[i, j, d] for m in model.MA for i in F_m[m] for j in model.P for d in model.D),
    sense=minimize
)

model.c1 = ConstraintList()
for i in model.F:
    model.c1.add(sum(model.x[i, j] for j in model.P) == 1)

# Replacing c23 with corrected equipment_turn_constraints
turn_time = min_turn
flight_data = FlightData
flight_arr = {k: [i for i in model.F if FlightData[i]['destination'] == k] for k in model.A}

# def F_geq_k(k, t):
#     return [i for i, f in flight_data.items() if f['destination'] == k and f['arrivalTime'] <= t + turn_time]
#
# def F_lt_k(k, t):
#     return [i for i, f in flight_data.items() if f['origin'] == k and f['departureTime'] < t]

model.equipment_turn_constraints = ConstraintList()
for j in model.P:
    for k in model.A:
        for i in F_dep_k[k]:
            t_dep = flight_data[i]['departureTime']
            lhs_geq = sum(model.x[i1, j] for i1 in F_arr_t(k, t_dep, turn_time))
            lhs_lt = sum(model.x[i1, j] for i1 in F_dep_t(k, t_dep))

            print("ijk", i, j, k, end=":")
            print(t_dep, end="\t")
            print(F_arr_t(k, t_dep, turn_time), lhs_geq, end="\t")
            print(F_dep_t(k, t_dep), lhs_lt)

            if k != a0[j]:
                model.equipment_turn_constraints.add(lhs_geq - lhs_lt >= model.x[i, j])
            else:
                model.equipment_turn_constraints.add(lhs_geq - lhs_lt >= model.x[i, j] - 1)

# model.turn_time = ConstraintList()
# for j in model.P:
#     for i in model.F:
#         for i2 in model.F:
#             if i != i2 and FlightData[i]["destination"] == FlightData[i2]["origin"] and \
#                FlightData[i]["arrivalTime"] + min_turn > FlightData[i2]["departureTime"]:
#                 model.turn_time.add(model.x[i, j] + model.x[i2, j] <= 1)

model.maint_last = ConstraintList()
for i in model.F:
    for j in model.P:
        for d in model.D:
            for i2 in F_d_i(d, i):
                model.maint_last.add(model.z[i, j, d] + model.x[i2, j] <= 1)

model.maint_assignment = ConstraintList()
for i in model.F:
    for j in model.P:
        for d in model.D:
            model.maint_assignment.add(model.x[i, j] >= model.z[i, j, d])

model.maint_capacity = ConstraintList()
for d in model.D:
    for m in model.MA:
        relevant_flights = F_m.get(m, [])
        if relevant_flights:
            model.maint_capacity.add(
                sum(model.z[i, j, d] for i in relevant_flights for j in model.P) <= mcap[m, d]
            )

model.maint_link = ConstraintList()
for d in model.D:
    for m in model.MA:
        for j in model.P:
            model.maint_link.add(sum(model.z[i, j, d] for i in F_m[m]) == model.y[j, d])


model.maint_spacing = ConstraintList()
for j in model.P:
    for start in range(0, len(Days) - dmax + 1):
        model.maint_spacing.add(sum(model.y[j, r] for r in Days[start:start + dmax]) >= 1)


model.maint_cumulative = ConstraintList()
for j in model.P:
    for start in range(len(Days) - 1):
        for end in range(start + 2, min(start + dmax, len(Days))):
            d = Days[start]
            d_ = Days[end]
            t_sum = sum(FlightData[i]['duration'] * model.x[i, j] for i in F_d_next(d+1, d_))
            y_sum = sum(model.y[j, r] for r in Days[start+1:end])
            model.maint_cumulative.add(t_sum <= Tmax + Mbig * y_sum + Mbig*(2 - model.y[j, d] - model.y[j, d_]) )

# Solve
solver = SolverFactory('cplex')  # Or 'cplex', 'glpk', etc.
solver.solve(model)



print("\nAssignment Results:")
for i in model.F:
    for j in model.P:
        if value(model.x[i, j]) > 0.5:
            print(f"Flight {i} assigned to Plane {j}")

print(f"Total Cost: {value(model.obj)}")
