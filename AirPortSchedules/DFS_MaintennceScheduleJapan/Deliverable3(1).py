#!/usr/bin/env python
# coding: utf-8

# #### Objectives:
# 
# Term Project Deliverable 3, requires following tasks to be completed:
# 
# Read (again) and (better) understand the article of "Chellappan and Ali Haghani (2003)". 
# 
# ###### For this deliverable you can use any version of the following codes or modified versions shared with you on Brightspace:
# 
# - class DGraph() or DGraph2() or DGraph3 but it cannot be identical to the class used for your Deliverable 1.
# 
# - read_inputs()
# 
# - Maintenance_Cost()
# 
# - Reassignment_Cost()
# 
#  
# 
#         
# 1 - Modify your Python code of Deliverable 2 to execute the following steps from the original algorithm discussed in article by "Chellappan and Ali Haghani (2003)". The code should be using the functions, variables and data structures created/modified above.
#    
#    ** Make sure ALL your code is properly documented. **
#    
#    ** Submitted codes should run without error. **
#    
#    ** Capacity Data in Excel file will be used to check feasibility in Step 3 below. **
#    
#    ** The code should be able to work with all data files in similar format (different data sizes).
# 
# #### Main() algorithm:
#    
#    read_inputs(filename): #Reading data in the `filename`. 
#    
#    initiate(): # Initiate proper data structures and parameters
#    
#    Max_ Iteration = 1000
#    
#    Iteration = 0
#    
#    
# * Step 0: 
#    
#    Iteration + = 1
#         
#    Copy (or restore) the original flight network data.
#         
#    Make a randomly ordered list of all aircrafts. 
#         
#    Make a randomly ordered list of all nodes (city-day) with degree greater than zero.
#    
#         
# * Step 1:
#    
#    Set n = 1
#         
#    Set k = 1
#    
#    
# 
# * Step 2: 
#         
#    Pick the k-th node in the randomized list of nodes.
#         
#    Create all cycles starting from the k-th node.
#    
#    
# * Step 3:
#    
#    For all cycles identify/calculate:
# 
#        - Required number of aircraft(s) from top of the current randomized list of aircrafts (based on cycle length).
#        - Cycle's minimum feasible average weekly Maintenance and Reassignment cost considering the city's capacity.
#        - Aircraft(s)'s weekly maintenance days.
#    
#    Identify the cycle with "lowest feasible minimum average total weekly Maintenance and Reassignment cost".
#    
#    Assign the aircraft(s) to the cycle.
#    
#    Set `m = number of aircrafts needed for the cycle`
# 
#    Remove the edges of the cycle from the current flight network data.
# 
# 
# * Step 4: 
# 
#    k += 1
# 
#    n += m   
# 
# 
# * Step 5: 
# 
#    If n < number of aircraft go to step 2.
# 
# 
# * Step 6:
# 
#    If the current solution is better than the best solution so far (in terms of Total Weekly, store the current solution: 
#    
#    - `current_solution = (aircraft, maintenance days, weekly cost of maintenance, weekly reassignment cost, total cost, cycle)` 
# 
# 
# * Step 7:
# 
#    if ` Iteration <= Max_ Iteration ` go to Step 0
# 
# 
# * Step 8:
# 
#    Write the final results of the algorithm into `Term Project Article Data.xlsx` in Sheet `Results`.
# 
#    ** See the `Results` sheet for a NEW sample output. Respect the structure and data type and format in your code.
# 
# 2- Run your code on following datafiles:
# 
# - Term Project Article Data.xlsx 
# 
# - Term Project Data 1.xlsx
# 
# - Term Project Data Final
# 
# ONLY Submit the solution Jupyter Notebook file and the above three Excel files includeing the solution (obtained and written in to the file by your code). If needed, you can limit the `Max_ Iteration`  to smaller than 1000 for bigger datafiles to limit the code excution time to 30 min for the datafiles.
# 
# 
#    #### Include your solution below this line. 
#    
#    
# 

# In[1]:


import numpy as np
import pandas as pd
import copy
import time
from openpyxl import load_workbook

filename = 'Term Project Article Data.xlsx'
pageOD = "OD pairs & Reassignment penalty"

