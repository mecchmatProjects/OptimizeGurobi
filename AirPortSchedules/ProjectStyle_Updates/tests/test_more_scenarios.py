import os
import sys
from pyomo.environ import value, Constraint as PyomoConstraint

# Ensure repo root on path (tests run from tests/ by pytest)
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from improved_model import build_full_model
from model_params import Params


def multi_airport_instance():
    data = {
        "Airports": ["A", "B"],
        "Nbflight": 4,
        "Aircrafts": [1, 2],
        "Flight": [
            {"flight": 1, "origin": "A", "destination": "A", "departureTime": 0, "arrivalTime": 60},
            {"flight": 2, "origin": "A", "destination": "B", "departureTime": 120, "arrivalTime": 200},
            {"flight": 3, "origin": "B", "destination": "A", "departureTime": 300, "arrivalTime": 360},
            {"flight": 4, "origin": "B", "destination": "B", "departureTime": 420, "arrivalTime": 480},
        ],
        "cost": [[0, 0], [0, 0], [0, 0], [0, 0]],
        "a0": {1: "A", 2: "B"},
    }
    return data


def test_nontrivial_maintenance_flags():
    """Enable multiple maintenance features and ensure model builds and constraints are satisfiable by trivial assignment."""
    data = multi_airport_instance()
    # tighten param horizons so spacing/cumulative checks produce constraints in short horizon
    p = Params()
    p.All_Check_List = ["Acheck"]
    p.All_Check_days = {"Acheck": 2}
    p.All_Check_durations_days = {"Acheck": 1}
    p.All_Check_durations = {"Acheck": 60}
    p.All_Check_Done_hours = {"Acheck": 1000}

    model, FlightData, Days, AircraftInit = build_full_model(
        data,
        min_turn=30,
        add_equipment_turn=True,
        add_maint_block=True,
        params=p,
        enable_maint_spacing=True,
        enable_maint_spacing2=True,
        enable_maint_cumulative=True,
        enable_maint_cumulative_start=True,
        enable_maint_checks_days=True,
        enable_maint_capacity=True,
        enable_maint_link=True,
        enable_maint_hierarchy=True,
    )

    # basic presence checks
    assert hasattr(model, "maint_spacing")
    assert hasattr(model, "maint_cumulative")
    assert hasattr(model, "maint_checks_days")
    assert hasattr(model, "maint_capacity")

    # Construct trivial feasible assignment: assign flights to first plane.
    # For maintenance-related vars: don't force all mega_check==0 when spacing/cumulative
    # constraints are enabled; instead set at least one mega_check active so spacing
    # constraints are satisfied by construction.
    j0 = list(model.P)[0]
    for i in model.F:
        for j in model.P:
            model.x[i, j].fix(1 if j == j0 else 0)

    # initialize maintenance markers to 0
    if hasattr(model, 'z'):
        for v in model.z.values():
            v.fix(0)
    if hasattr(model, 'y'):
        for v in model.y.values():
            v.fix(0)
    if hasattr(model, 'mega_check'):
        for v in model.mega_check.values():
            v.fix(0)
        # ensure spacing constraints happy: set one mega_check on first day for first plane
        d0 = list(model.D)[0]
        c0 = list(model.C)[0]
        model.mega_check[j0, d0, c0].fix(1)

    # Evaluate all active constraints
    violated = []
    for con in model.component_data_objects(ctype=PyomoConstraint, active=True):
        try:
            b = value(con.body)
        except Exception:
            violated.append(con)
            continue
        lower = value(con.lower) if con.lower is not None else None
        upper = value(con.upper) if con.upper is not None else None
        # simple numeric check
        if lower is not None and b + 1e-6 < lower:
            violated.append(con)
        if upper is not None and b - 1e-6 > upper:
            violated.append(con)

    assert len(violated) == 0, f"Found violated constraints in maintenance-enabled model: {len(violated)}"


def test_multi_airport_capacity_constraints():
    data = multi_airport_instance()
    p = Params()
    # set capacity small so constraint is meaningful
    p.mcap = {("A", d): 1 for d in range(1, 6)}
    p.mcap.update({("B", d): 1 for d in range(1, 6)})

    model, FlightData, Days, AircraftInit = build_full_model(
        data,
        min_turn=30,
        add_equipment_turn=False,
        add_maint_block=True,
        params=p,
        enable_maint_capacity=True,
    )

    assert hasattr(model, "maint_capacity")

    # trivial feasible assignment and no maintenance
    j0 = list(model.P)[0]
    for i in model.F:
        for j in model.P:
            model.x[i, j].fix(1 if j == j0 else 0)
    if hasattr(model, "z"):
        for v in model.z.values():
            v.fix(0)
    if hasattr(model, "y"):
        for v in model.y.values():
            v.fix(0)

    # Check capacity constraints evaluate to true
    for con in getattr(model, 'maint_capacity'):
        # ConstraintList is sometimes indexed by integers; ensure we get ConstraintData
        con_data = con
        if not hasattr(con, 'body'):
            # try to fetch via .items() mapping
            try:
                con_data = model.maint_capacity[con]
            except Exception:
                continue
        b = value(con_data.body)
        upper = value(con_data.upper) if con_data.upper is not None else None
        assert upper is not None
        assert b - 1e-6 <= upper
