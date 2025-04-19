from gurobipy import Model, GRB, quicksum


INPUT_FILE = "instance2-1.txt"
sep = " "

with open(INPUT_FILE) as f:
    n = int(f.readline())
    m = int(f.readline())

    # p, r,d w
    p = [0 for _ in range(n)]
    r = [0 for _ in range(n)]
    d = [0 for _ in range(n)]
    w = [0 for _ in range(n)]

    for i in range(n):
        p[i], r[i], d[i], w[i]  = map(int, f.readline().split())


def schedule_jobs_max_completed(n, m, p, r, d):
    model = Model("MaxScheduledJobs2")

    # Decision variables
    x = model.addVars(n, vtype=GRB.BINARY, name="x",lb=0,ub=1)  # 1 if job is scheduled
    s = model.addVars(n, vtype=GRB.INTEGER, name="start",lb=0)  # start time of job
    a = model.addVars(n, m, vtype=GRB.BINARY, name="assign",lb=0,ub=1)  # job j assigned to machine k
    y = model.addVars(n, n, vtype=GRB.BINARY, name="lesser",lb=0,ub=1)  # job i earlier job j

    # Objective: maximize number of scheduled jobs
    model.setObjective(quicksum(x[j] for j in range(n)), GRB.MAXIMIZE)

    # Each job can be assigned to at most one machine if it is scheduled
    for j in range(n):
        model.addConstr(quicksum(a[j, k] for k in range(m)) == x[j], name=f"assign_job_{j}")

    # Start time must be after release date
    for j in range(n):
        model.addConstr(s[j] >= r[j]*x[j], name=f"release_{j}")


    # Logical greater /less
    for i in range(n):
        for j in range(i+1,n):
            model.addConstr(y[i,j] + y[j,i] == x[i]*x[j], name=f"lesser1_{i}_{j}")

    # Less condition
    for i in range(n):
        for j in range(n):
            if i==j:
                continue
            model.addConstr(y[i,j] * (s[j] -s[i])>=0, name=f"lesser2_{i}_{j}")


    # No overlapping on same machine
    M = 2*sum(p)
    for i in range(n):
        for j in range(n):
            for k in range(m):
                if j != i:
                    # Enforce disjunctive constraint
                    model.addConstr(
                        s[i] + p[i]<= s[j] + M*(1 -a[i,k]*a[j,k]) + M*(1-y[i,j]), name=f"no_overlap_{j}_{i}_on_{k}"
                    )

    # added constraint on due date:
    for j in range(n):
        model.addConstr(
            (s[j] + p[j])*x[j] <= d[j], name=f"added_due_date_{j}"
        )


    model.setParam("OutputFlag", 0)
    model.optimize()

    # Output results
    if model.status == GRB.OPTIMAL:
        scheduled_jobs = []
        for j in range(n):
            # print(x[j].X,end ="::: ")
            if x[j].X > 0.5:
                # print(s[j].x,":")
                # print(a[j,0].x,a[j,1].x,end="\t\t\t")
                #
                # for i in range(n):
                #     print(y[j,i].x, end=", ")
                #
                # print(j, m)
                # print(a[j, 0].x, a[j, 1].x, end="!!!!")
                assigned_machine = [k for k in range(m) if a[j, k].X > 0.5]
                # print(assigned_machine, end="!!")

                scheduled_jobs.append((j, s[j].X, assigned_machine))
        return scheduled_jobs
    else:
        print(model.status)
        return None


jobs_done = schedule_jobs_max_completed(n, m, p, r, d)
print(jobs_done)



def schedule_jobs_min_penalty(n, m, p, r, d, w):
    model = Model("MinimizePenalty")

    # Variables
    x = model.addVars(n, vtype=GRB.BINARY, name="x")               # scheduled?
    s = model.addVars(n, vtype=GRB.CONTINUOUS, name="start")       # start time
    a = model.addVars(n, m, vtype=GRB.BINARY, name="assign")       # machine assignment
    tard = model.addVars(n, vtype=GRB.CONTINUOUS, name="tardiness")  # tardiness (>=0)
    y = model.addVars(n, n, vtype=GRB.BINARY, name="lesser")  # job i earlier job j

    # Objective: Minimize total weighted tardiness
    model.setObjective(quicksum(w[j] * tard[j] for j in range(n)), GRB.MINIMIZE)

    # Assign each job to at most one machine if scheduled
    for j in range(n):
        model.addConstr(quicksum(a[j, i] for i in range(m)) == x[j], name=f"assign_{j}")

    for j in range(n):
        model.addConstr(x[j]==1, name=f"assign_{j}")

    # Start time must respect release date
    for j in range(n):
        model.addConstr(s[j] >= r[j], name=f"release_{j}")

    # Logical greater /less
    for i in range(n):
        for j in range(i + 1, n):
            model.addConstr(y[i, j] + y[j, i] == 1, name=f"lesser1_{i}_{j}")

    # Less condition
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            model.addConstr(y[i, j] * (s[j] - s[i]) >= 0, name=f"lesser2_{i}_{j}")

    # No overlapping on same machine
    M = 10*sum(p)
    for i in range(n):
        for j in range(n):
            for k in range(m):
                if j != i:
                    # Enforce disjunctive constraint
                    model.addConstr(
                        s[i] + p[i] <= s[j] + M * (1 - a[i, k] * a[j, k]) + M * (1 - y[i, j]),
                        name=f"no_overlap_{i}_{j}_on_{k}"
                    )

    # Tardiness: max(0, finish - due date)
    for j in range(n):
        model.addConstr(tard[j] >= s[j] + p[j] - d[j], name=f"tard_{j}")
        model.addConstr(tard[j] >= 0)


    model.setParam("OutputFlag", 0)
    model.optimize()

    # Output results
    if model.status == GRB.OPTIMAL:
        results = []

        for j in range(n):
            # print(x[j].X, end="::: ")
            # if x[j].X > 0.5:
            #     print(s[j].x, ":")
            #     print(a[j, 0].x, a[j, 1].x, end="\t\t\t")
            #
            #     for i in range(n):
            #         print(y[j, i].x, end=", ")
            #
            # print()
            if x[j].X >= 0.5:
                assigned_machine = [i for i in range(m) if a[j, i].X > 0.5][0]
                results.append({
                    "job": j,
                    "start": s[j].X,
                    "machine": assigned_machine,
                    "tardiness": tard[j].X,
                    "penalty": tard[j].X * w[j]
                })
        return results
    else:
        print("ssss", model.status)
        return None


jobs = schedule_jobs_min_penalty(n, m, p, r, d, w)
for job in jobs:
    print(job, end="\\\\ \n")