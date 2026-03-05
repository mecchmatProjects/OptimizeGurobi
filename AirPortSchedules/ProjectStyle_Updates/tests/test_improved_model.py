from pathlib import Path

from data_io import parse_airline_data
from improved_model import build_full_model
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


def test_build_full_model_constraints_present():
    assert TEST_FILE.exists(), f"Test data file not found: {TEST_FILE}"

    data = parse_airline_data(str(TEST_FILE))

    model, FlightData, Days, AircraftInit = build_full_model(data)

    # Core structures added by improved_model
    assert hasattr(model, 'equipment_turn_constraints')
    assert hasattr(model, 'maint_block_flights')

    # They should contain some constraints for this dataset
    assert len(list(model.equipment_turn_constraints)) > 0
    assert len(list(model.maint_block_flights)) > 0


if __name__ == "__main__":
    import pytest

    pytest.main([str(TEST_FILE)])
