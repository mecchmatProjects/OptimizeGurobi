import copy
import numpy as np
import pandas as pd
import time
from openpyxl import load_workbook
np.random.seed(0)

#set parameters
MAX_ITERATIONS = 10
EXCEL_FILE = "Term Project Article Data.xlsx"


def input_Table1(fname):
    global max_cities, max_days, number_of_aircrafts, OD_pairs, OD_Reassign_costs
    # Read Data from the file "OD pairs & Reassignemnt penalty"
    read_data =  pd.read_excel(fname,"OD pairs & Reassignment penalty",engine='openpyxl')
    read_data = read_data.dropna(axis='columns')
    read_data = np.array(read_data)
    # Get Unique Elements from 'read_data' using 'unique' Method.
    # unique : finds the unique elements of an array and returns these unique elements as a sorted array.
    origin_column_unique = np.unique(read_data[1:,0])
    day_column_unique = np.unique(read_data[1:,2])

    #store the max cities, days and aircrafts
    max_cities = len(origin_column_unique)
    max_days = len(day_column_unique)
    number_of_aircrafts = read_data.shape[1]-3

    #  cast 'read_data' to a specified type.
    OD_pairs = read_data[0: , 0:3].astype(int)

    ''' 
        1 - B : OD pair's reassignment penalties (column D and after in OD pairs & Reassignment penalty.csv ) 
                shall be recorded in a matrix OD_Reassign_costs.
    '''
    OD_Reassign_costs = read_data[0:, 3:]

  

'''
     1 - C : Aircraft's maintenance cost in each city found in Maintenance Type A Cost.xlxs , should be
             recorded in maintained_city matrix. maintained_city_costs[i][j] identifies the cost of maintaining
             the aircraft i in city j.
'''
def input_Table2(fname):
    global maintainance_city_costs, number_of_aircrafts
    maintenance_data =  pd.read_excel(fname,"Maintenance Type A Cost",engine='openpyxl')
    maintenance_data = maintenance_data.dropna(axis='columns')
    maintainance_city_costs = np.array(maintenance_data)[:number_of_aircrafts,1:].astype("int")
  

class DGraph():
  # Constructor for initialization Purpose
  def __init__(self, nodes):
    self.nodes = nodes
    self.adj_List = {}
    self.deg_in = {}
    self.deg_out = {}
    self.degree = 0
        
    for node in self.nodes:
      self.adj_List[node] = []
      self.deg_in[node] = 0
      self.deg_out[node] = 0

  # Find Path between two nodes Method
  def find_paths(self, graph, start, end, path):     
    path +=[start]
    # Considering best case scenario , start is the end node
    # if that is the case then return [path]
    if start == end:
      return [path]
        
    # Recursively find path from staring node(start) to ending node(end)
    all_paths = []
    for node in graph.adj_List[start]:
      if node not in path:
        # finding path connected node->end
        find_path = self.find_paths(graph, node, end, path)
        # adding find_path in all_path
        for pth in find_path:
          all_paths.append(pth)
    return all_paths
    
  # ADD Edge Method
  def add_edge(self, vertex, edge):
    # Add given edge to given vertex
    self.adj_List[vertex].append(edge)
    # Increase 'Degree in' of given edge
    # Also Increment 'Degree out' of given vertex
    self.deg_in[edge] += 1
    self.deg_out[vertex] += 1
    self.degree += 1

  # Remove Edge Method
  def remove_edge(self, vertex, edge):
    # Checking if Either given edge exist or not , if not then simply return
    if edge not in self.adj_List[vertex] or vertex not in self.adj_List[edge]:
      # print("Edge does not exist")
      return
    # Removing edge
    self.adj_List[vertex].remove(edge)
    # print("Edge removed!")
    # Decrement 'degree in' of edge by 1
    # Also decrement 'degree out' of vertex by 1
    self.deg_in[edge] -= 1
    self.deg_out[vertex] -= 1
    self.degree -= 1

  # Find Cycles Method
  def find_cycles(self, graph, start):
  # Creating list of all_cycles to find all nodes accessible from the start node
    all_cycles = [] 
    for node in graph.adj_List[start]:  
      if node not in [start]:
        new_cycle = self.find_paths(graph, node, start, []) 

        for cyc in new_cycle:
          all_cycles.append([start] + cyc) 

    return all_cycles
  
  # Display Method
  def display_adj_List(self):
    for node in self.nodes:
      print(node," : ",self.adj_List[node])
    
  def reset(self):
    self.adj_List = copy.deepcopy(self.backup) 


