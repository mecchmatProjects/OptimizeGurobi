import re


def parse_airline_data(file_path):
    with open(file_path, 'r') as f:
        content = f.read()

    # Helper function to parse sets
    def parse_set(s):
        return [x.strip() for x in re.findall(r"(\w+)", s)]

    # Helper function to parse tuples
    def parse_tuples(s):
        return [tuple(x.split(',')) for x in re.findall(r"<([^>]+)>", s)]

    # Helper function to parse matrix
    def parse_matrix(s):
        return [
            [float(x.strip()) for x in row.split(',') if x.strip()]
            for row in re.findall(r"\[([^\]]*)\][,\s]*", s)
        ]

    # Parse Airports
    airports_match = re.search(r"Airports\s*=\s*{([^}]+)};", content)
    Airports = parse_set(airports_match.group(1)) if airports_match else []

    # Parse Nbflight
    nbflight_match = re.search(r"Nbflight\s*=\s*(\d+);", content)
    Nbflight = int(nbflight_match.group(1)) if nbflight_match else 0
    Flights = list(range(1, Nbflight + 1))

    # Parse Aircrafts
    aircrafts_match = re.search(r"Aircrafts\s*=\s*{([^}]+)};", content)
    Aircrafts = parse_set(aircrafts_match.group(1)) if aircrafts_match else []
    try:
        Aircrafts = [int(x) for x in Aircrafts]
    except Exception:
        # leave as strings if conversion fails
        pass

    # Parse Flight data
    flight_match = re.search(r"Flight\s*=\s*{([^}]+)};", content, re.DOTALL)
    flight_tuples = parse_tuples(flight_match.group(1)) if flight_match else []
    Flight = []
    for t in flight_tuples:
        parts = [x.strip() for x in t]
        if len(parts) >= 5:
            # some files may include trailing commas/spaces
            try:
                fnum = int(parts[0])
            except Exception:
                continue
            Flight.append({
                "flight": fnum,
                "origin": parts[1],
                "destination": parts[2],
                "departureTime": float(parts[3]),
                "arrivalTime": float(parts[4])
            })

    # Parse Cost matrix
    cost_match = re.search(r"Cost\s*=\s*\[(.*?)\]\s*;", content, re.DOTALL)
    cost = parse_matrix(cost_match.group(1)) if cost_match else []

    # Parse Aircraft initial positions
    aircraft_match = re.search(r"Aircraft\s*=\s*\[([^\]]+)\];", content, re.DOTALL)
    aircraft_tuples = parse_tuples(aircraft_match.group(1)) if aircraft_match else []
    a0 = {}
    for t in aircraft_tuples:
        parts = [x.strip() for x in t]
        if len(parts) >= 2:
            try:
                key = int(parts[0])
            except Exception:
                key = parts[0]
            a0[key] = parts[1]

    return {
        "Airports": Airports,
        "Nbflight": Nbflight,
        "Flights": Flights,
        "Flight": Flight,
        "Aircrafts": Aircrafts,
        "cost": cost,
        "a0": a0,
    }
