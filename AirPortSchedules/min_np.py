import pyomo.environ as pyo
import random
from datetime import datetime

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
np_param = 2  # Number of airplanes for instance
delta = 0.5  # Fraction of airplanes contributing flights


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

# Create Pyomo model for min-airplane problem
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


# Proper flow conservation constraints
def flow_conservation(model, node):
    # Skip source and sink - they have special handling
    if node in ['source', 'sink']:
        return pyo.Constraint.Skip

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


# Additional constraint to ensure source outflow equals sink inflow
def source_sink_balance(model):
    source_out = sum(model.flow[arc] for arc in model.arcs if arc[0] == 'source')
    sink_in = sum(model.flow[arc] for arc in model.arcs if arc[1] == 'sink')
    return source_out == sink_in


model.source_sink_balance = pyo.Constraint(rule=source_sink_balance)


# Objective: Minimize total airplanes used
def objective_rule(model):
    return sum(model.flow[('source', f'u_{a}')] for a in model.airports)


model.objective = pyo.Objective(rule=objective_rule, sense=pyo.minimize)

# Solve the model
solver = pyo.SolverFactory('cplex')
results = solver.solve(model)

# Check if solution was found
if results.solver.termination_condition == pyo.TerminationCondition.optimal:
    print("Solution found!")


    # Extract rotations from flow solution
    def extract_rotations(model, flight_data):
        rotations = []
        rotation_paths = []

        # Find all starting points (source to u_airport to v_flight)
        for airport in model.airports:
            source_arc = ('source', f'u_{airport}')
            flow_val = pyo.value(model.flow[source_arc])
            if flow_val > 0.5:
                # For each airplane starting at this airport
                for _ in range(int(round(flow_val))):
                    current = f'u_{airport}'
                    rotation = []
                    path = [current]

                    # Follow the path
                    while current != 'sink':
                        next_node = None
                        # Find outgoing arc with flow
                        for arc in model.arcs:
                            if arc[0] == current and pyo.value(model.flow[arc]) > 0.5:
                                next_node = arc[1]
                                break

                        if next_node is None:
                            break

                        # If we're moving to a flight node
                        if next_node.startswith('v_'):
                            fid = int(next_node.split('_')[1])
                            rotation.append(fid)

                        current = next_node
                        path.append(current)

                    rotations.append(rotation)
                    rotation_paths.append(path)

        return rotations, rotation_paths


    # Get rotations from solution
    rotations, paths = extract_rotations(model, flight_data)
    npmin = len(rotations)
    print(f"Minimum airplanes needed (npmin): {npmin}")
    print("Rotations:", rotations)


    # Instance generation procedure
    def generate_instance(rotations, np, delta):
        # Step (a): P_bar is the set of rotations (airplanes)
        P_bar = list(range(len(rotations)))

        # Step (b): Select subset of np airplanes
        if np > npmin:
            raise ValueError(f"np={np} exceeds npmin={npmin}")
        P_prime = random.sample(P_bar, min(np, len(P_bar)))

        # Step (c): Select subset of delta*np airplanes
        num_selected = max(1, min(len(P_prime), round(delta * np)))
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
        rotations, np_param, delta
    )

    print("\nGenerated instance:")
    print(f"Selected airplanes (P_prime): {P_prime}")
    print(f"Airplanes contributing flights (P_doubleprime): {P_doubleprime}")
    print(f"Initial positions: {initial_positions_prime}")
    print("Flight set:", flight_set)

else:
    print("Model is infeasible or no solution found")
    print("Solver status:", results.solver.termination_condition)

    # Debug: Check flight coverage constraints
    print("\nChecking flight compatibility:")
    for i in model.flights:
        for j in model.flights:
            if i == j:
                continue
            arr_port_i = flight_data[i]['arr_airport']
            dep_port_j = flight_data[j]['dep_airport']
            time_diff = flight_data[j]['dep_time'] - flight_data[i]['arr_time']
            if arr_port_i == dep_port_j and time_diff >= turnaround:
                print(f"Compatible: Flight {i} -> Flight {j} (Time diff: {time_diff} min)")

    # Debug: Check initial positions
    print("\nInitial positions:", initial_positions)

    # Debug: Check if flights can be covered from initial positions
    for fid in model.flights:
        dep_airport = flight_data[fid]['dep_airport']
        if dep_airport not in initial_positions or initial_positions[dep_airport] <= 0:
            print(f"Warning: No initial airplanes at {dep_airport} for flight {fid}")
        else:
            print(f"Flight {fid} can be covered from {dep_airport}")