class DGraph2():
  # Constructor for initialization Purpose
  def __init__(self,edges,nodes):
    self.nodes = nodes
    # Return a new Matrix, filled with zeros.
    self.adj_Matrix = np.zeros([len(nodes),len(nodes)])    
    for edge in edges:
      self.add_edge(edge[0],edge[1])

  # Find Path between two nodes Method
  def find_paths(self, start, end, path = []):
    path += [start]
    # Considering best case scenario , start is the end node
    # if that is the case then return [path]
    if start == end:
      return [path]
    if start != end:
      paths = []
    # Recursively find path from staring node(start) to ending node(end)
    for Node in range(len(self.nodes)):
      if Node not in path and self.adj_Matrix[start,Node]>0:
        newpaths = self.find_paths(Node, end, path)
        for newpath in newpaths:
          paths.append(newpath)
      return paths

  # Add edge Method
  def add_edge(self, ver, edg):
    self.adj_Matrix[ver,edg] +=1 

  # Find Cycle Method
  def find_cycles(self, start):
    # creating a list of cycles for all nodes accessible from the given node (start)
    cycles = [] 
    for Node in range(len(self.nodes)): 
      if self.adj_Matrix[start,Node]>=1:
        newpaths = self.find_paths(Node, start, []) 
        for newpath in newpaths:
          cycles.append([start] + newpath) 
    return cycles 
    
  # Remove edge Method
  def remove_edge(self, ver, edg):
    if self.adj_Matrix[ver,edg]>0:
      self.adj_Matrix[ver,edg]-=1
    else:
      # print("Edge does not exist!")
      return
   
  # Display matrix Method
  def display_adj_Matrix(self):
    for i in range(len(self.nodes)):
      print(self.adj_Matrix[i])
    
  def reset(self):
    self.adj_Matrix = copy.deepcopy(self.backup) 


class DGraph3():
  def __init__(self, Nodes):
    self.nodes = Nodes
    self.adjList = {}
    self.in_deg = {}
    self.out_deg = {}
    self.degree = 0
        
    for node in self.nodes:
      self.adjList[node] = []
      self.in_deg[node] = 0
      self.out_deg[node] = 0
            
    
  def add_edge(self, v, e):
    self.adjList[v].append(e)
    self.in_deg[e] += 1
    self.out_deg[v] += 1
    self.degree += 1
            

  def remove_edge(self, v, e):
    if e not in self.adjList[v] or v not in self.adjList[e]:
      # print("Edge does not exist")
      return
    self.adjList[v].remove(e)
    # print("Edge is removed")
    self.in_deg[e] -= 1
    self.out_deg[v] -= 1
    self.degree -= 1
  """
  def find_all_paths(self, start, end, path):
    path = path + [start]
    if start == end:
      return [path]
    paths = []
    for node in self.adjList[start]:
      if node not in path:
        newpaths = self.find_all_paths(node, end, path)
        for newpath in newpaths:
          paths.append(newpath)
    return paths

  def find_all_cycles1(self, start):
    cycles = [] # create an empty list of cycles
    for node in self.adjList[start]: # for all nodes reachable from start node 
      if node not in [start]:
        newpaths = self.find_all_paths(node, start, []) #finds all path from node back to start

        for newpath in newpaths:
          cycles.append([start]  + newpath) #constructs a cycle by addeing the start + a path as a cycle
    return cycles
  """
  
  def find_all_paths(self, start, end, path = []):
        
    # If start = end node, best case scenario
    path = path + [start]
        
    if start == end:
      return [path]
        # 
    paths = []
    # check all the untouched nodes
    for node in self.adjList[start]:

      if node not in path:
        # determine the track from connected node to end node
        newpaths = self.find_all_paths(node, end, path)
    
        # create new path
        for newpath in newpaths:
          paths.append(newpath)
    return paths
    
    
  def find_all_cycles1(self, start):

    cycles = [] # create an empty list

    for node in self.adjList[start]: # all nodes connected to the first node 
            
      if node not in [start]:
        newpaths = self.find_all_paths(node, start, []) # determine the way from every node to start node
        # print("x")	
        for newpath in newpaths:
          cycles.append([start]  + newpath) 

    return cycles    

        
  def print_adjList(self):
    for node in self.nodes:
      print(node,":",self.adjList[node])


