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

print(p,r,d,w)
def schedule_jobs_max_completed(n, m, p, r):
    model = Model("MaxScheduledJobs2")

    # Decision variables
    s = model.addVars(n, vtype=GRB.INTEGER, name="start",lb=0)  # start time of job
    a = model.addVars(n, m, vtype=GRB.BINARY, name="assign",lb=0,ub=1)  # job j assigned to machine k
    y = model.addVars(n, n, vtype=GRB.BINARY, name="lesser",lb=0,ub=1)  # job i earlier job j
    T = model.addVars(1, vtype=GRB.INTEGER, name="finish",lb=0)

    # Objective: maximize number of scheduled jobs
    model.setObjective(T[0], GRB.MINIMIZE)

    # Each job can be assigned to at most one machine if it is scheduled
    for j in range(n):
        model.addConstr(quicksum(a[j, k] for k in range(m)) == 1, name=f"assign_job_{j}")


    # Start time must be after release date
    for j in range(n):
        model.addConstr(s[j] >= r[j], name=f"release_{j}")


    # Logical greater /less
    for i in range(n):
        for j in range(i+1,n):
            model.addConstr(y[i,j] + y[j,i] == 1, name=f"lesser1_{i}_{j}")

    # Less condition
    for i in range(n):
        for j in range(n):
            if i==j:
                continue
            model.addConstr(y[i,j] * (s[j] -s[i])>=0, name=f"lesser2_{i}_{j}")

    # Finish
    for i in range(n):
        model.addConstr(T[0] >= s[i]+p[i], name=f"fin_{i}")


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

    model.setParam("OutputFlag", 0)
    model.optimize()

    # Output results
    if model.status == GRB.OPTIMAL:
        scheduled_jobs = []
        # print("gggg")
        for j in range(n):

            # print("s=", s[j].x,":")
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
        return scheduled_jobs, T[0].x
    else:
        print(model.status)
        return None


jobs_done, T = schedule_jobs_max_completed(n, m, p, r)
# print(jobs_done)
print(f"Minimal completion time is {T} \\\\ ")
for job in jobs_done:
    print(f"Job {job[0]+1} is starting at {job[1]} on machine {job[2][0]+1} \\\\ ")


