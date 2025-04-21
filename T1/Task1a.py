import sys

from gurobipy import Model, GRB, quicksum

INPUT_FILE = "instance1-1.txt"
sep = ","
P, W, C = None, None, None

if __name__ == "__main__":
    with open(INPUT_FILE) as f:
        P, W, C = map(int, f.readline().split(sep))

        # Sets
        plants = range(P)
        warehouses = range(W)
        customers = range(C)

        supply = list(map(int,f.readline().split(sep)))
        capacity = list(map(int, f.readline().split(sep)))
        demand = list(map(int, f.readline().split(sep)))

        # Cost matrices
        a = []
        for _ in range(P):
            # cost from plant i to warehouse j
            a_row = list(map(int, f.readline().split(sep)))
            a.append(a_row)


        b = []
        for _ in range(W):
            # cost from warehouse j to customer k
            b_row = list(map(int, f.readline().split(sep)))
            b.append(b_row)

    if C is None:
        sys.exit()
    # Model
    model = Model("TransportationNetwork")

    # Variables
    x = model.addVars(plants, warehouses, name="x", lb=0)  # Plant -> Warehouse
    y = model.addVars(warehouses, customers, name="y", lb=0)  # Warehouse -> Customer



    # Objective: minimize total cost
    model.setObjective(
        quicksum(a[i][j] * x[i, j] for i in plants for j in warehouses) +
        quicksum(b[j][k] * y[j, k] for j in warehouses for k in customers),
        GRB.MINIMIZE
    )

    # Constraints
    for i in plants:
        model.addConstr(quicksum(x[i, j] for j in warehouses) <= supply[i])

    for j in warehouses:
        model.addConstr(quicksum(y[j, k] for k in customers) <= capacity[j])

    for k in customers:
        model.addConstr(quicksum(y[j, k] for j in warehouses) >= demand[k])

    for j in warehouses:
        model.addConstr(quicksum(x[i, j] for i in plants) >= quicksum(y[j, k] for k in customers))

    # Solve
    model.optimize()

    # Print solution
    if model.status == GRB.OPTIMAL:
        print("Objective value:", model.ObjVal)
        for i in plants:
            for j in warehouses:
                if x[i, j].X > 0:
                    print(f"Ship {x[i,j].X} from Plant {i} to Warehouse {j} \\\\")
        for j in warehouses:
            for k in customers:
                if y[j, k].X > 0:
                    print(f"Ship {y[j,k].X} from Warehouse {j} to Customer {k} \\\\ ")
