import types
import sys
from io import StringIO
import pytest

import Model_28Oct as M
from model_builder import build_model_from_data


def make_dummy_results():
    # Build a dummy results object that mimics solver results structure
    res = types.SimpleNamespace()
    res.solver = types.SimpleNamespace(num_nodes=1, time=0.5, gap=0.01)
    res.problem = types.SimpleNamespace(lower_bound=100.0, upper_bound=95.0)
    return res


def test_print_solver_summary_outputs(capsys):
    # Build a tiny model to feed into print_solver_summary
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
    model, FlightData, Days, AircraftInit = build_model_from_data(data)
    # create a dummy var/constraint to make counts non-zero
    # model already has variables from builder

    results = make_dummy_results()
    M.print_solver_summary(model, results)
    captured = capsys.readouterr()
    assert "Residual Gap" in captured.out or "Var\tConst\tNodes" in captured.out


def test_solve_model_with_mock(monkeypatch):
    # Monkeypatch SolverFactory in Model_28Oct module to return a dummy solver
    class DummySolver:
        def __init__(self):
            self.available = True
            self.options = {}
        def solve(self, model):
            return make_dummy_results()

    def fake_SolverFactory(name):
        return DummySolver()

    monkeypatch.setattr(M, 'SolverFactory', fake_SolverFactory)

    # Build tiny model
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
    model, FlightData, Days, AircraftInit = build_model_from_data(data)
    results = M.solve_model(model, solver_name='cplex')
    assert hasattr(results, 'solver')