def readOD_Reassign_costs(filename,pageOD):
    # Take the data from "OD pairs..." sheet and put it in an array 
    OD_Reassign_costs = pd.read_excel(filename,pageOD,engine='openpyxl')
    OD_Reassign_costs = OD_Reassign_costs.dropna(axis='columns')
    OD_Reassign_costs = np.array(OD_Reassign_costs)

    max_city = len(np.unique(OD_Reassign_costs[:,0]))
    max_day = len(np.unique(OD_Reassign_costs[:,2]))
    max_aircraft = OD_Reassign_costs.shape[1]-3

    return OD_Reassign_costs, max_city, max_day, max_aircraft
    return OD_Reassign_costs, max_city, max_day, max_aircraft


# In[2]:


OD_Reassign_costs, max_city, max_day, max_aircraft = readOD_Reassign_costs(filename,pageOD)
print(f"Number of cities:", max_city)
print(f"Number of days:", max_day)
print(f"Number of aircrafts:", max_aircraft)
print(f"Dimension of adj_mtx: {max_city*max_day} x {max_city*max_day}")


# In[3]:


print(f"OD pairs & Reassignment penalty sheet in array:")
print(OD_Reassign_costs,OD_Reassign_costs.shape)


# In[4]:


pageMT = "Maintenance Type A Cost"
def read_maintenance_city_costs(filename,page):
    print(pageMT)
    # Take the data from "Maintenance Type A Cost" sheet and put it in an array 
    maintenance_city_costs = pd.read_excel(filename,page,engine='openpyxl')
    maintenance_city_costs = maintenance_city_costs.dropna(axis='columns')
    maintenance_city_costs = np.array(maintenance_city_costs)[:,1:].astype("int")
    return maintenance_city_costs


# In[5]:


maintenance_city_costs = read_maintenance_city_costs('Term Project Article Data.xlsx',pageMT)
print(f"Maintenance Type A Cost sheet in array:")
maintenance_city_costs


# In[6]:


#from deliverable 1, in adj_mtx

class DGraph():
    def __init__(self, Nodes):
        self.nodes = [i for i in range(Nodes)]
        self.size = Nodes
        self.adj_mtx = np.zeros([self.size,self.size]) 
        
    def add_edge(self, v,e): # adds edges in the matrix
        self.adj_mtx[v,e]+=1
        
    def rem_edge(self, v,e): # removes edges in the matrix
        if self.adj_mtx[v,e]<=0:
            print("edge does not exist")
        else:
            self.adj_mtx[v,e]-=1
            print("edge has been removed")
            
    def print_adjMtx(self): # print the matrix
        for i in range(self.size):
            print(f"node{i}: {self.adj_mtx[i]}")
            
    def find_all_paths(self, start, end, path = []): # finds all the possible paths
        
        path = path + [start]
        
        #path.append(start)
        
        if start == end:
            return [path]
        paths = []
        
        for node in self.adj_mtx[start].astype(int):
           
            if node not in path and self.adj_mtx[start][node] != 0:
                
                newpaths = self.find_all_paths(node, end, path)
                
                for newpath in newpaths:
                    paths.append(newpath)
            
        return paths
    
    def find_all_cycles(self, start, path = []):
        
        return self.find_all_paths(start, start+7)
    
    def reset(self, adj_mtx):
        self.adj_mtx = adj_mtx


# In[7]:


