"""
Converter between IBM CPLEX .dat format and JSON format for airport scheduling data.

Usage:
    python convert_dat_json.py input.dat [output.json]
    python convert_dat_json.py input.json [output.dat]

Rules:
    dat -> json : fields missing in .dat are set to null (None)
    json -> dat : fields not present in .dat are ignored
"""

import json
import re
import sys
import os


# ---------------------------------------------------------------------------
# DAT  →  JSON
# ---------------------------------------------------------------------------

def parse_dat(text: str) -> dict:
    """Parse CPLEX .dat file text and return a dict matching the JSON schema."""

    def extract_block(name: str, src: str):
        """Return the raw text between the first '{' and matching '}' for `name =`."""
        pat = re.compile(rf'\b{name}\s*=\s*\{{', re.IGNORECASE)
        m = pat.search(src)
        if not m:
            return None
        depth = 1
        i = m.end()
        while i < len(src) and depth:
            if src[i] == '{':
                depth += 1
            elif src[i] == '}':
                depth -= 1
            i += 1
        return src[m.end():i - 1]  # contents between outer { }

    def extract_array_block(name: str, src: str):
        """Return contents between first '[' and matching ']' for `name =`."""
        pat = re.compile(rf'\b{name}\s*=\s*\[', re.IGNORECASE)
        m = pat.search(src)
        if not m:
            return None
        depth = 1
        i = m.end()
        while i < len(src) and depth:
            if src[i] == '[':
                depth += 1
            elif src[i] == ']':
                depth -= 1
            i += 1
        return src[m.end():i - 1]

    def extract_bracket_block(name: str, src: str):
        """Return contents between first '[' and matching ']' for `name =`."""
        pat = re.compile(rf'(?<![a-zA-Z_]){name}\s*=\s*\[', re.IGNORECASE)
        m = pat.search(src)
        if not m:
            return None
        depth = 1
        i = m.end()
        while i < len(src) and depth:
            if src[i] == '[':
                depth += 1
            elif src[i] == ']':
                depth -= 1
            i += 1
        return src[m.end():i - 1]

    # --- Aircrafts ---
    ac_block = extract_block('Aircrafts', text)
    if ac_block is not None:
        tokens = [t.strip() for t in ac_block.split(',') if t.strip()]
        try:
            aircrafts = [int(t) for t in tokens]
        except ValueError:
            aircrafts = tokens
    else:
        aircrafts = None

    # --- Flights ---
    flight_block = extract_block('Flight', text)
    flights = []
    if flight_block is not None:
        # each entry: <id, origin, dest, depart, arrive>
        for m in re.finditer(r'<([^>]+)>', flight_block):
            parts = [p.strip() for p in m.group(1).split(',')]
            if len(parts) == 5:
                fid_raw, orig, dest, dep, arr = parts
                try:
                    fid = int(fid_raw)
                except ValueError:
                    fid = fid_raw
                try:
                    dep = float(dep)
                except ValueError:
                    pass
                try:
                    arr = float(arr)
                except ValueError:
                    pass
                flights.append([fid, orig, dest, dep, arr])

    # --- Aircraft initial positions ---
    # Format: Aircraft = [<0,A> ,<1,C> ,...]
    aircraft_init_pos = None
    ac_init_block = extract_bracket_block('Aircraft', text)
    if ac_init_block is not None:
        init_dict = {}
        for m in re.finditer(r'<(\d+)\s*,\s*([^>]+)>', ac_init_block):
            init_dict[m.group(1)] = m.group(2).strip()
        if init_dict:
            aircraft_init_pos = init_dict

    # --- Cost matrix ---
    cost_block = extract_array_block('Cost', text)
    cost = []
    if cost_block is not None:
        for m in re.finditer(r'\[([^\]]+)\]', cost_block):
            row_tokens = [t.strip() for t in m.group(1).split(',') if t.strip()]
            try:
                row = [float(v) for v in row_tokens]
            except ValueError:
                row = row_tokens
            cost.append(row)

    result = {
        "Aircrafts": aircrafts,
        "AIRCRAFT_INIT_POS": aircraft_init_pos,
        "Flights": flights if flights else None,
        "Cost_Matrix": cost if cost else None,
        "Maintenance_Thresholds": None,
        "Maintenance_Durations": None,
        "Station_Capacity": None,
        "Initial_Checks": None,
    }
    return result


def dat_to_json(dat_path: str, json_path: str):
    with open(dat_path, 'r', encoding='utf-8') as fh:
        text = fh.read()
    data = parse_dat(text)
    with open(json_path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=4)
    print(f"Converted  {dat_path}  →  {json_path}")


# ---------------------------------------------------------------------------
# JSON  →  DAT
# ---------------------------------------------------------------------------

def build_dat(data: dict) -> str:
    lines = []

    # --- Airports: collect from Flights ---
    flights = data.get("Flights") or []
    airports = []
    seen = set()
    for f in flights:
        for ap in (f[1], f[2]):
            if ap not in seen:
                seen.add(ap)
                airports.append(ap)
    # Also preserve any airports mentioned in Station_Capacity if present
    sc = data.get("Station_Capacity") or {}
    for ap in sc:
        if ap not in seen:
            seen.add(ap)
            airports.append(ap)
    airports_str = ','.join(airports) + (',' if airports else '')
    lines.append(f"Airports =  {{{airports_str}}};")

    # --- Nbflight ---
    lines.append(f"Nbflight = {len(flights)};")

    # --- Aircrafts ---
    aircrafts = data.get("Aircrafts") or []
    ac_str = ','.join(str(a) for a in aircrafts) + (',' if aircrafts else '')
    lines.append(f"Aircrafts = {{{ac_str}}};")

    # --- Flight ---
    lines.append("Flight = {")
    for f in flights:
        fid, orig, dest, dep, arr = f[0], f[1], f[2], f[3], f[4]
        lines.append(f"<{fid},{orig},{dest},{dep},{arr}>")
    lines.append("};")

    # --- Cost ---
    cost = data.get("Cost_Matrix") or data.get("Cost") or []
    lines.append("Cost =[")
    for row in cost:
        row_str = ','.join(str(v) for v in row) + ','
        lines.append(f"[{row_str}]")
    lines.append("];")

    # --- Aircraft initial positions ---
    init_pos = data.get("AIRCRAFT_INIT_POS") or {}
    if init_pos:
        entries = ', '.join(f'<{k},{v}>' for k, v in sorted(init_pos.items(), key=lambda x: int(x[0])))
        lines.append(f"Aircraft =\n[{entries} ,];")
    else:
        lines.append("Aircraft =")

    return '\n'.join(lines) + '\n'


def json_to_dat(json_path: str, dat_path: str):
    with open(json_path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
    text = build_dat(data)
    with open(dat_path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(f"Converted  {json_path}  →  {dat_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    src = sys.argv[1]
    ext = os.path.splitext(src)[1].lower()

    if ext == '.dat':
        dst = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + '.json'
        dat_to_json(src, dst)
    elif ext == '.json':
        dst = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + '.dat'
        json_to_dat(src, dst)
    else:
        print(f"Unsupported file extension: {ext!r}. Expected .dat or .json")
        sys.exit(1)


if __name__ == '__main__':
    main()
