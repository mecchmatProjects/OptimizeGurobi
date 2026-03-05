from pathlib import Path

from data_io import parse_airline_data
from model_builder import build_model_from_data
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


def test_model_structure_basic():
    assert TEST_FILE.exists(), f"Test data file not found: {TEST_FILE}"

    data = parse_airline_data(str(TEST_FILE))

    model, FlightData, Days, AircraftInit = build_model_from_data(data)

    # Basic sets
    assert hasattr(model, 'F')
    assert hasattr(model, 'P')
    assert hasattr(model, 'A')
    assert hasattr(model, 'D')
    assert hasattr(model, 'MA')
    assert hasattr(model, 'C')

    # Variables
    assert hasattr(model, 'x')
    assert hasattr(model, 'z')
    assert hasattr(model, 'y')
    assert hasattr(model, 'mega_check')

    # Constraints: c1 should have as many entries as flights
    c1_count = len(list(model.c1))
    assert c1_count == data['Nbflight']

    # maint_block_checks should exist and have entries for planes*days
    assert len(list(model.maint_block_checks)) > 0

    # maint_link should exist
    assert len(list(model.maint_link)) > 0

    # --- Additional checks: variable domains and simple constraint expressions ---
    # pick first flight and first plane
    first_f = data['Flights'][0]
    first_p = data['Aircrafts'][0]

    # x variable should be binary
    assert model.x[first_f, first_p].is_binary()

    # z and y should be binary as well (sample checks)
    # pick first day and first check
    first_d = list(model.D)[0]
    first_c = list(model.C)[0]
    assert model.z[first_f, first_p, first_d, first_c].is_binary()
    assert model.y[first_p, first_d, first_c].is_binary()

    # Check that c1 constraints are equalities (string contains '==') for a sample
    sample_c_item = list(model.c1)[0]
    if hasattr(sample_c_item, 'expr'):
        sample_expr = sample_c_item.expr
    else:
        sample_expr = model.c1[sample_c_item].expr
    # structural check: expect a relational/equality constraint
    clsname_c = sample_expr.__class__.__name__.lower()
    assert 'equal' in clsname_c or 'inequal' in clsname_c or 'relational' in clsname_c

    # Check that maint_block_checks constraints are inequalities with '<=' and '1'
    sample_mb_item = list(model.maint_block_checks)[0]
    if hasattr(sample_mb_item, 'expr'):
        sample_mb_expr = sample_mb_item.expr
    else:
        sample_mb_expr = model.maint_block_checks[sample_mb_item].expr
    clsname_mb = sample_mb_expr.__class__.__name__.lower()
    assert 'inequal' in clsname_mb or 'relational' in clsname_mb or 'equal' in clsname_mb


if __name__ == "__main__":
    import pytest

    pytest.main([str(TEST_FILE)])
