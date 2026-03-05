from improved_model import build_full_model
from data_io import parse_airline_data
from pathlib import Path
import pytest


def find_test_dat(name="DataCplex_density=0.5_p=10_h=15_test_0.dat"):
    here = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = here / "TestsData" / "tests_d_0.5" / "d=0.5" / "p=10" / "h=15" / name
        if candidate.exists():
            return candidate
        here = here.parent
    root = Path(__file__).resolve().parents[3]
    found = list(root.rglob(name))
    if found:
        return found[0]
    pytest.skip(f"Test data file not found: {name}")


TEST_FILE = find_test_dat()


def test_equipment_turn_toggle():
    data = parse_airline_data(str(TEST_FILE))
    # With equipment turn
    model1, FlightData, Days, AircraftInit = build_full_model(data, add_equipment_turn=True, add_maint_block=False)
    assert hasattr(model1, 'equipment_turn_constraints')
    # Without equipment turn
    model2, FlightData, Days, AircraftInit = build_full_model(data, add_equipment_turn=False, add_maint_block=False)
    assert not hasattr(model2, 'equipment_turn_constraints')


def test_maint_block_toggle():
    data = parse_airline_data(str(TEST_FILE))
    # With maint block
    model1, FlightData, Days, AircraftInit = build_full_model(data, add_equipment_turn=False, add_maint_block=True)
    assert hasattr(model1, 'maint_block_flights')
    # Without maint block
    model2, FlightData, Days, AircraftInit = build_full_model(data, add_equipment_turn=False, add_maint_block=False)
    assert not hasattr(model2, 'maint_block_flights')
