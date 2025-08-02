from pyomo.environ import *
from pyomo.opt import SolverFactory


DEBUG = False

# Inputs ---

#  Basic conditions check
# Airports = ["A", "B"]
# Aircrafts = [1, 2]
# Nbflight = 6
# Flights = list(range(1, Nbflight + 1))
# Days = list(range(1, 8))
# MA = sorted(["A", "B", "C"])  # Maintenance airports
# Flight Information
# Flight = [
#     {"flight": 1, "origin": "A", "destination": "B", "departureTime": 540, "arrivalTime": 660},
#     {"flight": 2, "origin": "B", "destination": "A", "departureTime": 690, "arrivalTime": 810},
#     {"flight": 3, "origin": "A", "destination": "B", "departureTime": 840, "arrivalTime": 960},
#     {"flight": 4, "origin": "B", "destination": "A", "departureTime": 570, "arrivalTime": 690},
#     {"flight": 5, "origin": "A", "destination": "B", "departureTime": 720, "arrivalTime": 840},
#     {"flight": 6, "origin": "B", "destination": "A", "departureTime": 870, "arrivalTime": 990}
# ]
#
# # Initial aircraft locations
# a0 = {1: "A", 2: "B"}

# Cost matrix
# cost = [
#      [6804, 6870],
#      [4536, 4580],
#      [7216, 7286],
#      [1133, 1144],
#      [6185, 6245],
#      [5678, 5700]
#     ]


Airports = ["A","B","C","D","E","F","H","G","K","I","J","N","R","Q","P","M","L","S"]
Nbflight = 103
Aircrafts = [0, 1, 2,  3, 4, 5, 6, 7, 8, 9]

DayShift = 24 # Consider shift as day with 24 hrs

Flights = list(range(1, Nbflight + 1))
Days = list(range(1, 8 * int(24/DayShift)))

MA = sorted(Airports)  # Consider Maintenance everywhere

