Input/Output

Input and output are stored in `.csv` files.

Input

Each problem instance is described by a `.csv` file. This file consists of three main parts:
1) Reservation data
2) Zone data
3) Vehicle data

Reservation data is described as follows:

Reservation ID; Zone ID; Day; Start time; Duration; {Possible vehicle IDs}; Penalty 1; Penalty 2

- Reservation ID: A unique identifier for this reservation. It can be a string without a fixed format.
- Zone ID: The ID of the zone where this reservation was made.
- Day: The day the reservation starts. Days are indexed: 0 is the first day, 1 is the second day, etc.
- Start time: Start time of the reservation, in minutes after midnight. For example, 8:30 AM is 510, and 1:00 PM is 780.
- Duration: Total duration of the reservation, expressed in minutes.
- Possible vehicle IDs: List of vehicle IDs that can be assigned to this reservation.
- Penalty 1: The cost of not assigning the reservation to any vehicle.
- Penalty 2: The cost of assigning the reservation to a vehicle in an adjacent zone.

Zone data is described as follows:

Zone ID; {List of adjacent Zone IDs}

- Zone ID: A unique identifier for this zone. It can be a string without a fixed format.
- {List of adjacent Zone IDs}: List of zone IDs that are adjacent to this zone.

Vehicle data is described as follows:

Vehicle ID

- Vehicle ID: A unique identifier for this vehicle. It can be a string without a fixed format.

At the end of the input file, the total number of days in the planning period is provided.


