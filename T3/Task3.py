import csv
from collections import defaultdict

from gurobipy import Model, GRB, quicksum

INPUT_FILE = "toy1.csv"
def parse_car_sharing_csv(filepath):
    reservations = []
    zones = defaultdict(set)
    vehicles = []
    total_days = 0

    current_section = None
    with open(filepath, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile, delimiter=';')
        for row in reader:
            if not row or not row[0].strip():
                continue

            keyword = row[0].strip()
            if keyword.startswith("+Requests"):
                current_section = "requests"
                continue
            elif keyword.startswith("+Zones"):
                current_section = "zones"
                continue
            elif keyword.startswith("+Vehicles"):
                current_section = "vehicles"
                continue
            elif keyword.startswith("+Days"):
                current_section = "days"
                total_days = int(row[0].split(":")[1].strip())
                continue

            if current_section == "requests":
                req_id, zone, day, start, duration, *rest = row
                vehicle_part = rest[:-2]
                penalty1 = int(rest[-2])
                penalty2 = int(rest[-1])
                possible_vehicles = [v for v in vehicle_part if v]
                reservations.append({
                    "id": req_id,
                    "zone": zone,
                    "day": int(day),
                    "start": int(start),
                    "duration": int(duration),
                    "vehicles": possible_vehicles,
                    "penalty1": penalty1,
                    "penalty2": penalty2
                })

            elif current_section == "zones":
                zone_id = row[0].strip()
                adjacent = [z.strip() for z in row[1:] if z.strip()]
                for adj in adjacent:
                    zones[zone_id].add(adj)

            elif current_section == "vehicles":
                vehicles.append(row[0].strip())

    return {
        "reservations": reservations,
        "zones": dict(zones),
        "vehicles": vehicles,
        "days": total_days
    }

# Example usage
data = parse_car_sharing_csv(INPUT_FILE)
print(data["reservations"])
print(data["zones"])


# Sample data
requests = range(3)
vehicles = range(2)
zones = range(2)

start_times = [0, 30, 60]
durations = [60, 60, 60]
preferred_zones = [0, 1, 0]
eligible_zones = [{0, 1}, {0, 1}, {0, 1}]
eligible_vehicles = [{0, 1}, {0}, {1}]
penalty_not_served = [10, 15, 12]
penalty_wrong_zone = [5, 3, 4]

def overlap(r1, r2):
    s1, e1 = start_times[r1], start_times[r1] + durations[r1]
    s2, e2 = start_times[r2], start_times[r2] + durations[r2]
    return max(s1, s2) < min(e1, e2)

# Model
m = Model("CarSharing")

x = {(r, v, z): m.addVar(vtype=GRB.BINARY, name=f"x_{r}_{v}_{z}")
     for r in requests for v in eligible_vehicles[r] for z in eligible_zones[r]}
u = {r: m.addVar(vtype=GRB.BINARY, name=f"u_{r}") for r in requests}  # unserved

m.update()

# Objective: Minimize total penalties
m.setObjective(
    quicksum(penalty_not_served[r] * u[r] for r in requests) +
    quicksum(x[r, v, z] * (penalty_wrong_zone[r] if z != preferred_zones[r] else 0)
             for (r, v, z) in x),
    GRB.MINIMIZE
)

# Each request served once or marked unserved
for r in requests:
    m.addConstr(quicksum(x[r, v, z] for v in eligible_vehicles[r] for z in eligible_zones[r]
                         if (r, v, z) in x) + u[r] == 1)

# No overlapping requests for the same vehicle
for v in vehicles:
    for r1 in requests:
        for r2 in requests:
            if r1 < r2 and overlap(r1, r2):
                for z1 in zones:
                    for z2 in zones:
                        if (r1, v, z1) in x and (r2, v, z2) in x:
                            m.addConstr(x[r1, v, z1] + x[r2, v, z2] <= 1)

m.optimize()

# Output
for r in requests:
    if u[r].X > 0.5:
        print(f"Request {r} not served")
    else:
        for v in eligible_vehicles[r]:
            for z in eligible_zones[r]:
                if (r, v, z) in x and x[r, v, z].X > 0.5:
                    print(f"Request {r} served by vehicle {v} from zone {z}")