# Flight Information
Flight = [
{'flight': 1, 'origin': 'D', 'destination': 'E', 'departureTime': 4855.0, 'arrivalTime': 5060.0},
{'flight': 2, 'origin': 'E', 'destination': 'F', 'departureTime': 5130.0, 'arrivalTime': 5240.0},
{'flight': 3, 'origin': 'G', 'destination': 'B', 'departureTime': 8550.0, 'arrivalTime': 8700.0},
{'flight': 4, 'origin': 'E', 'destination': 'D', 'departureTime': 9395.0, 'arrivalTime': 9650.0},
{'flight': 5, 'origin': 'D', 'destination': 'H', 'departureTime': 9690.0, 'arrivalTime': 9795.0},
{'flight': 6, 'origin': 'H', 'destination': 'D', 'departureTime': 9870.0, 'arrivalTime': 9990.0},
{'flight': 7, 'origin': 'B', 'destination': 'E', 'departureTime': 9175.0, 'arrivalTime': 9360.0},
{'flight': 8, 'origin': 'F', 'destination': 'B', 'departureTime': 5275.0, 'arrivalTime': 5425.0},
{'flight': 9, 'origin': 'B', 'destination': 'D', 'departureTime': 5455.0, 'arrivalTime': 5730.0},
{'flight': 10, 'origin': 'G', 'destination': 'I', 'departureTime': 7190.0, 'arrivalTime': 7300.0},
{'flight': 11, 'origin': 'I', 'destination': 'J', 'departureTime': 7745.0, 'arrivalTime': 7915.0},
{'flight': 12, 'origin': 'J', 'destination': 'I', 'departureTime': 7945.0, 'arrivalTime': 8110.0},
{'flight': 13, 'origin': 'I', 'destination': 'B', 'departureTime': 8140.0, 'arrivalTime': 8315.0},
{'flight': 14, 'origin': 'B', 'destination': 'G', 'departureTime': 8415.0, 'arrivalTime': 8520.0},
{'flight': 15, 'origin': 'B', 'destination': 'C', 'departureTime': 1405.0, 'arrivalTime': 1605.0},
{'flight': 16, 'origin': 'C', 'destination': 'D', 'departureTime': 4090.0, 'arrivalTime': 4295.0},
{'flight': 17, 'origin': 'C', 'destination': 'P', 'departureTime': 2060.0, 'arrivalTime': 2365.0},
{'flight': 18, 'origin': 'P', 'destination': 'N', 'departureTime': 2440.0, 'arrivalTime': 2490.0},
{'flight': 19, 'origin': 'N', 'destination': 'A', 'departureTime': 2560.0, 'arrivalTime': 2675.0},
{'flight': 20, 'origin': 'A', 'destination': 'K', 'departureTime': 2750.0, 'arrivalTime': 2860.0},
{'flight': 21, 'origin': 'K', 'destination': 'C', 'departureTime': 3490.0, 'arrivalTime': 3705.0},
{'flight': 22, 'origin': 'C', 'destination': 'R', 'departureTime': 3790.0, 'arrivalTime': 3895.0},
{'flight': 23, 'origin': 'R', 'destination': 'C', 'departureTime': 3925.0, 'arrivalTime': 4035.0},
{'flight': 24, 'origin': 'A', 'destination': 'D', 'departureTime': 810.0, 'arrivalTime': 1025.0},
{'flight': 25, 'origin': 'D', 'destination': 'B', 'departureTime': 1055.0, 'arrivalTime': 1350.0},
{'flight': 26, 'origin': 'D', 'destination': 'L', 'departureTime': 6410.0, 'arrivalTime': 6575.0},
{'flight': 27, 'origin': 'L', 'destination': 'K', 'departureTime': 6675.0, 'arrivalTime': 6800.0},
{'flight': 28, 'origin': 'K', 'destination': 'I', 'departureTime': 6870.0, 'arrivalTime': 6975.0},
{'flight': 29, 'origin': 'I', 'destination': 'G', 'departureTime': 7015.0, 'arrivalTime': 7160.0},
{'flight': 30, 'origin': 'J', 'destination': 'A', 'departureTime': 555.0, 'arrivalTime': 735.0},
{'flight': 31, 'origin': 'C', 'destination': 'G', 'departureTime': 2595.0, 'arrivalTime': 2870.0},
{'flight': 32, 'origin': 'B', 'destination': 'C', 'departureTime': 2365.0, 'arrivalTime': 2565.0},
{'flight': 33, 'origin': 'G', 'destination': 'I', 'departureTime': 4310.0, 'arrivalTime': 4420.0},
{'flight': 34, 'origin': 'I', 'destination': 'J', 'departureTime': 4865.0, 'arrivalTime': 5035.0},
{'flight': 35, 'origin': 'J', 'destination': 'I', 'departureTime': 5065.0, 'arrivalTime': 5230.0},
{'flight': 36, 'origin': 'I', 'destination': 'B', 'departureTime': 5260.0, 'arrivalTime': 5435.0},
{'flight': 37, 'origin': 'B', 'destination': 'G', 'departureTime': 5535.0, 'arrivalTime': 5640.0},
{'flight': 38, 'origin': 'B', 'destination': 'C', 'departureTime': 7950.0, 'arrivalTime': 8155.0},
{'flight': 39, 'origin': 'C', 'destination': 'B', 'departureTime': 8240.0, 'arrivalTime': 8450.0},
{'flight': 40, 'origin': 'B', 'destination': 'P', 'departureTime': 8530.0, 'arrivalTime': 8725.0},
{'flight': 41, 'origin': 'C', 'destination': 'B', 'departureTime': 9680.0, 'arrivalTime': 9890.0},
{'flight': 42, 'origin': 'A', 'destination': 'K', 'departureTime': 555.0, 'arrivalTime': 720.0},
{'flight': 43, 'origin': 'L', 'destination': 'C', 'departureTime': 940.0, 'arrivalTime': 1115.0},
{'flight': 44, 'origin': 'K', 'destination': 'L', 'departureTime': 800.0, 'arrivalTime': 910.0},
{'flight': 45, 'origin': 'Q', 'destination': 'B', 'departureTime': 1405.0, 'arrivalTime': 1650.0},
{'flight': 46, 'origin': 'C', 'destination': 'Q', 'departureTime': 1225.0, 'arrivalTime': 1350.0},
{'flight': 47, 'origin': 'C', 'destination': 'B', 'departureTime': 6400.0, 'arrivalTime': 6600.0},
{'flight': 48, 'origin': 'B', 'destination': 'K', 'departureTime': 6690.0, 'arrivalTime': 6860.0},
{'flight': 49, 'origin': 'K', 'destination': 'B', 'departureTime': 6980.0, 'arrivalTime': 7105.0},
{'flight': 50, 'origin': 'G', 'destination': 'C', 'departureTime': 5820.0, 'arrivalTime': 6050.0},
{'flight': 51, 'origin': 'P', 'destination': 'C', 'departureTime': 9345.0, 'arrivalTime': 9650.0},
{'flight': 52, 'origin': 'H', 'destination': 'C', 'departureTime': 1110.0, 'arrivalTime': 1400.0},
{'flight': 53, 'origin': 'C', 'destination': 'G', 'departureTime': 1430.0, 'arrivalTime': 1705.0},
{'flight': 54, 'origin': 'B', 'destination': 'Q', 'departureTime': 5420.0, 'arrivalTime': 5655.0},
{'flight': 55, 'origin': 'I', 'destination': 'H', 'departureTime': 750.0, 'arrivalTime': 1050.0},
{'flight': 56, 'origin': 'G', 'destination': 'B', 'departureTime': 4595.0, 'arrivalTime': 4710.0},
{'flight': 57, 'origin': 'H', 'destination': 'C', 'departureTime': 6870.0, 'arrivalTime': 7160.0},
{'flight': 58, 'origin': 'N', 'destination': 'B', 'departureTime': 9740.0, 'arrivalTime': 9945.0},
{'flight': 59, 'origin': 'M', 'destination': 'J', 'departureTime': 3995.0, 'arrivalTime': 4110.0},
{'flight': 60, 'origin': 'J', 'destination': 'F', 'departureTime': 4180.0, 'arrivalTime': 4295.0},
{'flight': 61, 'origin': 'D', 'destination': 'I', 'departureTime': 9255.0, 'arrivalTime': 9490.0},
{'flight': 62, 'origin': 'I', 'destination': 'N', 'departureTime': 9560.0, 'arrivalTime': 9670.0},
{'flight': 63, 'origin': 'B', 'destination': 'M', 'departureTime': 3515.0, 'arrivalTime': 3685.0},
{'flight': 64, 'origin': 'F', 'destination': 'B', 'departureTime': 5160.0, 'arrivalTime': 5270.0},
{'flight': 65, 'origin': 'B', 'destination': 'I', 'departureTime': 5350.0, 'arrivalTime': 5525.0},
{'flight': 66, 'origin': 'I', 'destination': 'K', 'departureTime': 5555.0, 'arrivalTime': 5660.0},
{'flight': 67, 'origin': 'K', 'destination': 'I', 'departureTime': 6375.0, 'arrivalTime': 6480.0},
{'flight': 68, 'origin': 'I', 'destination': 'H', 'departureTime': 6510.0, 'arrivalTime': 6810.0},
{'flight': 69, 'origin': 'I', 'destination': 'C', 'departureTime': 605.0, 'arrivalTime': 845.0},
{'flight': 70, 'origin': 'C', 'destination': 'I', 'departureTime': 930.0, 'arrivalTime': 1215.0},
{'flight': 71, 'origin': 'I', 'destination': 'P', 'departureTime': 1300.0, 'arrivalTime': 1405.0},
{'flight': 72, 'origin': 'P', 'destination': 'I', 'departureTime': 1530.0, 'arrivalTime': 1630.0},
{'flight': 73, 'origin': 'I', 'destination': 'M', 'departureTime': 2065.0, 'arrivalTime': 2245.0},
{'flight': 74, 'origin': 'M', 'destination': 'B', 'departureTime': 2345.0, 'arrivalTime': 2475.0},
{'flight': 75, 'origin': 'B', 'destination': 'E', 'departureTime': 2560.0, 'arrivalTime': 2745.0},
{'flight': 76, 'origin': 'E', 'destination': 'B', 'departureTime': 2780.0, 'arrivalTime': 2965.0},
{'flight': 77, 'origin': 'C', 'destination': 'L', 'departureTime': 7855.0, 'arrivalTime': 8045.0},
{'flight': 78, 'origin': 'L', 'destination': 'D', 'departureTime': 8825.0, 'arrivalTime': 8935.0},
{'flight': 79, 'origin': 'I', 'destination': 'N', 'departureTime': 9560.0, 'arrivalTime': 9670.0},
{'flight': 80, 'origin': 'C', 'destination': 'B', 'departureTime': 535.0, 'arrivalTime': 745.0},
{'flight': 81, 'origin': 'C', 'destination': 'D', 'departureTime': 8410.0, 'arrivalTime': 8615.0},
{'flight': 82, 'origin': 'N', 'destination': 'B', 'departureTime': 9740.0, 'arrivalTime': 9945.0},
{'flight': 83, 'origin': 'B', 'destination': 'C', 'departureTime': 830.0, 'arrivalTime': 1040.0},
{'flight': 84, 'origin': 'C', 'destination': 'Q', 'departureTime': 1110.0, 'arrivalTime': 1230.0},
{'flight': 85, 'origin': 'Q', 'destination': 'S', 'departureTime': 1300.0, 'arrivalTime': 1400.0},
{'flight': 86, 'origin': 'S', 'destination': 'C', 'departureTime': 1430.0, 'arrivalTime': 1545.0},
{'flight': 87, 'origin': 'D', 'destination': 'I', 'departureTime': 9255.0, 'arrivalTime': 9490.0},
{'flight': 88, 'origin': 'B', 'destination': 'Q', 'departureTime': 6860.0, 'arrivalTime': 7095.0},
{'flight': 89, 'origin': 'I', 'destination': 'J', 'departureTime': 3830.0, 'arrivalTime': 3995.0},
{'flight': 90, 'origin': 'J', 'destination': 'C', 'departureTime': 4025.0, 'arrivalTime': 4230.0},
{'flight': 91, 'origin': 'C', 'destination': 'R', 'departureTime': 4945.0, 'arrivalTime': 5050.0},
{'flight': 92, 'origin': 'R', 'destination': 'B', 'departureTime': 5120.0, 'arrivalTime': 5345.0},
{'flight': 93, 'origin': 'C', 'destination': 'I', 'departureTime': 3505.0, 'arrivalTime': 3795.0},
{'flight': 94, 'origin': 'B', 'destination': 'E', 'departureTime': 5440.0, 'arrivalTime': 5625.0},
{'flight': 95, 'origin': 'B', 'destination': 'M', 'departureTime': 6395.0, 'arrivalTime': 6565.0},
{'flight': 96, 'origin': 'M', 'destination': 'B', 'departureTime': 6665.0, 'arrivalTime': 6795.0},
{'flight': 97, 'origin': 'C', 'destination': 'I', 'departureTime': 2065.0, 'arrivalTime': 2355.0},
{'flight': 98, 'origin': 'I', 'destination': 'B', 'departureTime': 2480.0, 'arrivalTime': 2660.0},
{'flight': 99, 'origin': 'B', 'destination': 'C', 'departureTime': 2695.0, 'arrivalTime': 2945.0},
{'flight': 100, 'origin': 'Q', 'destination': 'C', 'departureTime': 7185.0, 'arrivalTime': 7360.0},
{'flight': 101, 'origin': 'C', 'destination': 'B', 'departureTime': 7840.0, 'arrivalTime': 8040.0},
{'flight': 102, 'origin': 'B', 'destination': 'C', 'departureTime': 8125.0, 'arrivalTime': 8325.0},
{'flight': 103, 'origin': 'E', 'destination': 'B', 'departureTime': 5660.0, 'arrivalTime': 5845.0}
]