# Adjacency list
class DGraph2():
    def __init__(self,nodes, edges):
        self.nodes = nodes
        self.size = len(nodes)
        self.adj_list = {} 
        
        for node in nodes:
            self.adj_list[node] = []
        
        for edge in edges:
            self.add_edge(edge[0],edge[1])
        
        self.visited = {nod:False for nod in self.nodes}    
        self.backup = copy.deepcopy(self.adj_list)
                
    def add_edge(self, v,e):
        self.adj_list[v].append(e)  

    def rem_edge(self, v,e):
        if e not in self.adj_list[v]:
            print("edge not existing")
        else:
            self.adj_list[v].remove(e) 


    def print_adjList(self):
        for i in self.nodes:
            print(f"node {i}: {self.adj_list[i]}")


    def find_all_paths(self, start, end, path = []):
        
        print("se:",start,end)
        # If start = end node, best case scenario
        path = path + [start]
        
        if start == end:
            return [path]
        # 
        paths = []
        # check all the untouched nodes
        for node in self.adj_list[start]:

            if self.visited[node]:
               continue                  
            if node not in path:
                # determine the track from connected node to end node
                newpaths = self.find_all_paths(node, end, path)
    
                # create new path
                for newpath in newpaths:
                    paths.append(newpath)
        return paths
    
    
    def find_all_cycles(self, start):

        cycles = [] # create an empty list

        for node in self.adj_list[start]: # all nodes connected to the first node 
            
            self.visited = {nod:False for nod in self.nodes}     
            if node not in [start]:
                newpaths = self.find_all_paths(node, start, []) # determine the way from every node to start node
                print("x")	
                for newpath in newpaths:
                    cycles.append([start]  + newpath) 

        return cycles    

    def reset(self):
        self.adj_list = copy.deepcopy(self.backup) 




# In[26]:


# Incident Matrix
class DGraph3():
    def __init__(self, nodes, edges):
        self.nodes = nodes
        self.edges = edges
        m = max(self.nodes)
        self.ind_mtx = np.zeros([m+1,m+1])
    
        
        for vertices in edges:
            
            vertex1 = vertices[0]
            vertex2 = vertices[1]
            
            self.add_edge(vertex1,vertex2)
            
        self.backup = copy.deepcopy(self.ind_mtx)
                
    def add_edge(self,v,e):
        
        for edge, vertices in enumerate(self.edges):
            vertice1 = vertices[0]
            vertice2 = vertices[1]
            if vertice1 == v and vertice2 == e:
                self.ind_mtx[vertice1,vertice2] +=1 
                self.ind_mtx[vertice2,vertice1] +=1 

    def rem_edge(self,v,e):        
        for edge, vertices in enumerate(self.edges):
            vertice1 = vertices[0]
            vertice2 = vertices[1]
            if vertice1 == v and vertice2 == e:
                if (self.ind_mtx[vertice1,vertice2]>=1) and (self.ind_mtx[vertice2,vertice1]>=1):
                    self.ind_mtx[vertice1,vertice2] -=1 
                    self.ind_mtx[vertice2,vertice1] -=1 
                    return
                else:
                    return False                   
        return False

    def print_indMtx(self):
        for i in range(len(self.nodes)):
            print(self.ind_mtx[i])

    def find_all_paths(self, start, end, path = []):
        
        # If start = end node, best case scenario
        path = path + [start]
        
        if start == end:
            return [path]
               
        paths = []
        
        # every node to start node that has not been touched
        
        for edge, vertices in enumerate(self.edges):
            
            
            if vertices[0] == start:
                node = vertices[1]
                
                
                if node not in path:
                    if self.ind_mtx[start,vertices[1]] >=1 and self.ind_mtx[node,vertices[0]] >=1:
                        
                        newpaths = self.find_all_paths(node, end, path)
                    # creates a new path
                        for newpath in newpaths:
                            paths.append(newpath)

        return paths
    
    def find_all_cycles(self, start):

        cycles = [] # create an empty list
        
        for edge, vertices in enumerate(self.edges):
            if vertices[0] == start:
                node = vertices[1]
                if self.ind_mtx[start,vertices[1]] >=1 and self.ind_mtx[node,vertices[0]] >=1:
                    
                    newpaths = self.find_all_paths(node, start, []) #finds all path from node back to start
                    for newpath in newpaths:
                        
                        cycles.append([start] + newpath) 

        return cycles    

    
    def reset(self):
        self.ind_mtx = copy.deepcopy(self.backup) 


# In[27]:


def read_inputs(filename): #Reading data files

    global OD_data, max_city, max_day, max_aircraft


    OD_data = pd.read_excel(filename,"OD pairs & Reassignment penalty",engine='openpyxl')
    OD_data = OD_data.dropna(axis='columns')
    OD_data = np.array(OD_data)

    max_city = len(np.unique(OD_data[:,0]))
    max_day = len(np.unique(OD_data[:,2]))
    max_aircraft = OD_data.shape[1]-3

    print(f"we have {max_city} cities and {max_day} days and {max_aircraft} aircrafts" )
    print(f"The adj_mtx should be a {max_city*max_day} x {max_city*max_day} matrix")


