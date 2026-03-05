import os
import sys
# Ensure repo root on path (tests run from tests/ by pytest)
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pyomo.environ import value, Constraint as PyomoConstraint
from improved_model import build_full_model
from model_params import Params


def small_instance():
    data = {
        "Airports": ["A"],
        "Nbflight": 2,
        "Aircrafts": [1],
        "Flight": [
            {"flight": 1, "origin": "A", "destination": "A", "departureTime": 0, "arrivalTime": 60},
            {"flight": 2, "origin": "A", "destination": "A", "departureTime": 120, "arrivalTime": 180},
        ],
        "cost": [[0], [0]],
        "a0": {1: "A"},
    }
    return data


def is_constraint_satisfied(con, tol=1e-6):
    """Return True if pyomo Constraint con is satisfied under current variable values."""
    # Constraint body value
    try:
        b = value(con.body)
    except Exception:
        # if body cannot be evaluated, consider it unsatisfied
        return False

    lower = value(con.lower) if con.lower is not None else None
    upper = value(con.upper) if con.upper is not None else None

    if lower is not None and upper is not None:
        # equality or ranged constraint
        if abs(lower - upper) <= tol:
            return abs(b - lower) <= tol
        # ranged: lower <= b <= upper
        return (b + tol >= lower) and (b - tol <= upper)
    if lower is not None:
        return b + tol >= lower
    if upper is not None:
        return b - tol <= upper
    # unconstrained? treat as satisfied
    return True


def test_feasible_assignment_satisfies_constraints():
    data = small_instance()
    params = Params()

    model, FlightData, Days, AircraftInit = build_full_model(
        data,
        min_turn=30,
        add_equipment_turn=True,
        add_maint_block=True,
        params=params,
    )

    # Trivial feasible assignment: assign each flight to the single available plane
    planes = list(model.P)
    assert len(planes) >= 1
    j0 = planes[0]

    # Fix maintenance-related variables to 0 (no maintenance performed)
    if hasattr(model, 'z'):
        for v in model.z.values():
            v.fix(0)
    if hasattr(model, 'y'):
        for v in model.y.values():
            v.fix(0)
    if hasattr(model, 'mega_check'):
        for v in model.mega_check.values():
            v.fix(0)

    # Set x so each flight assigned to j0
    for i in model.F:
        for j in model.P:
            if j == j0:
                model.x[i, j].fix(1)
            else:
                model.x[i, j].fix(0)

    # Now verify every constraint is satisfied
    violated = []
    for con in model.component_data_objects(ctype=PyomoConstraint, active=True):
        if not is_constraint_satisfied(con):
            violated.append(con)

    assert len(violated) == 0, f"Found violated constraints: {len(violated)}"


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
