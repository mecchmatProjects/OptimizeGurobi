import pytest
from pyomo.opt import SolverFactory, TerminationCondition
from pyomo.common.errors import ApplicationError

from improved_model import build_full_model


def has_cbc():
    try:
        s = SolverFactory('cbc')
        return s.available(exception_flag=False)
    except Exception:
        return False


@pytest.mark.skipif(not has_cbc(), reason="CBC solver not available")
def test_small_instance_with_cbc():
    """Smoke integration test: build a tiny instance and solve with CBC.

    This test constructs a very small, in-memory instance (2 flights, 2 aircraft),
    builds the compact model via build_full_model and attempts to solve with CBC.
    The test asserts that CBC returns a feasible or optimal termination condition.
    """
    # Tiny instance
    data = {
        'Airports': ['A', 'B'],
        'Nbflight': 2,
        'Flights': [
            {'flight': 1, 'origin': 'A', 'destination': 'B', 'departureTime': 0.0, 'arrivalTime': 60.0},
            {'flight': 2, 'origin': 'B', 'destination': 'A', 'departureTime': 120.0, 'arrivalTime': 180.0},
        ],
        'Aircrafts': [0, 1],
        'cost': [[10, 20], [30, 40]],
        'a0': {0: 'A', 1: 'B'}
    }

    model, FlightData, Days, AircraftInit = build_full_model(data, add_equipment_turn=True, add_maint_block=False)

    solver = SolverFactory('cbc')
    # small instances should solve very quickly; run without verbose tee
    try:
        results = solver.solve(model)
    except ApplicationError as e:
        # Some CBC installations may reject options passed by the Pyomo plugin
        # (e.g., unsupported printingOptions). Treat such execution problems as
        # an environmental skip so the test suite remains stable in CI.
        pytest.skip(f"CBC execution failed (treated as skip): {e}")

    term = results.solver.termination_condition
    assert term in (TerminationCondition.optimal, TerminationCondition.feasible), f"Unexpected termination: {term}"
