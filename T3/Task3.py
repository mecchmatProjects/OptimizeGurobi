import gurobipy as gp
from gurobipy import GRB


def parse_custom_csv(content):
    data = {'requests': [], 'zones': {}, 'vehicles': [], 'days': 0}
    current_section = None
    lines = content.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('+'):
            current_section = line[1:].split(':')[0].strip().lower()
            continue
        if current_section == 'requests':
            fields = line.split(';')
            req = {
                'id': fields[0],
                'zone': fields[1],
                'day': int(fields[2]),
                'start': int(fields[3]),
                'duration': int(fields[4]),
                'vehicles': fields[5].split('\t'),
                'penalty1': int(fields[6]),
                'penalty2': int(fields[7])
            }
            data['requests'].append(req)
        elif current_section == 'zones':
            fields = line.split(';')
            zone = fields[0]
            adjacent = fields[1].split('\t') if len(fields) > 1 else []
            data['zones'][zone] = adjacent
        elif current_section == 'vehicles':
            data['vehicles'].append(line.split(';')[0].strip())
        elif current_section == 'days':
            data['days'] = int(line.strip())
    return data


def solve_with_gurobi(parsed_data):
    model = gp.Model("CarSharing")

    # Create variables
    x = {}
    y = {}

    requests = parsed_data['requests']
    zones = parsed_data['zones']
    vehicles = parsed_data['vehicles']

    for req in requests:
        r = req['id']
        x[r] = model.addVar(vtype=GRB.BINARY, name=f"x_{r}")
        eligible_zones = [req['zone']] + zones[req['zone']]
        for v in req['vehicles']:
            for z in eligible_zones:
                y[(r, v, z)] = model.addVar(vtype=GRB.BINARY, name=f"y_{r}_{v}_{z}")

    # Objective function
    obj = gp.quicksum(
        (1 - x[req['id']]) * req['penalty1'] +
        gp.quicksum(
            y[(req['id'], v, z)] * req['penalty2']
            for v in req['vehicles']
            for z in zones[req['zone']]  # Adjacent zones only
        )
        for req in requests
    )
    model.setObjective(obj, GRB.MINIMIZE)

    # Assignment constraints
    for req in requests:
        r = req['id']
        model.addConstr(
            gp.quicksum(y[(r, v, z)]
                        for v in req['vehicles']
                        for z in [req['zone']] + zones[req['zone']]
                        ) == x[r],
            name=f"assign_{r}"
        )

    # Vehicle conflict constraints (corrected)
    for v in vehicles:
        # Fix: Use correct variable 'v' in list comprehension
        relevant_requests = [req for req in requests if v in req['vehicles']]

        for i in range(len(relevant_requests)):
            req1 = relevant_requests[i]
            eligible_zones1 = [req1['zone']] + zones[req1['zone']]

            for j in range(i + 1, len(relevant_requests)):
                req2 = relevant_requests[j]
                eligible_zones2 = [req2['zone']] + zones[req2['zone']]

                if req1['day'] != req2['day']:
                    continue

                # Check time overlap
                start1 = req1['start']
                end1 = start1 + req1['duration']
                start2 = req2['start']
                end2 = start2 + req2['duration']

                if (start1 < end2) and (start2 < end1):
                    # Corrected: Sum all possible zone assignments
                    model.addConstr(
                        gp.quicksum(y[(req1['id'], v, z)] for z in eligible_zones1) +
                        gp.quicksum(y[(req2['id'], v, z)] for z in eligible_zones2)
                        <= 1,
                        name=f"conflict_{v}_{req1['id']}_{req2['id']}"
                    )

    # Solve and process results
    model.optimize()
    # --- SOLUTION PROCESSING STARTS HERE ---
    results = []
    total_penalty = 0

    if model.status == GRB.OPTIMAL:
        print("\nOptimal solution found!")

        # Process each request
        for req in parsed_data['requests']:
            req_id = req['id']
            served = x[req_id].X > 0.5  # Check if served
            assignment = None
            penalty = 0

            if served:
                # Find vehicle and zone assignment
                for v in req['vehicles']:
                    for z in [req['zone']] + zones[req['zone']]:
                        if y[(req_id, v, z)].X > 0.5:
                            assignment = (v, z)
                            # Check if non-preferred zone
                            if z != req['zone']:
                                penalty = req['penalty2']
                            break
                    if assignment:
                        break
            else:
                # Apply penalty for unserved request
                penalty = req['penalty1']

            total_penalty += penalty
            results.append((req_id, served, assignment))

        # Print detailed results
        print("\nDetailed assignments:")
        for req_id, served, assignment in results:
            if served:
                print(f"{req_id}: Served by {assignment[0]} from zone {assignment[1]}")
            else:
                print(f"{req_id}: NOT SERVED (Penalty: {req['penalty1']})")

        print(f"\nTotal penalty: {total_penalty}")

    else:
        print("No optimal solution found. Status:", model.status)

    return results, total_penalty
#
# # Example data
# csv_content = """+Requests: 10
# req0;z0;0;1072;127;car2	car3	car0	car1	car4;100;20
# req1;z4;1;648;342;car2	car3	car1	car4	car5;100;20
# req2;z4;1;889;166;car3;100;20
# req3;z0;0;885;314;car1;100;20
# req4;z2;0;780;312;car2	car3	car4	car5;100;20
# req5;z0;1;763;265;car2	car3	car0	car1	car4;100;20
# req6;z3;1;922;188;car2;100;20
# req7;z4;0;568;175;car3	car0	car1;100;20
# req8;z1;0;1034;128;car3	car0;100;20
# req9;z4;0;539;335;car3;100;20
# +Zones: 5
# z0;z1
# z1;z0	z2
# z2;z1	z3
# z3;z2	z4
# z4;z3
# +Vehicles: 6
# car0
# car1
# car2
# car3
# car4
# car5
# +Days: 2"""

# Run solution
INPUT_FILE = "instance05.csv" # "toy1.csv"

with open(INPUT_FILE, 'r') as file:
    file_content = file.read()

print(file_content)
parsed_data = parse_custom_csv(file_content)
results, total_penalty = solve_with_gurobi(parsed_data)

# Print results
print("Optimal Assignment:")
for req_id, served, assignment in results:
    if served:
        print(f"{req_id}: Served by {assignment[0]} from {assignment[1]} \\\\")
    else:
        print(f"{req_id}: Not served\\\\")
print(f"\nTotal Penalty: {total_penalty}\\\\")