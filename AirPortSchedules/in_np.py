import pyomo.environ as pyo
from datetime import datetime
import random

# Flight data: (id, dep_airport, arr_airport, dep_time, arr_time)
flights = [
    (1, 'A', 'B', '09:00', '11:00'),
    (2, 'B', 'A', '11:30', '13:30'),
    (3, 'A', 'B', '14:00', '16:00'),
    (4, 'B', 'A', '09:30', '11:30'),
    (5, 'A', 'B', '12:00', '14:00'),
    (6, 'B', 'A', '14:30', '16:30')
]

# Initial positions: {airport: count}
initial_positions = {'A': 1, 'B': 1}
turnaround = 30  # minutes


# Convert times to minutes since midnight
def time_to_minutes(time_str):
    return int(time_str.split(':')[0]) * 60 + int(time_str.split(':')[1])


# Preprocess flight data
flight_data = {}
for fid, dep, arr, dep_time, arr_time in flights:
    flight_data[fid] = {
        'dep_airport': dep,
        'arr_airport': arr,
        'dep_time': time_to_minutes(dep_time),
        'arr_time': time_to_minutes(arr_time)
    }

# Create Pyomo model
model = pyo.ConcreteModel()

# Sets
model.flights = pyo.Set(initialize=[fid for fid, *_ in flights])
model.airports = pyo.Set(initialize=list(initial_positions.keys()))
model.nodes = pyo.Set(initialize=['source', 'sink'] +
                                 [f'v_{fid}' for fid in model.flights] +
                                 [f'w_{fid}' for fid in model.flights] +
                                 [f'u_{airport}' for airport in model.airports])

# Arc set and parameters
model.arcs = pyo.Set(dimen=2)
model.arc_capacity = pyo.Param(model.arcs, mutable=True, default=0)
model.arc_cost = pyo.Param(model.arcs, mutable=True, default=0)

# Add arcs: source to u_nodes (initial positions)
for airport in model.airports:
    arc = ('source', f'u_{airport}')
    model.arcs.add(arc)
    model.arc_capacity[arc] = initial_positions[airport]
    model.arc_cost[arc] = 1  # Cost 1 per airplane used

# Add arcs: u_nodes to v_nodes (flight starts)
for fid in model.flights:
    dep_airport = flight_data[fid]['dep_airport']
    arc = (f'u_{dep_airport}', f'v_{fid}')
    model.arcs.add(arc)
    model.arc_capacity[arc] = 1
    model.arc_cost[arc] = 0

# Add arcs: v_nodes to w_nodes (flight coverage)
for fid in model.flights:
    arc = (f'v_{fid}', f'w_{fid}')
    model.arcs.add(arc)
    model.arc_capacity[arc] = 1  # Must be covered
    model.arc_cost[arc] = 0

# Add arcs: w_nodes to v_nodes (flight connections)
for i in model.flights:
    for j in model.flights:
        if i == j:
            continue
        # Check compatibility
        arr_port_i = flight_data[i]['arr_airport']
        dep_port_j = flight_data[j]['dep_airport']
        time_diff = flight_data[j]['dep_time'] - flight_data[i]['arr_time']

        if arr_port_i == dep_port_j and time_diff >= turnaround:
            arc = (f'w_{i}', f'v_{j}')
            model.arcs.add(arc)
            model.arc_capacity[arc] = 1
            model.arc_cost[arc] = 0

# Add arcs: w_nodes to sink
for fid in model.flights:
    arc = (f'w_{fid}', 'sink')
    model.arcs.add(arc)
    model.arc_capacity[arc] = 1
    model.arc_cost[arc] = 0

# Flow variables
model.flow = pyo.Var(model.arcs, domain=pyo.NonNegativeReals)


# Flow conservation constraints
def flow_conservation(model, node):
    if node == 'source':
        # Source: outflow only
        return sum(model.flow[arc] for arc in model.arcs if arc[0] == node) == sum(
            model.flow[('source', f'u_{a}')] for a in model.airports)
    elif node == 'sink':
        # Sink: inflow only
        return sum(model.flow[arc] for arc in model.arcs if arc[1] == node) == sum(
            model.flow[(f'w_{f}', 'sink')] for f in model.flights)
    else:
        inflow = sum(model.flow[arc] for arc in model.arcs if arc[1] == node)
        outflow = sum(model.flow[arc] for arc in model.arcs if arc[0] == node)
        return inflow == outflow