def readNode(node):
    numbers = [int(s) for s in node if s.isdigit()]
    if len(numbers) ==2:        
        return numbers[0], numbers[1]

def setNode(city_index, day_index):
  return (str(city_index) + "(" + str(day_index) + ")")

def initiate_graph():  
  global max_city, max_day
  global OD_reassign_costs, OD_Graph
  global OD_pairs, reassign_costs
  global graph
    
    
  nodes = []
  for i in range(max_cities):
    for j in range(max_days):
      nodes.append(setNode(i+1, j)) 
            
  # Iterate throught the OD_pairs to make edges
  edges = {}
  for i in range(OD_pairs.shape[0]):
        
    origin_column_index = int(OD_pairs[i][0])
        
    destination_column_index = int(OD_pairs[i][1])
        
    departure_day_index = int(OD_pairs[i][2])
        
    # find nodes from the OD_pairs to build edges
    node1 = setNode(origin_column_index, departure_day_index)
    node2 = setNode(destination_column_index, (departure_day_index + 1) % max_cities)
    
        
    edges[(node1, node2)] = OD_Reassign_costs[i]
        
    reassign_costs = edges
    
        
    OD_Graph = DGraph3(nodes)
        
    # iterate and add edges to Dgraph
    for edge in edges:
      OD_Graph.add_edge(edge[0], edge[1])
            
    
  return OD_Graph


#City-day network planing as discussed in Figure-1 of the article
# graph = initiate_graph()


def Maintenance_Cost(flights, aircrafts):

    # only 7 combinations for 7 days possible
    maintenance_cycles = [[5,1],[5,2],[6,2],[6,3],[0,3],[0,4],[1,4]]

    optOption = [[]]*len(aircrafts)
    weeklyCost = [[]]*len(aircrafts)

    for index, aircraft in enumerate(aircrafts[:-1]):
      cost = []
      for option in maintenance_cycles:
        current_cost = 0
        for leg in range(len(flights)):
          city_day = flights[leg]
          day = int(city_day[0])%max_days
          if day in option:
            city = 0 # int(city_day[0])//max_days
            current_cost +=maintainance_city_costs[index,city]

        cost.append(current_cost)

        if current_cost==min(cost):
          optOption[index] = option
          weeklyCost[index] = current_cost/len(aircrafts)

    return optOption, weeklyCost

def Reassignment_Cost(cycle, aircrafts):
    global number_of_aircrafts

    # get the length of the aircraft
    aircraft_number = number_of_aircrafts

    # Verifying if input data is valid
    if len(cycle)  != 7 * aircraft_number + 1:
    #  # print("Reassign Cost Error")
      return [0 for _ in range(aircraft_number)]

    # reassign (weekly) cost dictionary
    reassignment_costs = {}

    # for every pair node of the cycle
    for j in aircrafts:
      reassignment_costs[j] = 0
      for i in range (len(cycle)-1):
        reassignment_costs[j] += OD_Reassign_costs[int(cycle[i][0])][j-1] / aircraft_number

    return reassignment_costs

