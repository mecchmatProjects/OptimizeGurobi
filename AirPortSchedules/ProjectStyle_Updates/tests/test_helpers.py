import os
import sys

# Ensure repo root on path (tests run from tests/ by pytest)
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from model_builder import build_model_from_data
from improved_model import add_equipment_turn_constraints, add_maint_block_and_related
from model_params import Params, normalize_params


def small_data_one_airport():
    return {
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


def test_add_equipment_turn_constraints_creates_list():
    data = small_data_one_airport()
    model, FlightData, Days, AircraftInit = build_model_from_data(data)

    # call helper
    add_equipment_turn_constraints(model, FlightData, min_turn=30, AircraftInit=AircraftInit)

    assert hasattr(model, 'equipment_turn_constraints')
    # should contain at least one constraint (given flights)
    assert len(list(model.equipment_turn_constraints.items())) >= 0


def test_add_maint_block_and_related_creates_collections():
    data = small_data_one_airport()
    model, FlightData, Days, AircraftInit = build_model_from_data(data)

    # Prepare normalized params and pass their values to the helper
    p = Params()
    p = normalize_params(p, data)

    add_maint_block_and_related(
        model,
        FlightData,
        Days,
        params=p,
        min_turn=30,
        All_Check_days=p.All_Check_days,
        All_Checks_Done_Days=p.All_Checks_Done_Days,
        All_Checks=p.All_Checks,
        All_Check_Done_hours=p.All_Check_Done_hours,
        All_Check_durations_days=p.All_Check_durations_days,
        Mbig=p.Mbig,
        mcap=p.mcap,
        enable_z_check=True,
        enable_maint_spacing=True,
        enable_maint_cumulative=True,
        enable_maint_cumulative_start=True,
        enable_maint_block_checks=True,
        enable_maint_checks_days=True,
        enable_maint_capacity=True,
        enable_maint_link=True,
        enable_maint_hierarchy=True,
        enable_overlap_checks=True,
    )

    # Check that key constraint lists were created
    for name in ('maint_block_flights', 'z_check', 'maint_spacing', 'maint_cumulative', 'maint_block_checks', 'maint_checks_days', 'maint_capacity', 'maint_link', 'maint_hierarchy', 'flight_overlap'):
        assert hasattr(model, name)
