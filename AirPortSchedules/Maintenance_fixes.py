from pyomo.environ import *
from pyomo.opt import SolverFactory

# --- CP-style Inputs ---
# Airports = ["A", "B"]
# Aircrafts = [1, 2]
# Nbflight = 6
# Flights = list(range(1, Nbflight + 1))
# Days = list(range(1, 8))
# MA = sorted(["A", "B", "C"])  # Maintenance airports

Airports =  ["A","B","C","D","E","F","H","G","K","I","J","N","R","Q","P","M","L","S"]
Nbflight = 103;
Aircrafts = [0,1,2,3,4,5,6,7,8,9]

DayShift = 24

Flights = list(range(1, Nbflight + 1))
Days = list(range(1, 8 * int(24/DayShift)))

MA = sorted(Airports)

# Flight Information
# Flight = [
#     {"flight": 1, "origin": "A", "destination": "B", "departureTime": 540, "arrivalTime": 660},
#     {"flight": 2, "origin": "B", "destination": "A", "departureTime": 690, "arrivalTime": 810},
#     {"flight": 3, "origin": "A", "destination": "B", "departureTime": 840, "arrivalTime": 960},
#     {"flight": 4, "origin": "B", "destination": "A", "departureTime": 570, "arrivalTime": 690},
#     {"flight": 5, "origin": "A", "destination": "B", "departureTime": 720, "arrivalTime": 840},
#     {"flight": 6, "origin": "B", "destination": "A", "departureTime": 870, "arrivalTime": 990}
# ]

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
],

for f in Flight[0]:
    print(f)