# In[28]:


def initiate(filename): # Initiate proper data structures and parameters

    global OD_Reassign_costs, start_nodes, edges, maintenance_city, nodes

    OD_Reassign_costs = np.zeros([max_city*max_day,max_city*max_day,max_aircraft]).astype("int")

    start_nodes = []
    edges = []
    
    nodes_set = set()

    for i in range(OD_data.shape[0]):

        origin_city = OD_data[i][0]-1 # remember index starts from 0 !!!!
        destination_city = OD_data[i][1]-1
        departure_day = OD_data[i][2]
        arrival_day = departure_day+1

        # print("S",origin_city, destination_city, departure_day, arrival_day)

        # let's convert the pari of "origin, day" into the index (row)
        ori_day = origin_city*max_day + departure_day%max_day # recall day 8 means day 1 of the next week

        # let's convert the pari of "destination, day" into the index (col)
        des_day = destination_city*max_day + arrival_day%max_day

        # print("OD",ori_day,des_day)

        
        
        for j in range(max_aircraft):
            OD_Reassign_costs[ori_day,des_day,j] += OD_data[i,3+j]

        edges.append([ori_day,des_day])
        
        nodes_set.add(ori_day)
        # nodes_set.add(des_day)

        if departure_day==0:
            start_nodes.append(ori_day)

    nodes = list(nodes_set)     
    
    maintenance_city = pd.read_excel(filename,"Maintenance Type A Cost",engine='openpyxl')
    maintenance_city = maintenance_city.dropna(axis='columns')
    maintenance_city = np.array(maintenance_city)[:,1:].astype("int")

    


# In[29]:


def Maintenance_Cost(cycle, aircraft, maintenance): # calculate's minimum maintenance
    # store all possible combinations of weekdays for type A maintenance
    maintenance_path = [[5,1], [5,2], [6,2], [6,3], [0,3], [0,4], [1,4]]

    
    # print(cycle)   
    # print(maintenance_city,maintenance_city.shape)
    cost = []
    
    # number of weeks
    weeks = len(cycle) // max_day

    # for every node of cycle
    for path in maintenance_path:

        day_1 = path[0] 
        day_2 = path[1]
        price = 0
        for i in range(weeks):        
            city1 = cycle[day_1 + i * max_day]//max_day
            city2 = cycle[day_2 + i * max_day]//max_day
            price += maintenance[aircraft][city1] + maintenance[aircraft][city2] 

        cost.append(price)

    min_cost = min(cost) # obtaining min value from the list
    opt_path = maintenance_path[cost.index(min(cost))] # obtaining the value of optimal path

    # print(opt_path, min_cost)
    return opt_path, min_cost # return minimum maintenance cost



# In[30]:


# Calculates the cost of reassignments
def Reassignment_Cost(cycle, aircraft, cost_mtx = OD_Reassign_costs):
    cost = 0
    # print("ReC",cost_mtx,cost_mtx.shape)
    # print("pl", aircraft)
    # print("c", cycle)
    
    # number of weeks
    weeks = len(cycle) // max_day
    
    for i in range(len(cycle)-1):
        
        cost += cost_mtx[cycle[i],cycle[i+1],aircraft]
    
    #cost += cost_mtx[cycle[-1],cycle[0],aircraft]
    
    # print(cost/weeks)
    # input()
    
    return cost/weeks


# In[31]:


