from pyomo.environ import *
from datetime import datetime, timedelta
import re

# Parse the input file
def parse_input(filename):
    with open(filename, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]

    F = int(lines[0])
    P = int(lines[1])
    A = int(lines[2])

    flights = {}
    costs = {}

    initial_locations = {}  # airplane -> initial airport
    tau = timedelta(minutes=30)


    # Locate where flight info starts
    idx = lines.index('Flight i a1(i) a2(i) t1(i) t2(i)') + 1
    while re.match(r'^\d+', lines[idx]):
        parts = lines[idx].split()
        fid = parts[0]
        a1 = parts[1]
        a2 = parts[2]
        t1_str = parts[3] + ' ' + parts[4]
        t2_str = parts[5] + ' ' + parts[6]
        t1 = datetime.strptime(t1_str, '%d.%m.%Y %H:%M')
        t2 = datetime.strptime(t2_str, '%d.%m.%Y %H:%M')
        flights[fid] = {'a1': a1, 'a2': a2, 't1': t1, 't2': t2}
        idx += 1

    # Locate where costs start
    while 'Assignment costs' not in lines[idx]:
        idx += 1
    idx += 2  # skip header line

    while idx < len(lines):
        parts = lines[idx].split()
        fid = parts[0]
        for j, cost in enumerate(parts[1:], 1):
            costs[(fid, str(j))] = float(cost)
        idx += 1


    # Example parsing logic (you likely have a file-reading loop)
    if line.startswith("Initial airports:"):
        for _ in range(P):
            aid, airport = next(file).split()
            initial_locations[aid] = airport
    elif line.startswith("Turnaround time:"):
        h, m = map(int, next(file).strip().split(":"))
        tau = timedelta(hours=h, minutes=m)

    return F, P, A, flights, costs, tau, initial_locations

# Load data
F, P, A, flights, costs,tau, initial_locations = parse_input('test0.txt')
flight_ids = list(flights.keys())
plane_ids = [str(p+1) for p in range(P)]

# Pyomo model
model = ConcreteModel()
model.F = Set(initialize=flight_ids)
model.P = Set(initialize=plane_ids)
model.c = Param(model.F, model.P, initialize=costs)
model.x = Var(model.F, model.P, domain=Binary)
model.a0 = Param(model.P, initialize=initial_locations)  # initial airport

# Each flight is assigned to exactly one plane
def one_plane_per_flight_rule(m, f):
    return sum(m.x[f, p] for p in m.P) == 1
model.flight_assignment = Constraint(model.F, rule=one_plane_per_flight_rule)

# No overlapping flights for a plane
def no_overlap_rule(m, p):
    for i in m.F:
        for j in m.F:
            if i == j:
                continue
            fi = flights[i]
            fj = flights[j]
            # If times overlap
            if not (fi['t2'] <= fj['t1'] or fj['t2'] <= fi['t1']):
                yield m.x[i, p] + m.x[j, p] <= 1

model.no_overlap = ConstraintList()
for p in model.P:
    for c in no_overlap_rule(model, p):
        model.no_overlap.add(c)

def initial_location_rule(m, j, i):
    if flights[i]['a1'] != m.a0[j]:
        return m.x[i, j] == 0
    return Constraint.Skip

model.initial_conditions = Constraint(model.P, model.F, rule=initial_location_rule)

def equipment_continuity_rule(m, j, i):
    a_i = flights[i]['a1']  # airport of departure
    t_i = flights[i]['t1']
    lhs = sum(
        m.x[fp, j]
        for fp in m.F
        if flights[fp]['a2'] == a_i and flights[fp]['t2'] + tau <= t_i
    )
    rhs = m.x[i, j]
    return lhs >= rhs

model.equipment_continuity = Constraint(model.P, model.F, rule=equipment_continuity_rule)


def turnaround_time_rule(m, j, i, ip):
    if i == ip:
        return Constraint.Skip
    fi, fip = flights[i], flights[ip]
    if fi['a2'] == fip['a1'] and fi['t2'] + tau > fip['t1']:
        return m.x[i, j] + m.x[ip, j] <= 1
    return Constraint.Skip

model.turnaround = Constraint(model.P, model.F, model.F, rule=turnaround_time_rule)

# Objective: minimize total assignment cost
def obj_rule(m):
    return sum(m.c[f, p] * m.x[f, p] for f in m.F for p in m.P)
model.obj = Objective(rule=obj_rule, sense=minimize)

# Solve
solver = SolverFactory('cplex')
results = solver.solve(model, tee=True)

# Output
print("\n--- Assignment Results ---")
for f in model.F:
    for p in model.P:
        if value(model.x[f, p]) > 0.5:
            print("Flight {} -> Plane {}".format(f, p))
