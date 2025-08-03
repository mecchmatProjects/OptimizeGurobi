import os
import re
from collections import defaultdict


def parse_airline_data(file_path):
    with open(file_path, 'r') as f:
        content = f.read()

    # Helper function to parse sets
    def parse_set(s):
        return [x.strip() for x in re.findall(r'(\w+)', s)]

    # Helper function to parse tuples
    def parse_tuples(s):
        return [tuple(x.split(',')) for x in re.findall(r'<([^>]+)>', s)]

    # Helper function to parse matrix
    def parse_matrix(s):
        return [
            [float(x.strip()) for x in row.split(',') if x.strip()]
            for row in re.findall(r'\[([^\]]*)\][,\s]*', s)
        ]

    # Parse Airports
    airports_match = re.search(r'Airports\s*=\s*{([^}]+)};', content)
    Airports = parse_set(airports_match.group(1)) if airports_match else []

    # Parse Nbflight
    nbflight_match = re.search(r'Nbflight\s*=\s*(\d+);', content)
    Nbflight = int(nbflight_match.group(1)) if nbflight_match else 0
    Flights = list(range(1, Nbflight + 1))

    # Parse Aircrafts
    aircrafts_match = re.search(r'Aircrafts\s*=\s*{([^}]+)};', content)
    Aircrafts = parse_set(aircrafts_match.group(1)) if aircrafts_match else []

    # Parse Flight data
    flight_match = re.search(r'Flight\s*=\s*{([^}]+)};', content, re.DOTALL)
    flight_tuples = parse_tuples(flight_match.group(1)) if flight_match else []
    Flight = []
    for t in flight_tuples:
        parts = [x.strip() for x in t]
        if len(parts) >= 5:
            Flight.append({
                "flight": int(parts[0]),
                "origin": parts[1],
                "destination": parts[2],
                "departureTime": float(parts[3]),
                "arrivalTime": float(parts[4])
            })


    # Parse Cost matrix
    #cost_match = re.search(r'\s*Cost\s*=\[()\];', content)
    # cost_match = re.search(r'Cost\s*=\s*\[(.*?)\]\s*;', content, re.DOTALL)
    # print(cost_match)
    # cost = parse_matrix(cost_match.group(0)) if cost_match else []

    cost_match = re.search(r'Cost\s*=\s*\[(.*?)\]\s*;', content, re.DOTALL)
    print(cost_match)
    cost = parse_matrix(cost_match.group(1)) if cost_match else []

    # Parse Aircraft initial positions
    aircraft_match = re.search(r'Aircraft\s*=\s*\[([^\]]+)\];', content)
    print(aircraft_match)
    aircraft_tuples = parse_tuples(aircraft_match.group(1)) if aircraft_match else []
    a0 = {}
    for t in aircraft_tuples:
        parts = [x.strip() for x in t]
        if len(parts) >= 2:
            a0[int(parts[0])] = parts[1]

    # Parse checks
    checks = {}
    for check_type in ['Acheck', 'Bcheck', 'Ccheck', 'Dcheck']:
        check_match = re.search(fr'{check_type}\s*=\s*\[([^\]]+)\];', content)
        check_tuples = parse_tuples(check_match.group(1)) if check_match else []
        check_dict = {}
        for t in check_tuples:
            parts = [x.strip() for x in t]
            if len(parts) >= 2:
                check_dict[int(parts[0])] = float(parts[1])
        checks[check_type] = check_dict

    # Maintenance airports (example - modify as needed)
    MA = sorted(Airports[:3])  # First 3 airports as maintenance

    # Days (example - 7-day week)
    Days = list(range(1, 8))

    return {
        "Airports": Airports,
        "Nbflight": Nbflight,
        "Flights": Flights,
        "Flight": Flight,
        "Aircrafts": Aircrafts,
        "cost": cost,
        "a0": a0,
        "MA": MA,
        "Days": Days,
        "Acheck": checks['Acheck'],
        "Bcheck": checks['Bcheck'],
        "Ccheck": checks['Ccheck'],
        "Dcheck": checks['Dcheck']
    }


# Example usage
if __name__ == "__main__":

    TEST_DIR = "TestsData"
    data = parse_airline_data("test_000.dat")

    # Access parsed data
    print("Airports:", data["Airports"])
    print("Number of flights:", data["Nbflight"])
    print("Flight details:")
    for val in data["Flight"]:
        print(val, ",")
    print("Cost matrix sample:", data["cost"])
    print("Initial aircraft positions:", data["a0"])
    print("Maintenance airports:", data["MA"])
    print("A-checks:", data["Acheck"])
    print("B-checks:", data["Bcheck"])
    print("C-checks:", data["Ccheck"])
    print("D-checks:", data["Dcheck"])

    for root, dirs, files in os.walk(TEST_DIR):
        for fname in files:
            if len(fname) > 3 and fname.endswith(".dat"):
                data = parse_airline_data(os.path.join(root,fname))
                # Access parsed data
                print("Airports:", data["Airports"])
                print("Number of flights:", data["Nbflight"])
                print("Flight details:")
                for val in data["Flight"]:
                    print(val, ",")
                print("Cost matrix sample:", data["cost"])
                print("Initial aircraft positions:", data["a0"])