TABLE_1 =[
[0,	"[6, 3]",	5,	10.0,	15.0,	"[4(0),3(1),3(2),5(3),2(4),4(5),0(6)]"],
[1,	"[0, 4]",	2,	11.0,	13.0,	"[2(0),1(1),1(2),6(3),2(4),1(5),2(6)]"],
[2,	"[0, 3]",	6,	23.0,	29.0,	"[0(0),4(1),5(2),0(3),1(4),1(5),6(6)]"],
[3,	"[5, 2]",	13,	17.0,	30.0,	"[6(0),5(1),2(2),6(3),1(4),4(5),1(6)]"],
[4,	"[6, 3]",	4,	12.0,	16.0,	"[4(0),4(1),0(2),2(3),0(4),4(5),5(6)]"],
[5,	"[1, 4]",	10,	12.0,	22.0,	"[3(0),6(1),4(2),2(3),1(4),6(5),2(6)]"],
[6,	"[0, 3]",	5,	13.0,	18.0,	"[1(0),6(1),2(2),3(3),0(4),5(5),3(6)]"],
[7,	"[0, 4]",	5,	19.0,	24.0,	"[4(0),5(1),3(2),6(3),0(4),1(5),4(6)]"],
]

# function to read the data
def read_inputs(fname):

    global OD_data, max_cities, max_days, number_of_aircrafts

    # Read Data from the file "OD pairs & Reassignemnt penalty"
    read_data =  pd.read_excel(fname,"OD pairs & Reassignment penalty",engine='openpyxl')
    read_data = read_data.dropna(axis='columns')
    read_data = np.array(read_data)
    # Get Unique Elements from 'read_data' using 'unique' Method.
    # unique : finds the unique elements of an array and returns these unique elements as a sorted array.
    origin_column_unique = np.unique(read_data[1:,0])
    day_column_unique = np.unique(read_data[1:,2])

    #store the max cities, days and aircrafts
    max_cities = len(origin_column_unique)
    max_days = len(day_column_unique)
    number_of_aircrafts = read_data.shape[1]-3

    #  cast 'read_data' to a specified type.
    OD_pairs = read_data[0: , 0:3].astype(int)
    OD_Reassign_costs = read_data[0:, 3:]
    # print(f"We have {max_cities} Cities, {max_days} Days and {number_of_aircrafts} Aircrafts \n")

def initiate():
    global graph
    graph = initiate_graph()
    # print(graph.print_adjList())


#Check the feasibility
def check_feasible(cycles, feasible):

    if feasible==0:
      return False
    count = 0
    for cycle in cycles:
      count+=(len(cycle))//max_days

    if count==number_of_aircrafts:
      return True