# Derived FlightData
FlightData = {
    f["flight"]: {
        "origin": f["origin"],
        "destination": f["destination"],
        "departureTime": f["departureTime"],
        "arrivalTime": f["arrivalTime"],
        "duration": f["arrivalTime"] - f["departureTime"],
        "day": int(f["departureTime"] // (DayShift * 60)) + 1
    } for f in Flight[0]
}
for it in FlightData.values():
    print(it)

# Initial aircraft locations
a0 = {1: "A", 2: "B"}

# Cost matrix
# cost = [
#      [6804, 6870],
#      [4536, 4580],
#      [7216, 7286],
#      [1133, 1144],
#      [6185, 6245],
#      [5678, 5700]
#     ]

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

# Tmax = 8 * 60  # in minutes
# nu = 15
# dmax = 3

Mbig = 9999

min_turn = 30  # in minutes


# Maintenance thresholds
A_check_hours = 400.0
B_check_hours = 600.0
C_check_days = 540
D_check_days = 1825


A_check_days = int((A_check_hours+DayShift) / DayShift)

# Maintenance durations
A_check_duration = 8 * 60
B_check_duration = 16 * 60
C_check_duration = 5
D_check_duration = 10


mc = {(i, j, d): 100 for i in Flights for j in Aircrafts for d in Days}  # dummy maintenance cost

# Maintenance capacity
mcap = {(m, d): 2 for m in MA for d in Days}  # dummy capacity

# Helper functions
F_m = {m: [i for i in Flights if FlightData[i]["origin"] == m] for m in MA}  # The set of flights which departs from airport m

F_arr_k = {k: [i for i in Flights if FlightData[i]["destination"] == k] for k in sorted(Airports)}  # The set of flights which land in airport k
F_dep_k = {k: [i for i in Flights if FlightData[i]["origin"] == k] for k in sorted(Airports)}  # The set of flights which land in airport k

# The set of flights which land in airport k before time t
# def F_gkt(k, t, delta):
#     return [i for i in Flights if FlightData[i]["destination"] == k and FlightData[i]["departureTime"] <= t - delta]
F_arr_t = lambda k, t, delta: [i for i in F_arr_k[k] if FlightData[i]["arrivalTime"] <= t - delta]

# The set of flights which land in airport k before time t
def F_lkt(k,t):
    return [i for i in Flights if FlightData[i]["origin"] == k and FlightData[i]["departureTime"] < t]

F_dep_t = lambda k, t: [i for i in F_dep_k[k] if FlightData[i]["departureTime"] < t]


F_d = {d: [i for i in Flights if FlightData[i]["day"] == d] for d in Days}
F_d_next = lambda d1, d2: [i for i in Flights if d1 <= FlightData[i]["day"] <= d2]
F_d_i = lambda d, i: [i2 for i2 in Flights if FlightData[i2]["day"] == d and FlightData[i2]["arrivalTime"] > FlightData[i]["arrivalTime"]]



model = ConcreteModel()

model.F = Set(initialize=Flights)
model.P = Set(initialize=sorted(Aircrafts))
# model.A = Set(initialize=sorted(Airports))
model.A = Set(initialize=list(set(f['origin'] for f in FlightData.values()).union(set(f['destination'] for f in FlightData.values()))))

print(model.A)

model.D = Set(initialize=sorted(Days))
model.MA = Set(initialize=sorted(MA))

print([j for j in model.P])

model.x = Var(model.F, model.P, domain=Binary)
model.z = Var(model.F, model.P, model.D, domain=Binary)
model.y = Var(model.P, model.D, domain=Binary)

model.obj = Objective(
    expr=sum(cost[i-1][j-1] * model.x[i, j] for i in model.F for j in model.P) +
         sum(mc[i, j, d] * model.z[i, j, d] for m in model.MA for i in F_m[m] for j in model.P for d in model.D),
    sense=minimize
)

model.c1 = ConstraintList()
for i in model.F:
    model.c1.add(sum(model.x[i, j] for j in model.P) == 1)

# Replacing c23 with corrected equipment_turn_constraints
turn_time = min_turn
flight_data = FlightData
flight_arr = {k: [i for i in model.F if FlightData[i]['destination'] == k] for k in model.A}

# def F_geq_k(k, t):
#     return [i for i, f in flight_data.items() if f['destination'] == k and f['arrivalTime'] <= t + turn_time]
#
# def F_lt_k(k, t):
#     return [i for i, f in flight_data.items() if f['origin'] == k and f['departureTime'] < t]

model.equipment_turn_constraints = ConstraintList()
for j in model.P:
    for k in model.A:
        for i in F_dep_k[k]:
            t_dep = flight_data[i]['departureTime']
            lhs_geq = sum(model.x[i1, j] for i1 in F_arr_t(k, t_dep, turn_time))
            lhs_lt = sum(model.x[i1, j] for i1 in F_dep_t(k, t_dep))

            print("ijk", i, j, k, end=":")
            print(t_dep, end="\t")
            print(F_arr_t(k, t_dep, turn_time), lhs_geq, end="\t")
            print(F_dep_t(k, t_dep), lhs_lt)

            if k != AircraftInit[j]:
                model.equipment_turn_constraints.add(lhs_geq - lhs_lt >= model.x[i, j])
            else:
                model.equipment_turn_constraints.add(lhs_geq - lhs_lt >= model.x[i, j] - 1)


model.maint_last = ConstraintList()
for i in model.F:
    for j in model.P:
        for d in model.D:
            for i2 in F_d_i(d, i):
                model.maint_last.add(model.z[i, j, d] + model.x[i2, j] <= 1)

model.maint_assignment = ConstraintList()
for i in model.F:
    for j in model.P:
        for d in model.D:
            model.maint_assignment.add(model.x[i, j] >= model.z[i, j, d])

model.maint_capacity = ConstraintList()
for d in model.D:
    for m in model.MA:
        relevant_flights = F_m.get(m, [])
        if relevant_flights:
            model.maint_capacity.add(
                sum(model.z[i, j, d] for i in relevant_flights for j in model.P) <= mcap[m, d]
            )

model.maint_link = ConstraintList()
for d in model.D:
    for m in model.MA:
        for j in model.P:
            model.maint_link.add(sum(model.z[i, j, d] for i in F_m[m]) == model.y[j, d])


model.maint_spacing = ConstraintList()
# model.maint_spacing0 = ConstraintList()
# print(Days)


Acheck_start_days = {}
for plane, check_prev in Acheck.items():
    Acheck_start_days[plane] = int((A_check_hours - check_prev)/24)
    print(plane, Acheck_start_days[plane])

# for j in model.P:
#     print("j is", j, Days[0: Acheck_start_days[j]+1])
#     model.maint_spacing0.add(sum(model.y[j, r] for r in Days[0: Acheck_start_days[j]+1]) >= 1)

for j in model.P:
    print("j=",j)
    for start in range(0, len(Days) - A_check_days + 1):
        print("checks", start, start + A_check_days, Days[start:start + A_check_days])
        model.maint_spacing.add(sum(model.y[j, r] for r in Days[start:start + A_check_days]) >= 1)


model.maint_cumulative = ConstraintList()
for j in model.P:
    for start in range(len(Days) - 1):
        for end in range(start + 2, min(start + A_check_days, len(Days))):
            d = Days[start]
            d_ = Days[end]
            t_sum = sum(FlightData[i]['duration'] * model.x[i, j] for i in F_d_next(d+1, d_))
            y_sum = sum(model.y[j, r] for r in Days[start+1:end])
            model.maint_cumulative.add(t_sum <= A_check_hours + Mbig * y_sum + Mbig*(2 - model.y[j, d] - model.y[j, d_]) )

model.maint_cumulative0 = ConstraintList()
for j in model.P:
    for end in range(1, min(A_check_days, len(Days))):
        d = Days[0]
        d_ = Days[end]
        t_sum = sum(FlightData[i]['duration'] * model.x[i, j] for i in F_d_next(d, d_))
        y_sum = sum(model.y[j, r] for r in Days[1:end])
        model.maint_cumulative0.add(t_sum <= A_check_hours + Mbig * y_sum + Mbig*(2 - model.y[j, d] - model.y[j, d_]) )


# Solve
solver = SolverFactory('cplex')  # Or 'cplex', 'glpk', etc.
solver.solve(model)



print("\nAssignment Results:")
for i in model.F:
    for j in model.P:
        if value(model.x[i, j]) > 0.5:
            print(f"Flight {i} assigned to Plane {j}")

print(f"Total Cost: {value(model.obj)}")