# main Optimization routine
# graph - is our Graph class (either Graph2, or Graph3)
# iteration_number - number of iterations (300 by default)
import sys
def optimization(graph, iteration_number=10):

    Max_Iteration = iteration_number
    Iteration = 0
    aircrafts_list = [i for i in range(max_aircraft)]

    min_cost = sys.float_info.max # start with maximum possible result
    costs = None # result variable
    
    # Step 7:
    # if Iteration <= Max_ Iteration go to Step 0 
    while Iteration<Max_Iteration:

        
        # Step 0:
        #         Iteration + = 1
        Iteration+=1
        #         Copy (or restore) the original flight network data.
        graph.reset()
        #         Make a randomly ordered list of all aircrafts.
        np.random.shuffle(aircrafts_list)
        #         Make a randomly ordered list of all nodes (city-day) with degree greater than zero.
        nodes_copy = copy.deepcopy(start_nodes)
        np.random.shuffle(nodes_copy)
        
        print(f"nodes_copy{nodes_copy}")

        solution = [None for i in range(max_aircraft)]
        min_cycle = []
        min_iter_cost = sys.float_info.max
        iter_costs = None
        
        # print("Iteration", Iteration)
        # input()
        # Step 1 
        n = 1
        
        sol = None
        sol_total_sum = 0

        # Step 5:
        # If n < number of aircraft go to step 2.
        while n<= max_aircraft:
            
            plane = aircrafts_list[n-1]
            print(f"plane({n}){plane}")
            
            # Step 2:
            # Pick the k-th node in the randomized list of nodes.
            k = 1
            while k <= len(nodes_copy):
               
                node = nodes_copy[k-1]

                # Create all cycles starting from the k-th node.
                all_cycles = graph.find_all_cycles(node)
                # print(all_cycles)
                print("NK", n, k)
                  
                # Checking the feasibility 
                if len(all_cycles) == 0:
                    k += 1
                    continue

                # Step 3:
                min_current_cost  = sys.float_info.max
                min_loop = -1
                min_current_maint = -1
                min_current_maint_cost = -1
                min_reassig_cost = -1
                fnd_cycle = None        

                # For all cycles identify/calculate:
                for ind,cycle in enumerate(all_cycles):
                    
                    # only 7-day loops are interesting
                    if len(cycle) % max_day != 1:
                        print("wrong loop", cycle)
                        #input()
                        continue

                    
                    print("good loop", cycle)    
                    #  - Required number of aircraft(s) from top of the current randomized list of aircrafts (based on cycle length).
                    num_aircrafts = 1

                    
                    #  - Cycle's minimum average weekly Maintenance and Reassignment cost.
                    #  - Aircraft(s)'s weekly maintenance days.
                    opt_maint, maint_cost = Maintenance_Cost(cycle, plane,maintenance_city)
                    reassig_cost = Reassignment_Cost(cycle, plane,OD_Reassign_costs)
                    current_cost =  maint_cost + reassig_cost
                    #total_cost = sum(maint_cost) + sum(reassig_cost)
                    #total_cost = min(total_costs)
                    
                    # print("cost", current_cost)    


                    # Identify the cycle with "lowest minimum average total weekly Maintenance and Reassignment cost".     
                    # Assign the aircraft(s) to the cycle.
                    if current_cost < min_current_cost:
                       min_loop = ind
                       min_current_maint = opt_maint
                       min_current_maint_cost = maint_cost
                       min_reassig_cost = reassig_cost
                       min_current_cost = current_cost
                       fnd_cycle = copy.deepcopy(cycle)

                    # print("Result_current", min_current_maint, min_current_maint_cost, min_reassig_cost)    
                    # input()
                    # end loop in cycles
                    
                #Step 4:
                # k += 1
                if min_loop==-1:
                    k += 1
                    continue
                

                #cycle = all_cycles[min_loop]
                # Remove the edges of the cycle from the current flight network data.                        
                for day in range(len(fnd_cycle)-1):      
                    graph.rem_edge(fnd_cycle[day],fnd_cycle[day+1])
                
                # graph.rem_edge(fnd_cycle[-1],fnd_cycle[0])
                
                solution[n-1] = [plane,min_current_maint,min_current_maint_cost,min_reassig_cost,min_current_cost, fnd_cycle]

                # print(f"find min loop, add to solution{n}_{k}")
                
                # print("cycle",fnd_cycle)
                # print(plane,min_current_maint,min_current_maint_cost,min_reassig_cost,min_current_cost)
                # input()
                # we find good combination 
                break        
                # 
                # END Loop in k
                 
            # n += m
            if solution[n-1]:
                #print(f"sol for {n}:{solution[n-1]}")
                #solution.append(sol)
                #sol = None
                sol_total_sum += min_current_cost
                
                if n == max_aircraft:
                    # print("gather",solution,"cost",sol_total_sum,"iter", min_iter_cost)
                    # costs = solution
                    # Step 6:
                    # If the current solution is better than the best solution so far (in terms of Total Weekly, store the current solution:
                    # current_solution = (aircraft, maintenance days, weekly cost of maintenance, weekly reassignment cost, total cost, cycle)

                    if min_iter_cost > sol_total_sum:
                        min_iter_cost = sol_total_sum
                        iter_costs = solution
                    # print(iter_costs)
                n += 1
                # input()
            else:
                
                sol_total_sum = 0
                solution = [None for i in range(max_aircraft)]
                break
            # end loop in n
        
        print(f"compare{min_cost} {min_iter_cost}")    
        if min_cost > min_iter_cost:
            min_cost = min_iter_cost
            costs = iter_costs
            
        print(costs)
        print("end iteration")
        # input()
        # end iterations

                        
    return min_cost, costs