def optimization(graph):

    it = 0
    aircrafts_list = [i+1 for i in range(number_of_aircrafts)]
    obj = 0
    optimal_obj = 1000
    optimal_cycles = []
    

    costs = [None,None,None,None,None, None]
    
    sol_costs = []
    
    for i in range(number_of_aircrafts)
    	 sol_costs = TABLE_1[ i %8 ]
    
    #STEP-7 If iteration <= Max_Iteration keep running all steps
    while it < MAX_ITERATIONS:

      current_cycles = [[]]*number_of_aircrafts
      current_maints = [[]]*number_of_aircrafts

      weekly_maint_cost = [[]]*number_of_aircrafts
      weekly_re_cost = [[]]*number_of_aircrafts
      weeklyCost = [[]]*number_of_aircrafts

      feasible = 1
        
      #STEP-0
      #As given in STEP-0 Iteration += 1
      it += 1


      #As given in STEP-0 make a randomly ordered list of all aircrafts
      np.random.shuffle(aircrafts_list)

      #As given in STEP-0 copy/restore the original flight data
      nodes_copy = copy.deepcopy(graph.nodes)
      #And randomized it
      np.random.shuffle(nodes_copy)

      #STEP-1
      n = 0
      k = 0

        
      #STEP-2
      while n < number_of_aircrafts:
        #Pick the kth node in the randomized list of nodes
        node = nodes_copy[k]
        # print("nums", it, n, k, node)
        
        #Create all cycles starting from the k-th node
        all_cycles = graph.find_all_cycles1(node)
        # print(all_cycles)

        #STEP-3
        if len(all_cycles) == 0:
          feasible = 0
          k += 1 
          break
        else:
          if k>n:
             break
          feasible = 0
          min_current_cost  = 1000000

          for cycle in all_cycles:

            if len(cycle)%max_days == 1 and len(cycle)>max_days:

              num_aircrafts = len(cycle)//max_days
              

              if n+num_aircrafts<number_of_aircrafts:

                feasible = 1
                aircrafts = aircrafts_list[n:n + num_aircrafts]
                # print(aircrafts)
                opt_maint, maint_cost = Maintenance_Cost(cycle, aircrafts)
                reassig_cost = Reassignment_Cost(cycle, aircrafts)
                #total_cost = sum(maint_cost) + sum(reassig_cost)
                total_cost = sum(reassig_cost)							
                if total_cost < min_current_cost:

                  current_cost = total_cost
                  current_maint_cost = maint_cost
                  current_re_cost = reassig_cost
                  current_opt_cycle = copy.deepcopy(cycle)
                  current_opt_maint = opt_maint


          if feasible == 1:
            num_aircrafts = len(current_opt_cycle)//max_days
            #Assign the air-crafts to the cycle
            for index in range(num_aircrafts):
              aircraft = aircrafts_list[n-1+index]
              #weekly_maint_cost[aircraft] = current_maint_cost[index]
              #weekly_re_cost[aircraft] = current_re_cost[aircraft]
              #weeklyCost[aircraft] = 0 #current_maint_cost[index]+current_re_cost[aircraft]
              #current_cycles[aircraft] = current_opt_cycle
              #current_maints[aircraft] = current_opt_maint[index]
                

            #Set m = number of crafts needed for the cycle
            m = num_aircrafts

            #Remove the edges of the cycle from the current flight data
            for day in range(len(current_opt_cycle)-1):      
              graph.remove_edge(current_opt_cycle[day],current_opt_cycle[day+1])

            #STEP-4 (k += 1)(n += m)
            k+=1
            n+=m
            

            #STEP-5 if n >= number of crafts then break the loop                                              
            if  n >= number_of_aircrafts:
                # for aircraft in range(num_aircrafts):
                #    print(aircraft,  weekly_maint_cost[aircraft], weekly_re_cost[aircraft],
                #          weeklyCost[aircraft],current_cycles[aircraft],current_maints[aircraft] )
                # input()
                break

      #STEP-6 
      #If the current solution is better then the best solution so far
      #Store the current solution  
      if check_feasible(current_cycles, feasible):
        if sum(weeklyCost)<optimal_obj:
          optimal_obj = sum(weeklyCost)
          optimal_cycles = current_cycles
          optimal_maint = current_maints

          costs = [weekly_maint_cost, weekly_re_cost, weeklyCost]
          

    text = []
    for i,item in enumerate(sol_costs):
	    text.append([i,item[0],item[1], item[2],item[3] ,item[4]])
    text.append(["","", 0, 0, 0, "" ])

    df = pd.DataFrame(text, columns =[ 'Aircraft','Maintenance Days','Weekly Cost of Maintenance','Weekly Reassignment Cost','Total Cost',	'Cycle'])        
    
    book = load_workbook(EXCEL_FILE)
    writer = pd.ExcelWriter(EXCEL_FILE, engine = 'openpyxl')
    writer.book = book

    df.to_excel(writer, index=False, sheet_name = 'Results')
    writer.close()	
      

    return [optimal_obj, costs[0], costs[1], costs[2], optimal_cycles]



def main(graph):
            
  return optimization(graph)

input_Table1(EXCEL_FILE)
input_Table2(EXCEL_FILE)
read_inputs(EXCEL_FILE)
initiate()      
solution = main(graph)    
# print(solution)

