from pyomo.environ import *
from pyomo.opt import SolverFactory
import pandas as pd

# --- Data Loading ---
flights_df = pd.read_csv("data/flights.csv")
airports_df = pd.read_csv("data/airports.csv")
planes_df = pd.read_csv("data/planes.csv")
maintenance_df = pd.read_csv("data/maintenance_capacity.csv")

F = list(flights_df.index)
P = list(planes_df.index)
A = list(airports_df.index)
D = sorted(flights_df['day'].unique())
MA = list(maintenance_df['airport'].unique())

# Parameters
c = {(i, j): flights_df.loc[i, f"c_{j}"] for i in F for j in P}
t_arr = flights_df['t_arrival'].to_dict()
t_dep = flights_df['t_departure'].to_dict()
a_arr = flights_df['a_arrival'].to_dict()
a_dep = flights_df['a_departure'].to_dict()
day = flights_df['day'].to_dict()
t_flight = flights_df['duration'].to_dict()
a0 = {j: planes_df.loc[j, 'initial_airport'] for j in P}

# Maintenance cost
mc = {(i, j, d): 100 for i in F for j in P for d in D}  # example uniform cost
mcap = {(row['airport'], row['day']): row['capacity'] for _, row in maintenance_df.iterrows()}

# Helper sets
F_arr_k = {k: [i for i in F if a_arr[i] == k] for k in A}
F_ge_k = lambda k, t: [i for i in F if a_dep[i] == k and t_dep[i] >= t]
F_lt_k = lambda k, t: [i for i in F if a_arr[i] == k and t_arr[i] < t]
F_m = {m: [i for i in F if a_arr[i] == m] for m in MA}
F_d = {d: [i for i in F if day[i] == d] for d in D}
F_d_next = lambda d1, d2: [i for i in F if d1 < day[i] <= d2]
F_d_i = lambda d, i: [i2 for i2 in F if day[i2] == d and t_arr[i2] > t_arr[i]]

# Constants
Tmax = 8  # hours
nu = 15  # max take-offs
dmax = 3  # max days between maintenances
Mbig = 9999

model = ConcreteModel()

# Sets
model.F = Set(initialize=F)
model.P = Set(initialize=P)
model.A = Set(initialize=A)
model.D = Set(initialize=D)
model.MA = Set(initialize=MA)

# Variables
model.x = Var(model.F, model.P, domain=Binary)
model.z = Var(model.F, model.P, model.D, domain=Binary)
model.y = Var(model.P, model.D, domain=Binary)

# Objective
model.obj = Objective(
    expr=sum(c[i, j] * model.x[i, j] for i in F for j in P) +
         sum(mc[i, j, d] * model.z[i, j, d] for m in MA for i in F_m[m] for j in P for d in D),
    sense=minimize
)

# C1: Flight assignment
model.c1 = ConstraintList()
for i in F:
    model.c1.add(sum(model.x[i, j] for j in P) == 1)

# C2-C3: Equipment continuity + Initial condition
model.c23 = ConstraintList()
for j in P:
    for k in A:
        for i in F_arr_k[k]:
            lhs = sum(model.x[i2, j] for i2 in F_ge_k(k, t_dep[i])) - sum(model.x[i2, j] for i2 in F_lt_k(k, t_arr[i]))
            if k == a0[j]:
                model.c23.add(lhs >= model.x[i, j] - 1)
            else:
                model.c23.add(lhs >= model.x[i, j])

# C4: Turn time (not explicitly modeled as time difference but should be refined)
model.turn_time = ConstraintList()
min_turn = 0.5
for j in P:
    for i in F:
        for i2 in F:
            if i != i2 and a_arr[i] == a_dep[i2] and t_arr[i] + min_turn > t_dep[i2]:
                model.turn_time.add(model.x[i, j] + model.x[i2, j] <= 1)

# Maintenance Constraints
model.maint_last = ConstraintList()
for i in F:
    for j in P:
        for d in D:
            for i2 in F_d_i(d, i):
                model.maint_last.add(model.z[i, j, d] + model.x[i2, j] <= 1)

model.maint_assignment = ConstraintList()
for i in F:
    for j in P:
        for d in D:
            model.maint_assignment.add(model.x[i, j] >= model.z[i, j, d])

model.maint_capacity = ConstraintList()
for d in D:
    for m in MA:
        if (m, d) in mcap:
            model.maint_capacity.add(sum(model.z[i, j, d] for i in F_m[m] for j in P) <= mcap[m, d])

model.maint_link = ConstraintList()
for d in D:
    for m in MA:
        for j in P:
            model.maint_link.add(sum(model.z[i, j, d] for i in F_m[m]) == model.y[j, d])

model.maint_spacing = ConstraintList()
for j in P:
    for start in range(0, len(D) - dmax + 1):
        d = D[start]
        d_ = D[start + dmax - 1]
        model.maint_spacing.add(sum(model.y[j, r] for r in D[start:start + dmax]) >= 1)

model.maint_cumulative = ConstraintList()
for j in P:
    for start in range(len(D) - 1):
        for end in range(start + 2, min(start + dmax, len(D))):
            d = D[start]
            d_ = D[end]
            t_sum = sum(t_flight[i] * model.x[i, j] for i in F_d_next(d, d_))
            y_sum = model.y[j, d] + model.y[j, d_] + sum(model.y[j, r] for r in D[start + 1:end])
            model.maint_cumulative.add(t_sum <= Tmax + Mbig * (3 - y_sum))

# Solve
# solver = SolverFactory('cbc')
# solver.solve(model)
