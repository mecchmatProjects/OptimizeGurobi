import pytest

from pyomo.opt import SolverFactory, TerminationCondition

from improved_model import build_full_model


def test_integration_cplex_small_instance():
    # Skip if CPLEX is not available in this environment
    solver = SolverFactory('cplex')
    if not solver.available(exception_flag=False):
        pytest.skip('CPLEX solver is not available')

    # Build a tiny feasible instance: one airport, one flight, one aircraft
    data = {
        'Airports': ['A'],
        'Nbflight': 1,
        'Flights': [
            {'flight': 1, 'origin': 'A', 'destination': 'A', 'departureTime': 0.0, 'arrivalTime': 60.0},
        ],
        'Aircrafts': [0],
        'cost': [[10.0]],
        'a0': {0: 'A'}
    }

    model, FlightData, Days, AircraftInit = build_full_model(data)

    # Solve with a short time limit to keep CI fast
    solver.options['timelimit'] = 10
    results = solver.solve(model)

    term = results.solver.termination_condition
    assert term in (TerminationCondition.optimal, TerminationCondition.feasible)