model.flow_conservation = pyo.Constraint(model.nodes, rule=flow_conservation)


# Flight coverage constraints
def flight_coverage(model, fid):
    return model.flow[(f'v_{fid}', f'w_{fid}')] == 1


model.flight_coverage = pyo.Constraint(model.flights, rule=flight_coverage)


# Capacity constraints
def capacity_constraint(model, i, j):
    return model.flow[(i, j)] <= model.arc_capacity[(i, j)]


model.capacity_constraint = pyo.Constraint(model.arcs, rule=capacity_constraint)


# Objective: Minimize total airplanes used
def objective_rule(model):
    return sum(model.flow[('source', f'u_{a}')] for a in model.airports)


model.objective = pyo.Objective(rule=objective_rule, sense=pyo.minimize)

# Solve the model
solver = pyo.SolverFactory('gurobi')
results = solver.solve(model)

# Print results
print("Minimum number of airplanes needed:", pyo.value(model.objective))
print("\nAirplane rotations:")
for airport in model.airports:
    flow = pyo.value(model.flow[('source', f'u_{airport}')])
    print(f"Airplanes starting at {airport}: {flow}")

# Print flight assignments
for fid in model.flights:
    for arc in model.arcs:
        if arc[0].startswith('w_') and arc[1].startswith('v_'):
            i = int(arc[0].split('_')[1])
            j = int(arc[1].split('_')[1])
            if pyo.value(model.flow[arc]) > 0.5:
                print(f"Flight {i} -> Flight {j}")

for fid in model.flights:
    if pyo.value(model.flow[(f'w_{fid}', 'sink')]) > 0.5:
        print(f"Flight {fid} ends rotation")

npmin = pyo.value(model.objective)

# Instance generation procedure
def generate_instance(rotations, np, delta):
    # Step (a): P_bar is the set of rotations (airplanes)
    P_bar = list(range(len(rotations)))

    # Step (b): Select subset of np airplanes
    if np > npmin:
        raise ValueError(f"np={np} exceeds npmin={npmin}")
    P_prime = random.sample(P_bar, np)

    # Step (c): Select subset of delta*np airplanes
    num_selected = max(1, min(np, round(delta * np)))
    P_doubleprime = random.sample(P_prime, int(num_selected))

    # Create flight set as union of flights from selected rotations
    flight_set = set()
    for idx in P_doubleprime:
        flight_set.update(rotations[idx])

    # Get initial positions for P_prime
    initial_positions_prime = []
    for idx in P_prime:
        if rotations[idx]:
            first_flight = rotations[idx][0]
            initial_positions_prime.append(flight_data[first_flight]['dep_airport'])
        else:
            # If rotation is empty, assign random airport
            initial_positions_prime.append(random.choice(list(model.airports)))

    return list(flight_set), initial_positions_prime, P_prime, P_doubleprime


# Generate instance
flight_set, initial_positions_prime, P_prime, P_doubleprime = generate_instance(
    rotations, np_param, delta_
)

print("\nGenerated instance:")
print(f"Selected airplanes (P_prime): {P_prime}")
print(f"Airplanes contributing flights (P_doubleprime): {P_doubleprime}")
print(f"Initial positions: {initial_positions_prime}")
print("Flight set:", flight_set)

# (Optional) Solve tail assignment for generated instance
# This would use the same model structure but with the generated flight_set
# and initial_positions_prime


def generate_instance(rotations, np, delta):
    P_bar = list(range(len(rotations)))  # All airplanes in optimal solution

    # Select subset of np airplanes
    P_prime = random.sample(P_bar, np)

    # Select subset of δ*np airplanes
    num_selected = max(1, min(np, round(delta * np)))
    P_doubleprime = random.sample(P_prime, int(num_selected))

    # Create flight set as union of flights from selected rotations
    flight_set = set()
    for idx in P_doubleprime:
        flight_set.update(rotations[idx])

    # Get initial positions from first flight in each rotation
    initial_positions_prime = []
    for idx in P_prime:
        if rotations[idx]:
            first_flight = rotations[idx][0]
            initial_positions_prime.append(flight_data[first_flight]['dep_airport'])
        else:
            initial_positions_prime.append(random.choice(list(model.airports)))

    return list(flight_set), initial_positions_prime, P_prime, P_doubleprime

