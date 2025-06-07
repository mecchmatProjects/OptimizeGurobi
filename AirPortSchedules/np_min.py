from datetime import datetime, timedelta
import bisect
import networkx as nx


def parse_time(time_str):
    return datetime.strptime(time_str, "%d.%m.%Y %H:%M")


# Precompute compatible flights
def precompute_compatibility(flights, delta_t):
    # Group flights by departure airport
    deps = {}
    for i, (_, dep_air, _, dep_time, _) in flights.items():
        deps.setdefault(dep_air, []).append((parse_time(dep_time), i))

    # Sort by departure time
    for air in deps:
        deps[air].sort(key=lambda x: x[0])

    compatibility = {}
    for i, (_, _, arr_air, _, arr_time) in flights.items():
        arr_time = parse_time(arr_time)
        min_dep_time = arr_time + delta_t
        compat_flights = []
        if arr_air in deps:
            # Binary search for first compatible flight
            times = [t for t, _ in deps[arr_air]]
            pos = bisect.bisect_left(times, min_dep_time)
            compat_flights = [fid for (_, fid) in deps[arr_air][pos:]]
        compatibility[i] = compat_flights
    return compatibility


def compute_npmin(flights, initial_pos, delta_t_minutes):
    # Convert delta_t to timedelta
    delta_t = timedelta(minutes=delta_t_minutes)
    # Precompute compatibility
    compat_map = precompute_compatibility(flights, delta_t)

    # Create flow network
    G = nx.DiGraph()

    # Add nodes with demands
    airports = set()
    for fid, (_, dep_air, arr_air, _, _) in flights.items():
        G.add_node(f"d_{fid}", demand=-1)
        G.add_node(f"a_{fid}", demand=1)
        airports.add(dep_air)
        airports.add(arr_air)

    # Add initial/final nodes
    for air in airports:
        G.add_node(f"I_{air}", demand=0)
        G.add_node(f"F_{air}", demand=0)

    # Add source/sink
    G.add_node("s", demand=0)
    G.add_node("t", demand=0)

    # Add initial position arcs
    for air, count in initial_pos.items():
        G.add_edge("s", f"I_{air}", weight=1, capacity=float('inf'))

    # Add flight start/end arcs
    for fid, (_, dep_air, arr_air, _, _) in flights.items():
        # Initial position to departure
        G.add_edge(f"I_{dep_air}", f"d_{fid}", weight=0, capacity=1)

        # Flight coverage
        G.add_edge(f"d_{fid}", f"a_{fid}", weight=0, lower_bound=1, capacity=1)

        # Arrival to final position
        G.add_edge(f"a_{fid}", f"F_{arr_air}", weight=0, capacity=1)

    # Add compatible flight connections
    for i, compat_list in compat_map.items():
        for j in compat_list:
            G.add_edge(f"a_{i}", f"d_{j}", weight=0, capacity=1)

    # Add final position to sink
    for air in airports:
        G.add_edge(f"F_{air}", "t", weight=0, capacity=float('inf'))

    # Solve min-cost flow
    flow = nx.min_cost_flow(G)
    npmin = sum(flow["s"][f"I_{air}"] for air in airports)
    return npmin


# Flight data (flight_id: (flight_id, dep_air, arr_air, dep_time, arr_time))
flights = {
    1: (1, "A", "B", "1.10.2016 09:00", "1.10.2016 11:00"),
    2: (2, "B", "A", "1.10.2016 11:30", "1.10.2016 13:30"),
    3: (3, "A", "B", "1.10.2016 14:00", "1.10.2016 16:00"),
    4: (4, "B", "A", "1.10.2016 09:30", "1.10.2016 11:30"),
    5: (5, "A", "B", "1.10.2016 12:00", "1.10.2016 14:00"),
    6: (6, "B", "A", "1.10.2016 14:30", "1.10.2016 16:30")
}

# Initial positions {airport: count}
initial_pos = {"A": 1, "B": 1}

# Compute minimum airplanes needed
npmin = compute_npmin(flights, initial_pos, delta_t_minutes=30)
print(f"Minimum airplanes required: {npmin}")