# In[32]:


# write resulting solution to excel file 
# filename - name of excel file
# solution - list of optimal routes as lists
def write_solution(filename, solution):


    if not solution:
        return        
    solution = sorted(solution,key= lambda t:t[0])

    n = len(solution)
    text = []
    m_sum = 0
    r_sum = 0
    t_sum = 0

    for item in solution:
        air_plane = item[0]+1 # plane
        maint = str(item[1]) # maintanence schedule  
        m_cost = item[2]
        r_cost = item[3]
        t_cost = item[4]
        # calculate sums
        m_sum += m_cost
        r_sum += r_cost
        t_sum += t_cost
    
        # last column to create it as the special format row 
        loop_plane = "["
        for it in item[5][:-1]:
            city = it // max_day + 1
            day = it % max_day
            loop_plane += "{}({}),".format(city,day) 
        
        loop_plane = loop_plane[:-1] + "]"
        # add row data to DataFrame
        text.append([air_plane,maint, m_cost,r_cost ,t_cost,loop_plane ])
    
    # add sums
    text.append(["","",m_sum,r_sum,t_sum,""])
    # save to excel file
    df = pd.DataFrame(text, columns =[ 'Aircraft','Maintenance Days','Weekly Cost of Maintenance','Weekly Reassignment Cost','Total Cost','Cycle'])        
    with pd.ExcelWriter(filename,engine = 'openpyxl', mode = 'a', if_sheet_exists = 'overlay') as writer:
        df.to_excel(writer, sheet_name = 'Results',index=False)


# In[33]:


# create Graph from filename as Adjacency list
def form_graph2(filename):
    
    # read inputs
    read_inputs(filename)
    # initialize variables
    initiate(filename)
    
    # print( graph.nodes, graph.size, graph.adj_list)
    """
    print("nodes")    
    print(nodes)
    print(edges)
    print(start_nodes)
    print("go!!!")
    """
    graph = DGraph2(nodes,edges)
    return graph

# create Graph from filename as Identity matrix
def form_graph3(filename):
    
    # read inputs
    read_inputs(filename)
    # initialize variables
    initiate(filename)
    
    # print( graph.nodes, graph.size, graph.adj_list)
    """
    print("nodes")    
    print(nodes)
    print(edges)
    print(start_nodes)
    print("go!!!")
    """
    graph = DGraph3(nodes,edges)
    return graph

def main(filename):
    # here we can change Graph constructor
    graph1 = form_graph2(filename)
    
    min_cost, res = optimization(graph1)
    print("Minimal cost of schedule is ", min_cost)
    
    write_solution(filename,res)  
    return res



# In[34]:


# just call the main function to start execution
# for the first file
filename = 'Term Project Article Data.xlsx'
result = main(filename)
print("Resulting schedule as list:", result)

# for the second file
filename = 'Term Project Data 1.xlsx'
result = main(filename)
print("Resulting schedule as list:", result)
"""
# for the third file
filename = 'Term Project Data Final.xlsx'
result = main(filename)
print("Resulting schedule as list:", result)
"""
# 

# In[ ]:





# In[ ]:




