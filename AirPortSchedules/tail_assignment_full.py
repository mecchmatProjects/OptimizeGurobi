from pyomo.environ import *
from datetime import datetime, timedelta
import re

model = ConcreteModel()

# --- Load Data from Input File ---
def parse_input(filename):
    # Helper function to parse datetime strings
    def parse_datetime(s):
        return datetime.strptime(s.strip(), "%d.%m.%Y %H:%M")

    # Load input data
    with open(filename, "r") as file:
        lines = [line.strip() for line in file if line.strip()]

    # Read counts
    idx = 0
    F = int(lines[idx]);
    idx += 1
    A = int(lines[idx]);
    idx += 1
    P = int(lines[idx]);
    idx += 1

    # Read flights
    assert lines[idx].startswith("Flight"), "Expected header for flight data"
    idx += 1

    flights = {}
    flight_ids = []
    airports = set()
    for _ in range(F):
        parts = lines[idx].split()
        print(parts)
        i = int(parts[0])
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
            costs[(int(flight),int(j))] = int(cost)
        idx += 1

    print(costs)

    # Read initial airports
    assert lines[idx].startswith("Initial airports:"), "Expected initial airports section"
    idx += 1
    initial_airports = {}
    for _ in range(P):
        plane, airport = lines[idx].split()
        initial_airports[int(plane)] = airport
        idx += 1

    print(initial_airports)
    # Read turnaround time
    assert lines[idx].startswith("Turnaround time:"), "Expected turnaround time"
    idx += 1
    hh, mm = map(int, lines[idx].split(":"))
    turnaround_time = timedelta(hours=hh, minutes=mm)
    print(turnaround_time)

    return F, P, A, flights, costs, initial_airports, turnaround_time

F, P, A, flight_data, cost_data, a0, turn_time = parse_input('test1.txt')
# turn_time = timedelta(minutes=30)

model.F = Set(initialize=range(1, F+1))
model.P = Set(initialize=range(1, P+1))
model.A = Set(initialize=list(set(f['a1'] for f in flight_data.values()).union(set(f['a2'] for f in flight_data.values()))))

print("cost data:", cost_data, flight_data, a0)
model.x = Var(model.F, model.P, domain=Binary)
model.c = Param(model.F, model.P, initialize=cost_data)

# Airport transitions
flight_arr = {k: [] for k in model.A}
for i, f in flight_data.items():
    flight_arr[f['a2']].append(i)

#
# # Initial positions of planes (hardcoded for demo)
# a0 = {j: 'A' for j in model.P}  # all planes start at airport 'A'

model.obj = Objective(expr=sum(model.c[i, j]*model.x[i, j] for i in model.F for j in model.P), sense=minimize)

# Constraint (3): Each flight assigned to exactly one airplane
model.flight_assignment = ConstraintList()
for i in model.F:
    model.flight_assignment.add(sum(model.x[i, j] for j in model.P) == 1)

# Helper functions for constraints (4) and (5)
def F_geq_k(k, t):
    # print(flight_data,t)
    return [i for i, f in flight_data.items() if f['a2'] == k and f['t2'] <= t + turn_time]

def F_lt_k(k, t):
    return [i for i, f in flight_data.items() if f['a1'] == k and f['t1'] < t]

model.equipment_turn_constraints = ConstraintList()
for j in model.P:
    for k in model.A:
        for i in flight_arr[k]:
            t_arr_i = flight_data[i]['t2']
            # print("ijk",i,j,k, end=":")
            # print(t_arr_i, end="\t")
            # print(F_geq_k(k, t_arr_i), end="\t")
            # print(F_lt_k(k, t_arr_i))

            lhs_geq = sum(model.x[i1, j] for i1 in F_geq_k(k, t_arr_i))
            lhs_lt = sum(model.x[i1, j] for i1 in F_lt_k(k, t_arr_i))
            if k != a0[j]:
                model.equipment_turn_constraints.add(lhs_geq - lhs_lt >= model.x[i, j])
            else:
                model.equipment_turn_constraints.add(lhs_geq - lhs_lt >= model.x[i, j] - 1)

# Save and solve
solver = SolverFactory('cplex')
results = solver.solve(model, tee=True)

print("\nAssignment Results:")
for i in model.F:
    for j in model.P:
        if value(model.x[i, j]) > 0.5:
            print(f"Flight {i} assigned to Plane {j}")

print(f"Total Cost: {value(model.obj)}")


