
from pyomo.environ import ConcreteModel, Set, Var, Binary, Objective, ConstraintList, minimize

# Avoid importing large top-level constants from Model_28Oct to prevent circular
# imports when tests import model_builder or improved_model. Provide small
# sensible defaults used by the lightweight test builder.
DayShift = 24
min_turn = 30
All_Check_List = ["C1"]
All_Checks = {}
All_Check_days = {}
All_Check_Done_hours = {}
All_Check_durations = {}
All_Check_durations_days = {}
Mbig = 10**6
USE_CHECK_HIERARCHY = False
USE_CHECKS_SANITY = False
USE_DAYS_CHECKS = False
USE_EXISTING_DAYS_CHECKS = False
USE_EXISTING_HRS_CHECK = False

# Developer notes: compact model contract
# -------------------------------------
# This lightweight builder constructs a compact, test-friendly Pyomo model
# suitable for unit tests. It mimics the structure used in the full canonical
# builder but intentionally keeps the model small and robust for testing:
# - Inputs: `data` (parsed instance dict with keys like 'Flight', 'Airports',
#   'Aircrafts', 'a0', 'cost', 'Nbflight').
# - Outputs: (model, FlightData, Days, AircraftInit)
# - Modelled variables: x (assignment), z (maintenance markers), y
#   (maintenance activations) and mega_check aggregation.
# - Constraints included: per-flight assignment, x>=z activation, z->y link,
#   and one-check-per-plane-per-day blocking. The full builder augments these
#   with continuity/equipment-turn and more complex maintenance constraints.
#
# Keep this module minimal and avoid importing large configuration constants
# from `Model_28Oct.py` to prevent circular imports when tests import the
# builder or `improved_model`.


def build_model_from_data(data):
    """Construct a Pyomo model (simplified) from parsed data dictionary.

    This builds the main sets, binary decision variables and a subset of constraints
    sufficient for structural unit tests (assignment completeness, maintenance links,
    activation and blocking constraints).
    """
    Airports = data.get("Airports", [])
    Nbflight = data.get("Nbflight", len(data.get("Flights", [])))
    Flights = list(range(1, Nbflight + 1))
    Aircrafts = data.get("Aircrafts", [])
    # The parser may provide both 'Flights' (ids) and 'Flight' (dictionaries).
    # Prefer the detailed list under 'Flight' if available.
    Flight_list = data.get("Flight", data.get("Flights", []))
    cost = data.get("cost", [])
    AircraftInit = data.get("a0", {})

    FlightData = {
        f["flight"]: {
            "origin": f["origin"],
            "destination": f["destination"],
            "departureTime": f["departureTime"],
            "arrivalTime": f["arrivalTime"],
            "duration": f["arrivalTime"] - f["departureTime"],
            "day_departure": int(f["departureTime"] // (DayShift * 60)) + 1,
            "day_arrival": int(f["arrivalTime"] // (DayShift * 60)) + 1,
        } for f in Flight_list
    }

    MAX_DAYS = max([y["day_arrival"] for x, y in FlightData.items()]) + 1
    MAX_DAYS = max(8, MAX_DAYS)
    Days = list(range(1, MAX_DAYS * int(24.1 / DayShift)))

    MA = sorted(Airports)

    model = ConcreteModel()
    model.F = Set(initialize=Flights)
    model.P = Set(initialize=sorted(Aircrafts))
    model.A = Set(initialize=sorted(Airports))
    model.D = Set(initialize=sorted(Days))
    model.MA = Set(initialize=sorted(MA))
    model.C = Set(initialize=sorted(All_Check_List))

    # Decision variables
    model.x = Var(model.F, model.P, domain=Binary)
    model.z = Var(model.F, model.P, model.D, model.C, domain=Binary)
    model.y = Var(model.P, model.D, model.C, domain=Binary)
    model.mega_check = Var(model.P, model.D, model.C, domain=Binary)

    # Objective: simplified (assignment + dummy maintenance)
    model.obj = Objective(expr=sum((cost[i-1][j-1] if cost else 0) * model.x[i, j]
                                    for i in model.F for j in model.P), sense=minimize)

    # Constraint C1: each flight assigned exactly once
    model.c1 = ConstraintList()
    for i in model.F:
        model.c1.add(sum(model.x[i, j] for j in model.P) == 1)

    # Simple link: x >= z (activation for flights)
    model.maint_assignment = ConstraintList()
    for i in model.F:
        for j in model.P:
            for d in model.D:
                for c in model.C:
                    model.maint_assignment.add(model.x[i, j] >= model.z[i, j, d, c])

    # Link z -> y (if any z present then y triggers)
    model.maint_link = ConstraintList()
    for j in model.P:
        for d in model.D:
            for c in model.C:
                model.maint_link.add(sum(model.z[i, j, d, c] for i in model.F) == model.y[j, d, c])

    # No more than one check per plane per day
    model.maint_block_checks = ConstraintList()
    for j in model.P:
        for d in model.D:
            model.maint_block_checks.add(sum(model.y[j, d, check] for check in All_Check_List) <= 1)

    return model, FlightData, Days, AircraftInit