if DEBUG:
    for f in Flight:
        print(f)

# Derived FlightData
FlightData = {
    f["flight"]: {
        "origin": f["origin"],
        "destination": f["destination"],
        "departureTime": f["departureTime"],
        "arrivalTime": f["arrivalTime"],
        "duration": f["arrivalTime"] - f["departureTime"],
        "day_departure": int(f["departureTime"] // (DayShift * 60)) + 1,
        "day_arrival": int(f["arrivalTime"] // (DayShift * 60)) + 1,
    } for f in Flight
}

if DEBUG or True:
    for i,it in FlightData.items():
        print(i, it)

cost =[
[6804.0,6870.0,6771.0,6804.0,6870.0,6771.0,6804.0,6870.0,6771.0,6804.0,],
[4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,],
[7216.0,7286.0,7181.0,7216.0,7286.0,7181.0,7216.0,7286.0,7181.0,7216.0,],
[11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,],
[6185.0,6245.0,6155.0,6185.0,6245.0,6155.0,6185.0,6245.0,6155.0,6185.0,],
[5773.0,5829.0,5745.0,5773.0,5829.0,5745.0,5773.0,5829.0,5745.0,5773.0,],
[4330.0,4372.0,4309.0,4330.0,4372.0,4309.0,4330.0,4372.0,4309.0,4330.0,],
[5979.0,6037.0,5950.0,5979.0,6037.0,5950.0,5979.0,6037.0,5950.0,5979.0,],
[8041.0,8119.0,8002.0,8041.0,8119.0,8002.0,8041.0,8119.0,8002.0,8041.0,],
[7628.0,7702.0,7591.0,7628.0,7702.0,7591.0,7628.0,7702.0,7591.0,7628.0,],
[4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,],
[9071.0,9159.0,9027.0,9071.0,9159.0,9027.0,9071.0,9159.0,9027.0,9071.0,],
[9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,],
[20411.0,20609.0,20312.0,20411.0,20609.0,20312.0,20411.0,20609.0,20312.0,20411.0,],
[4330.0,4372.0,4309.0,4330.0,4372.0,4309.0,4330.0,4372.0,4309.0,4330.0,],
[4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,],
[6597.0,6661.0,6565.0,6597.0,6661.0,6565.0,6597.0,6661.0,6565.0,6597.0,],
[11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,],
[12164.0,12282.0,12105.0,12164.0,12282.0,12105.0,12164.0,12282.0,12105.0,12164.0,],
[8453.0,8535.0,8412.0,8453.0,8535.0,8412.0,8453.0,8535.0,8412.0,8453.0,],
[9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,],
[9690.0,9784.0,9643.0,9690.0,9784.0,9643.0,9690.0,9784.0,9643.0,9690.0,],
[7216.0,7286.0,7181.0,7216.0,7286.0,7181.0,7216.0,7286.0,7181.0,7216.0,],
[8865.0,8951.0,8822.0,8865.0,8951.0,8822.0,8865.0,8951.0,8822.0,8865.0,],
[3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,],
[3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,],
[11958.0,12074.0,11900.0,11958.0,12074.0,11900.0,11958.0,12074.0,11900.0,11958.0,],
[6597.0,6661.0,6565.0,6597.0,6661.0,6565.0,6597.0,6661.0,6565.0,6597.0,],
[11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,],
[12164.0,12282.0,12105.0,12164.0,12282.0,12105.0,12164.0,12282.0,12105.0,12164.0,],
[8247.0,8327.0,8207.0,8247.0,8327.0,8207.0,8247.0,8327.0,8207.0,8247.0,],
[9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,],
[24122.0,24356.0,24005.0,24122.0,24356.0,24005.0,24122.0,24356.0,24005.0,24122.0,],
[8453.0,8535.0,8412.0,8453.0,8535.0,8412.0,8453.0,8535.0,8412.0,8453.0,],
[8247.0,8327.0,8207.0,8247.0,8327.0,8207.0,8247.0,8327.0,8207.0,8247.0,],
[8865.0,8951.0,8822.0,8865.0,8951.0,8822.0,8865.0,8951.0,8822.0,8865.0,],
[3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,],
[3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,],
[3711.0,3747.0,3693.0,3711.0,3747.0,3693.0,3711.0,3747.0,3693.0,3711.0,],
[3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,],
[6804.0,6870.0,6771.0,6804.0,6870.0,6771.0,6804.0,6870.0,6771.0,6804.0,],
[4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,],
[7216.0,7286.0,7181.0,7216.0,7286.0,7181.0,7216.0,7286.0,7181.0,7216.0,],
[11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,],
[6185.0,6245.0,6155.0,6185.0,6245.0,6155.0,6185.0,6245.0,6155.0,6185.0,],
[5773.0,5829.0,5745.0,5773.0,5829.0,5745.0,5773.0,5829.0,5745.0,5773.0,],
[4330.0,4372.0,4309.0,4330.0,4372.0,4309.0,4330.0,4372.0,4309.0,4330.0,],
[5979.0,6037.0,5950.0,5979.0,6037.0,5950.0,5979.0,6037.0,5950.0,5979.0,],
[8041.0,8119.0,8002.0,8041.0,8119.0,8002.0,8041.0,8119.0,8002.0,8041.0,],
[7628.0,7702.0,7591.0,7628.0,7702.0,7591.0,7628.0,7702.0,7591.0,7628.0,],
[4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,],
[9071.0,9159.0,9027.0,9071.0,9159.0,9027.0,9071.0,9159.0,9027.0,9071.0,],
[9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,],
[20411.0,20609.0,20312.0,20411.0,20609.0,20312.0,20411.0,20609.0,20312.0,20411.0,],
[4330.0,4372.0,4309.0,4330.0,4372.0,4309.0,4330.0,4372.0,4309.0,4330.0,],
[4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,],
[6597.0,6661.0,6565.0,6597.0,6661.0,6565.0,6597.0,6661.0,6565.0,6597.0,],
[11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,],
[12164.0,12282.0,12105.0,12164.0,12282.0,12105.0,12164.0,12282.0,12105.0,12164.0,],
[8453.0,8535.0,8412.0,8453.0,8535.0,8412.0,8453.0,8535.0,8412.0,8453.0,],
[9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,],
[9690.0,9784.0,9643.0,9690.0,9784.0,9643.0,9690.0,9784.0,9643.0,9690.0,],
[7216.0,7286.0,7181.0,7216.0,7286.0,7181.0,7216.0,7286.0,7181.0,7216.0,],
[8865.0,8951.0,8822.0,8865.0,8951.0,8822.0,8865.0,8951.0,8822.0,8865.0,],
[3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,],
[3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,],
[11958.0,12074.0,11900.0,11958.0,12074.0,11900.0,11958.0,12074.0,11900.0,11958.0,],
[6597.0,6661.0,6565.0,6597.0,6661.0,6565.0,6597.0,6661.0,6565.0,6597.0,],
[11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,],
[12164.0,12282.0,12105.0,12164.0,12282.0,12105.0,12164.0,12282.0,12105.0,12164.0,],
[8247.0,8327.0,8207.0,8247.0,8327.0,8207.0,8247.0,8327.0,8207.0,8247.0,],
[9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,],
[24122.0,24356.0,24005.0,24122.0,24356.0,24005.0,24122.0,24356.0,24005.0,24122.0,],
[8453.0,8535.0,8412.0,8453.0,8535.0,8412.0,8453.0,8535.0,8412.0,8453.0,],
[8247.0,8327.0,8207.0,8247.0,8327.0,8207.0,8247.0,8327.0,8207.0,8247.0,],
[8865.0,8951.0,8822.0,8865.0,8951.0,8822.0,8865.0,8951.0,8822.0,8865.0,],
[3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,],
[3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,],
[3711.0,3747.0,3693.0,3711.0,3747.0,3693.0,3711.0,3747.0,3693.0,3711.0,],
[3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,3955.0,3898.0,3917.0,],
[6804.0,6870.0,6771.0,6804.0,6870.0,6771.0,6804.0,6870.0,6771.0,6804.0,],
[4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,],
[7216.0,7286.0,7181.0,7216.0,7286.0,7181.0,7216.0,7286.0,7181.0,7216.0,],
[11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,],
[6185.0,6245.0,6155.0,6185.0,6245.0,6155.0,6185.0,6245.0,6155.0,6185.0,],
[5773.0,5829.0,5745.0,5773.0,5829.0,5745.0,5773.0,5829.0,5745.0,5773.0,],
[4330.0,4372.0,4309.0,4330.0,4372.0,4309.0,4330.0,4372.0,4309.0,4330.0,],
[5979.0,6037.0,5950.0,5979.0,6037.0,5950.0,5979.0,6037.0,5950.0,5979.0,],
[8041.0,8119.0,8002.0,8041.0,8119.0,8002.0,8041.0,8119.0,8002.0,8041.0,],
[7628.0,7702.0,7591.0,7628.0,7702.0,7591.0,7628.0,7702.0,7591.0,7628.0,],
[4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,],
[9071.0,9159.0,9027.0,9071.0,9159.0,9027.0,9071.0,9159.0,9027.0,9071.0,],
[9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,],
[20411.0,20609.0,20312.0,20411.0,20609.0,20312.0,20411.0,20609.0,20312.0,20411.0,],
[4330.0,4372.0,4309.0,4330.0,4372.0,4309.0,4330.0,4372.0,4309.0,4330.0,],
[4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,4580.0,4514.0,4536.0,],
[6597.0,6661.0,6565.0,6597.0,6661.0,6565.0,6597.0,6661.0,6565.0,6597.0,],
[11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,11449.0,11284.0,11339.0,],
[12164.0,12282.0,12105.0,12164.0,12282.0,12105.0,12164.0,12282.0,12105.0,12164.0,],
[8453.0,8535.0,8412.0,8453.0,8535.0,8412.0,8453.0,8535.0,8412.0,8453.0,],
[9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,9368.0,9233.0,9278.0,],
[9690.0,9784.0,9643.0,9690.0,9784.0,9643.0,9690.0,9784.0,9643.0,9690.0,],
[7216.0,7286.0,7181.0,7216.0,7286.0,7181.0,7216.0,7286.0,7181.0,7216.0,],
]

AircraftInit ={0: 'I', 1: 'J', 2: 'K', 3: 'B', 4: 'J', 5: 'A', 6: 'D', 7: 'I', 8: 'I', 9: 'C'}

Acheck ={0: 390.0, 1: 20.0, 2: 20.0, 3: 20.0, 4: 20.0, 5: 20.0, 6: 20.0, 7: 20.0, 8: 20.0, 9: 20.0}
Bcheck = {0: 20.0, 1: 594.0, 2: 20.0, 3: 20.0, 4: 20.0, 5: 20.0, 6: 20.0, 7: 20.0, 8: 20.0, 9: 20.0}
Ccheck = {0: 20.0, 1: 20.0, 2: 538.0, 3: 20.0, 4: 20.0, 5: 20.0, 6: 20.0, 7: 20.0, 8: 20.0, 9: 20.0}
Dcheck = {0: 20.0, 1: 20.0, 2: 20.0, 3: 1823.0, 4: 20.0, 5: 20.0, 6: 20.0, 7: 20.0, 8: 20.0, 9: 20.0}

Acheck_days ={0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}
Bcheck_days = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}
Ccheck_days = {0: 20.0, 1: 20.0, 2: 538.0, 3: 20.0, 4: 20.0, 5: 20.0, 6: 20.0, 7: 20.0, 8: 20.0, 9: 20.0}
Dcheck_days = {0: 20.0, 1: 20.0, 2: 20.0, 3: 1823.0, 4: 20.0, 5: 20.0, 6: 20.0, 7: 20.0, 8: 20.0, 9: 20.0}

Acheck ={0: 390.0, 1: 360.0, 2: 350.0, 3: 380.0, 4: 395.0, 5: 340.0, 6: 380.0, 7: 385.0, 8: 375.0, 9: 390.0}
Bcheck = {0: 590.0, 1: 594.0, 2: 580.0, 3: 570.0, 4: 575.0, 5: 585.0, 6: 591.0, 7: 595.0, 8: 500.0, 9: 520.0}

# Tmax = 8 * 60  # in minutes
# nu = 15
# dmax = 3

Mbig = 9999999

min_turn = 30  # in minutes


# Maintenance thresholds
A_check_hours = 400.0
B_check_hours = 600.0
C_check_hours = 540 * 24
D_check_hours = 1825 * 24

# Maintenance thresholds in days
A_check_days = int((A_check_hours+DayShift) / DayShift)
B_check_days = int((B_check_hours+DayShift) / DayShift)
C_check_days = 540
D_check_days = 1825


# Maintenance durations
A_check_duration = 8 * 60
B_check_duration = 16 * 60
C_check_duration = 5 * 24 * 60
D_check_duration = 10 * 24 * 60

# Maintenance durations for days
A_check_duration_days = 0
B_check_duration_days = 0
C_check_duration_days = 5
D_check_duration_days = 10


# Generalized lists
NUM_Checks = 4
# All_Check_List = list(range(1, NUM_Checks+1))
All_Check_List = ["Acheck","Bcheck", "Ccheck", "Dcheck"]
All_Checks = {
    All_Check_List[0]: Acheck,
    All_Check_List[1]: Bcheck,
    All_Check_List[2]: Ccheck,
    All_Check_List[3]: Dcheck
}


All_Check_days = {
    All_Check_List[0]: 50,
    All_Check_List[1]: 100,
    All_Check_List[2]: C_check_days,
    All_Check_List[3]: D_check_days
}

Premature_Check_penalty = {
    All_Check_List[0]: {0:0,1:10,2:20,3:40,4:60},
    All_Check_List[1]: {0:0,1:10,2:20,3:40,4:60},
    All_Check_List[2]: {0:0,1:10,2:20,3:40,4:60},
    All_Check_List[3]: {0:0,1:10,2:20,3:40,4:60}
}

All_Checks_Done_Days = {
    All_Check_List[0]: Acheck_days,
    All_Check_List[1]: Bcheck_days,
    All_Check_List[2]: Ccheck_days,
    All_Check_List[3]: Dcheck_days
}


All_Check_Done_hours = {
    All_Check_List[0]: A_check_hours,
    All_Check_List[1]: B_check_hours,
    All_Check_List[2]: C_check_hours,
    All_Check_List[3]: D_check_hours
}

All_Check_durations ={
    All_Check_List[0]: A_check_duration,
    All_Check_List[1]: B_check_duration,
    All_Check_List[2]: C_check_duration,
    All_Check_List[3]: D_check_duration
}

All_Check_durations_days ={
    All_Check_List[0]: A_check_duration_days,
    All_Check_List[1]: B_check_duration_days,
    All_Check_List[2]: C_check_duration_days,
    All_Check_List[3]: D_check_duration_days
}

# All_Check_List = ["Acheck"]

mc = {(i, j, d): 100 for i in Flights for j in Aircrafts for d in Days}  # dummy maintenance cost

# Maintenance capacity
mcap = {(m, d): 2 for m in MA for d in Days}  # dummy capacity

# Helper functions
F_m = {m: [i for i in Flights if FlightData[i]["destination"] == m] for m in MA}  # The set of flights which departs from airport m

F_arr_k = {k: [i for i in Flights if FlightData[i]["destination"] == k] for k in sorted(Airports)}  # The set of flights which land in airport k
F_dep_k = {k: [i for i in Flights if FlightData[i]["origin"] == k] for k in sorted(Airports)}  # The set of flights which departs from airport k

# The set of flights which land in airport k before time t
F_arr_t = lambda k, t, delta: [i for i in F_arr_k[k] if FlightData[i]["arrivalTime"] <= t - delta]
# The set of flights which land in airport k before time t
F_dep_t = lambda k, t: [i for i in F_dep_k[k] if FlightData[i]["departureTime"] < t]
# The set of flights which land in airport k after t and before time t1
F_dep_t_t1 = lambda k, t, t1: [i for i in F_dep_k[k] if FlightData[i]["departureTime"] > t and FlightData[i]["departureTime"] <= t1]

# The set of flights for a given day
F_d = {d: [i for i in Flights if FlightData[i]["day_departure"] == d] for d in Days}
# The set of flights for a given day interval
F_d_next = lambda d1, d2: [i for i in Flights if d1 < FlightData[i]["day_departure"] <= d2]
# The set of flights for a given day when departureTime greater than arrivalTime of given flight
F_d_i = lambda d, i: [i2 for i2 in Flights if FlightData[i]["day_departure"] == d and FlightData[i2]["departureTime"] > FlightData[i]["arrivalTime"]]


# Define model
model = ConcreteModel()

# Define indices
model.F = Set(initialize=Flights)
model.P = Set(initialize=sorted(Aircrafts))
model.A = Set(initialize=sorted(Airports))
# model.A = Set(initialize=list(set(f['origin'] for f in FlightData.values()).union(set(f['destination'] for f in FlightData.values()))))
# print(model.A)

model.D = Set(initialize=sorted(Days))
model.MA = Set(initialize=sorted(MA))
model.C = Set(initialize=sorted(All_Check_List))

# print([j for j in model.P])

# Define variables
model.x = Var(model.F, model.P, domain=Binary)
model.z = Var(model.F, model.P, model.D, model.C, domain=Binary)
model.y = Var(model.P, model.D, model.C, domain=Binary)
model.mega_check = Var(model.P, model.D, model.C, domain=Binary)

# Define objective (7)
model.obj = Objective(
    expr=sum(cost[i-1][j-1] * model.x[i, j] for i in model.F for j in model.P) +
         sum((mc[i, j, d] + Premature_Check_penalty[check][(All_Check_days[check] - d)%5]) * model.z[i, j, d, check]
             for m in model.MA for i in F_m[m] for j in model.P for d in model.D for check in model.C)
    ,
    sense=minimize
)

# Constraint C1  (1)
model.c1 = ConstraintList()
for i in model.F:
    model.c1.add(sum(model.x[i, j] for j in model.P) == 1)

# Replacing c23 with corrected equipment_turn_constraints
turn_time = min_turn
flight_data = FlightData
flight_arr = {k: [i for i in model.F if FlightData[i]['destination'] == k] for k in model.A}

# Constraints (2)-(3)
model.equipment_turn_constraints = ConstraintList()
for j in model.P:
    for k in model.A:
        for i in F_dep_k[k]:
            t_dep = flight_data[i]['departureTime']
            lhs_geq = sum(model.x[i1, j] for i1 in F_arr_t(k, t_dep, turn_time))
            lhs_lt = sum(model.x[i1, j] for i1 in F_dep_t(k, t_dep))

            #
            if DEBUG:
                print("ijk", i, j, k, end=":")
                print(t_dep, end="\t")
                print(F_arr_t(k, t_dep, turn_time), lhs_geq, end="\t")
                print(F_dep_t(k, t_dep), lhs_lt)

            if k != AircraftInit[j]:
                model.equipment_turn_constraints.add(lhs_geq - lhs_lt >= model.x[i, j])
            else:
                model.equipment_turn_constraints.add(lhs_geq - lhs_lt >= model.x[i, j] - 1)


# Constraint (8)
# Maintenance blocks flights
model.maint_last = ConstraintList()
for check in model.C:
    for i in model.F:
        for j in model.P:
            for d in model.D:
                for i2 in F_d_i(d, i):
                    model.maint_last.add(model.z[i, j, d, check] + model.x[i2, j] <= 1)

# Constraint (9)
# Activation for flights: we have to fly for check
model.maint_assignment = ConstraintList()
for check in model.C:
    for i in model.F:
        for j in model.P:
            for d in model.D:
                model.maint_assignment.add(model.x[i, j] >= model.z[i, j, d, check])

# Constraint (10)
# Capacity limits for maintenances
model.maint_capacity = ConstraintList()
for check in model.C:
    for d in model.D:
        for m in model.MA:
            relevant_flights = F_m.get(m, [])
            if relevant_flights:
                model.maint_capacity.add(
                    sum(model.z[i, j, d, check] for i in relevant_flights for j in model.P) <= mcap[m, d]
                )

# Constraint (11)
# Activation for maintenances checks
model.maint_link = ConstraintList()
for check in model.C:
    for d in model.D:
        #for m in model.MA:
        for j in model.P:
            # print(j, d, m, F_m[m])
            model.maint_link.add(sum(model.z[i, j, d, check] for i in Flights if FlightData[i]["destination"] in MA) == model.y[j, d, check])


# model.maint_spacing0 = ConstraintList()
# print(Days)
#
# Acheck_start_days = {}
# for plane, check_prev in Acheck.items():
#     Acheck_start_days[plane] = int((A_check_hours - check_prev)/24)
#     print(plane, Acheck_start_days[plane])

# for j in model.P:
#     print("j is", j, Days[0: Acheck_start_days[j]+1])
#     model.maint_spacing0.add(sum(model.y[j, r] for r in Days[0: Acheck_start_days[j]+1]) >= 1)


model.maint_hierarchy = ConstraintList()

CHECK_HIERARCHY ={
    "Acheck": ["Acheck", "Bcheck", "Ccheck", "Dcheck"],
    "Bcheck": ["Bcheck", "Ccheck", "Dcheck"],
    "Ccheck": ["Ccheck", "Dcheck"],
    "Dcheck": ["Dcheck"]
}

for j in model.P:
    for d in model.D:
        for c in model.C:
            model.maint_hierarchy.add(model.mega_check[j, d, c] <=
                                   sum(model.y[j, d, check] for check in CHECK_HIERARCHY[c]))
            model.maint_hierarchy.add(len(CHECK_HIERARCHY) *  model.mega_check[j, d, c] >=
                                  sum(model.y[j, d, check] for check in CHECK_HIERARCHY[c]))


# Constraint (12)
# We have checks in All_Check_days interval
model.maint_spacing = ConstraintList()
for check in All_Check_List:
    for j in model.P:
        # print("j=",j, All_Check_days[check], len(Days) -1)
        for start in range(0, len(Days)- All_Check_days[check]-1):
            # print("checks", start, min(start + All_Check_days[check], len(Days)-1), Days[start:start + All_Check_days[check]])
            model.maint_spacing.add(sum(model.mega_check[j, r, check] for r in Days[start:start + All_Check_days[check]]) >= 1)

# Constraint (12 and 14 for C-D checks) we check regarding previous unchecked days
# We need checks regarding our check days remained
model.maint_spacing2 = ConstraintList()
for check in All_Check_List:
    for j in model.P:
        days_without_checks = int(All_Check_days[check] - All_Checks_Done_Days[check][j])
        if days_without_checks >= len(model.D):
            continue
        if DEBUG:
            print("days check", days_without_checks)
        model.maint_spacing2.add(sum(model.mega_check[j, r, check] for r in Days[:days_without_checks]) >= 1)


# Constraint (13)
# Planes could not fly without checks for All_Check_Done_hours
model.maint_cumulative = ConstraintList()
for check in All_Check_List:
    for j in model.P:
        for start in range(len(Days) - 1):
            for end in range(start + 2, min(start + All_Check_days[check], len(Days))):
                d = Days[start]
                d_ = Days[end]
                t_sum = sum(FlightData[i]['duration'] * model.x[i, j] for i in F_d_next(d+1, d_))
                y_sum = sum(model.mega_check[j, r, check] for r in Days[start+1:end])
                # This is paper constraint (13) - however, it seems to be Wrong???!!!
                model.maint_cumulative.add(t_sum <= All_Check_Done_hours[check]*60 + Mbig * y_sum +
                                           Mbig*(2 - model.mega_check[j, d, check] - model.mega_check[j, d_, check]) )

                # My corrected version:: either y_sum or y[j,start] and y[j,end]
                model.maint_cumulative.add(t_sum <= All_Check_Done_hours[check] * 60 + Mbig * y_sum + Mbig * model.mega_check[j, d, check])
                model.maint_cumulative.add(t_sum <= All_Check_Done_hours[check] * 60 + Mbig * y_sum + Mbig * model.mega_check[j, d_, check])

# Constraint 13-1
# Constraint for counting previous flight hours before start - my version
# Planes could not fly without checks for All_Check_Done_hours - Previous flight hours without checks
model.maint_cumulative_start = ConstraintList()
for check in All_Check_List:
    for j in model.P:
        for end in range(1, min(len(Days)-1, All_Check_days[check])):
            d = Days[0]
            d_ = Days[end]
            t_sum = sum(FlightData[i]['duration'] * model.x[i, j] for i in F_d_next(0, d_))
            y_sum = sum(model.mega_check[j, r, check] for r in Days[:end])
            if DEBUG:
                print("Plane ", j, "unchecked hrs", All_Check_Done_hours[check], All_Checks[check][j], "start/end days",d, d_)
            # Flight minutes is small or we have either y_sum or y[j,end]
            model.maint_cumulative_start.add(t_sum <= (All_Check_Done_hours[check] - All_Checks[check][j]) * 60 +
                                             Mbig * y_sum +
                                             Mbig * model.mega_check[j, d_, check])

# Constraint 14??
# Constraint - my version of no double check
# We can have only one check simultenuosly per one day
model.maint_block_checks = ConstraintList()
for j in model.P:
    for d in model.D:
        model.maint_block_checks.add(sum(model.y[j, d, check] for check in All_Check_List) <= 1)


# Constraint 14-1
# Constraint - my version of check length
# C-D checks last for All_Check_durations_days
model.maint_checks_days = ConstraintList()
for j in model.P:
    for check in All_Check_List:
        if All_Check_durations_days[check] == 0:
            continue

        for d in range(len(Days)):
            K = min(d + All_Check_durations_days[check], len(Days))
            if DEBUG:
                print([Days[x] for x in range(d + 1, K)])
            if d==0:
                model.maint_checks_days.add(
                    sum(model.mega_check[j, Days[d1], check] for d1 in range(1, K)) +
                    Mbig * (1 - model.mega_check[j, Days[0], check]) >= K-1)
                continue
            if d>=K:
                 continue

            model.maint_checks_days.add(sum(model.mega_check[j, Days[d1], check] for d1 in range(d + 1, K)) +
                                        Mbig * model.mega_check[j, Days[d - 1], check] +
                                        Mbig * (1 - model.mega_check[j, Days[d], check]) >= K - d - 1)

# Version of CPLEX sent - not sure they are correct
# Constraint no flight during checks
# for j in model.P:
#     for d in model.D:
#         for k in model.A:
#             for i in F_dep_k[k]:
#                 if flight_data[i]['day'] !=d:
#                     continue
#
#                 t_dep = flight_data[i]['departureTime']
#
#                 for check in All_Check_List:
#                     lhs_lt = sum(model.x[i1, j] for i1 in F_dep_t_t1(k,t_dep, t_dep + All_Check_durations[check]))
#                     model.maint_block_flights.add(lhs_lt <= Mbig * model.y[j, d, check])

# for j in model.P:
#     for d in model.D:
#         for i in model.F:
#             t_dep = flight_data[i]['departureTime']
#             if flight_data[i]['day'] < d:
#                 continue
#
#             for check in model.C:
#                 if t_dep < d * 24 * 60 + All_Check_durations[check]:
#                     print(j,i,d,check)
#                     model.maint_block_flights.add(model.x[i, j] + model.y[j, d, check] <=1)

# Constraint (15)
# Constraint no flight during checks - my version\
# For checks A-B hours
model.maint_block_flights = ConstraintList()
for check in model.C:
    for i in model.F:
        t_arr = flight_data[i]['arrivalTime']
        day = flight_data[i]['day_arrival']
        airport = flight_data[i]['destination']
        if airport not in MA:
            continue

        for j in model.P:
            if DEBUG or check=="Bcheck" and j==0:
                print("figths", i, "plane", j, "port", airport, "day", day, "t:", t_arr, t_arr + All_Check_durations[check],
                      F_dep_t_t1(airport, t_arr, t_arr + All_Check_durations[check]))
            for i2 in F_dep_t_t1(airport, t_arr, t_arr + All_Check_durations[check]):
                if DEBUG:
                    print(i,j,day,check,i2,j)
                for d in range(day, min(day + 2, Days[-1])):
                    model.maint_block_flights.add(model.z[i, j, d, check] + model.x[i2, j] <= 1)
                # if day == 1 and All_Check_durations_days[check] > 1:
                #     model.maint_block_flights.add(model.y[j, day, check] + model.x[i2, j] <= 1)

    t_arr = 0
    day = Days[0]

    for airport in AircraftInit.values():

        if airport not in MA:
            continue

        for j in model.P:
            if DEBUG or check == "Bcheck" and j == 0:
                print("figths", i, "plane", j, "port", airport, "day", day, "t:", t_arr, t_arr + All_Check_durations[check],
                      F_dep_t_t1(airport, t_arr, t_arr + All_Check_durations[check]))
            for i2 in F_dep_t_t1(airport, 0, All_Check_durations[check]):
                if DEBUG:
                    print(i, j, day, check, i2, j)
                for d in range(day, min(day + 1, Days[-1])):
                    model.maint_block_flights.add(model.mega_check[j, d, check] + model.x[i2, j] <= 1)

# model.maint_block_flights.add(model.z[, j, d, check] + model.x[i2, j] <= 1)

# Constraint (15-1)
# Constraint no flight during checks - my version
# For checks C-D days
model.maint_block_flights_days = ConstraintList()
for check in model.C:
    if All_Check_durations_days[check] <= 1:
        continue
    for i in model.F:
        t_arr = flight_data[i]['arrivalTime']
        day = flight_data[i]['day_arrival']
        if DEBUG:
            print("day", day)
        # day = Days.index(day)
        # print(day)
        if day == 1:
            for j in model.P:
               model.maint_block_flights_days.add(
                    model.mega_check[j, day, check] + model.x[i, j] <= 1)
            continue
        airport = flight_data[i]['origin']
        # if airport not in MA:
        #     continue

        for j in model.P:
            if DEBUG:
                print("Check fligths", i, "plane", j, "port", airport, "day", day, "t:", t_arr, t_arr +
                      All_Check_durations[check], F_dep_t_t1(airport, t_arr, t_arr + All_Check_durations[check]))

            model.maint_block_flights_days.add(model.mega_check[j, day - 1, check] + model.mega_check[j, day, check] + model.x[i, j] <= 2)



# Solve
solver = SolverFactory('cplex')  # Or 'cbc', 'glpk', etc.
solver.solve(model)

print("\nAssignment Results:")
for i in model.F:
    for j in model.P:
        if value(model.x[i, j]) > 0.5:
            print(f"Flight {i} assigned to Plane {j}")

        for d in model.D:
            for c in model.C:
                if value(model.z[i, j, d, c]) > 0.5:
                    print(f"In this flight Plane {j} goes to check {c[0]} on day {d}")
                # (value(model.y[j, d, c]),end=",")
            # print("\t",end="")

print(f"Total Cost: {value(model.obj)}")



print("\nAircraft Assignment and Maintenance Report:")

for j in model.P:
    events = []
    events2 = []
    # Gather all assigned flights for this aircraft (use departure time for sorting)
    for i in model.F:
        if value(model.x[i, j]) > 0.5:
            events.append((FlightData[i]['departureTime'],
                           f"F{i}_d{FlightData[i]['day_departure']}_{FlightData[i]['departureTime']}_{FlightData[i]['arrivalTime']}"))
            events2.append((FlightData[i]['departureTime'],
                           f"F{i}_d{FlightData[i]['day_departure']}_{FlightData[i]['departureTime']}_{FlightData[i]['arrivalTime']}"))
    # Gather all maintenance events for this aircraft (use day for sorting, ensure it follows flights on the same day)
    for d in model.D:
        for c in model.C:
            if value(model.y[j, d, c]) > 0.5:
                dt = (d-1)*24*60
                for i in model.F:

                    day = flight_data[i]['day_arrival']
                    if day != d:
                        continue
                    airport = flight_data[i]['destination']
                    if airport not in MA:
                        continue

                    t_arr = flight_data[i]['arrivalTime']
                    if value(model.z[i, j, d, c])>0.5:
                        dt = t_arr
                        break

                # Use a large offset to sort maintenance after all flights on the same day
                events.append((d * 1e6, f"M{c[0]}{d}_{dt}_{dt + All_Check_durations[c]}"))
                events2.append((dt, f"M{c[0]}{d}_{dt}_{dt + All_Check_durations[c]}"))
    # Sort all events chronologically
    events.sort()
    # Format output
    events_str = ", ".join([e[1] for e in events])
    print(f"Aircraft {j}: {events_str}")

    events2.sort()
    # Format output
    events2_str = ", ".join([e[1] for e in events2])
    print(f"Aircraft {j}: {events2_str}")

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# Prepare data (replace with your actual solution extraction)
events = []
for j in model.P:
    # Flights
    for i in model.F:
        if value(model.x[i, j]) > 0.5:
            events.append({
                'aircraft': j,
                'type': 'flight',
                'label': f'F{i}',
                'start': FlightData[i]['departureTime'],
                'end': FlightData[i]['arrivalTime'],
                'day': FlightData[i]['day_departure']
            })
    # Maintenance
    for d in model.D:
        for c in model.C:
            if value(model.y[j, d, c]) > 0.5:
                duration = All_Check_durations[c]
                dt = (d-1)*24*60
                for i in model.F:
                    t_arr = flight_data[i]['arrivalTime']
                    day = flight_data[i]['day_arrival']
                    if day != d:
                        continue
                    airport = flight_data[i]['destination']
                    if airport not in MA:
                        continue

                    if value(model.z[i, j, d, c])>0.5:
                        dt = t_arr
                        break

                # if All_Check_durations_days[c] <= 1:
                #     dt += 24*60

                events.append({
                    'aircraft': j,
                    'type': 'maintenance',
                    'label': f'M{c[0]}{d}_{(d-1) * 24 * 60 + dt}',
                    'start': dt,
                    'end':  dt + duration,
                    'day':  d
                })

# Sort by aircraft and start time
events.sort(key=lambda x: (x['aircraft'], x['start']))

# Plotting
fig, ax = plt.subplots(figsize=(15, 8))
flight_color = 'tab:blue'
maintenance_colors = {'A': 'tab:orange', 'B': 'tab:green', 'C': 'tab:red', 'D': 'tab:purple'}
aircraft_positions = {j: idx for idx, j in enumerate(sorted(set(e['aircraft'] for e in events)))}

for e in events:
    y = aircraft_positions[e['aircraft']]
    color = flight_color if e['type'] == 'flight' else maintenance_colors[e['label'][1]]
    ax.barh(y, e['end'] - e['start'], left=e['start'], height=0.4, color=color, edgecolor='black')
    ax.text(e['start'] + (e['end'] - e['start']) / 2, y, e['label'], ha='center', va='center', color='white', fontsize=8)

ax.set_yticks(list(aircraft_positions.values()))
ax.set_yticklabels([f'Aircraft {j}' for j in sorted(aircraft_positions.keys())])
ax.set_xlabel('Time (minutes)')
ax.set_title('Aircraft Flight and Maintenance Timeline')

flight_patch = mpatches.Patch(color=flight_color, label='Flight')
maintenance_patches = [mpatches.Patch(color=clr, label=f'Maintenance {typ}') for typ, clr in maintenance_colors.items()]
ax.legend(handles=[flight_patch] + maintenance_patches, loc='upper right')

plt.tight_layout()
plt.show()



