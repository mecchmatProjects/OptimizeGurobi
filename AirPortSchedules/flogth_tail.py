
from pyomo.environ import *
from datetime import datetime, timedelta

# Helper function to parse datetime strings
def parse_datetime(s):
    return datetime.strptime(s.strip(), "%d.%m.%Y %H:%M")

# Load input data
with open("test1.txt", "r") as file:
    lines = [line.strip() for line in file if line.strip()]

# Read counts
idx = 0
F = int(lines[idx]); idx += 1
A = int(lines[idx]); idx += 1
P = int(lines[idx]); idx += 1

# Read flights
assert lines[idx].startswith("Flight"), "Expected header for flight data"
idx += 1

flights = {}
flight_ids = []
airports = set()
for _ in range(F):
    parts = lines[idx].split()
    print(parts)
    i = parts[0]
    a1, a2 = parts[1], parts[2]
    t1 = parse_datetime(" ".join(parts[3:5]))
    t2 = parse_datetime(" ".join(parts[5:7]))
    flights[i] = {'a1': a1, 'a2': a2, 't1': t1, 't2': t2}
    flight_ids.append(i)
    airports.update([a1, a2])
    idx += 1

print(idx, lines[idx])
# Read assignment costs
assert lines[idx].startswith("Assignment costs"), "Expected assignment costs header"
idx += 1
assert lines[idx].startswith("Flight"), "Expected header row for costs"
headers = lines[idx].split()[2:]  # Skip 'Flight' and 'Airplane'
plane_ids = headers
idx += 1

costs = {}
while idx < len(lines) and lines[idx][0].isdigit():
    parts = lines[idx].split()
    flight = parts[0]
    for j, cost in zip(plane_ids, parts[1:]):
        costs[(flight, j)] = int(cost)
    idx += 1

print(costs)

# Read initial airports
assert lines[idx].startswith("Initial airports:"), "Expected initial airports section"
idx += 1
initial_airports = {}
for _ in range(P):
    plane, airport = lines[idx].split()
    initial_airports[plane] = airport
    idx += 1

print(initial_airports)
# Read turnaround time
assert lines[idx].startswith("Turnaround time:"), "Expected turnaround time"
idx += 1
hh, mm = map(int, lines[idx].split(":"))
turnaround_time = timedelta(hours=hh, minutes=mm)
print(turnaround_time)
# Create model
model = ConcreteModel()

model.F = Set(initialize=flight_ids)
model.P = Set(initialize=plane_ids)
model.A = Set(initialize=list(airports))
model.A1 = Set(initialize=list(range(1,A+1)))


model.x = Var(model.F, model.P, domain=Binary)
model.c = Param(model.F, model.P, initialize=costs)
model.a0 = Param(model.P, initialize=initial_airports)

# Objective: minimize total cost
def obj_rule(m):
    return sum(m.c[i, j] * m.x[i, j] for i in m.F for j in m.P)
model.obj = Objective(rule=obj_rule, sense=minimize)

# C1: Each flight is assigned to exactly one airplane
def assign_once_rule(m, i):
    return sum(m.x[i, j] for j in m.P) == 1
model.assign_once = Constraint(model.F, rule=assign_once_rule)

# C2: Equipment continuity
def equipment_continuity_rule(m, j, i):
    a_i = flights[i]['a1']
    t_i = flights[i]['t1']
    lhs = sum(
        m.x[fp, j]
        for fp in m.F
        if flights[fp]['a2'] == a_i and flights[fp]['t2'] + turnaround_time <= t_i
    )
    rhs = sum(
        m.x[fp, j]
        for fp in m.F
        if flights[fp]['a1'] == a_i and flights[fp]['t2'] + turnaround_time <= t_i
    )
    return lhs - rhs >= m.x[i,j]
model.equipment_continuity = Constraint(model.P, model.F, rule=equipment_continuity_rule)

# C4: Turnaround time
def turnaround_rule(m, j, i, ip):
    if i == ip:
        return Constraint.Skip
    fi, fip = flights[i], flights[ip]
    if fi['a2'] == fip['a1'] and fi['t2'] + turnaround_time > fip['t1']:
        return m.x[i, j] + m.x[ip, j] <= 1
    return Constraint.Skip
model.turnaround = Constraint(model.P, model.F, model.F, rule=turnaround_rule)

# Solve
solver = SolverFactory("gurobi")
results = solver.solve(model, tee=True)

# Output
for i in model.F:
    for j in model.P:
        if value(model.x[i, j]) == 1:
            print(f"Flight {i} assigned to Plane {j} with cost {model.c[i, j]}")
