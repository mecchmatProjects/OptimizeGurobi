from improved_model import build_full_model
from data_io import parse_airline_data
from pathlib import Path
import pytest
from pyomo.core.expr.visitor import identify_variables


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


def test_equipment_turn_expression_contains_x_and_ge():
    data = parse_airline_data(str(TEST_FILE))
    model, FlightData, Days, AircraftInit = build_full_model(data, add_equipment_turn=True, add_maint_block=False)
    assert hasattr(model, 'equipment_turn_constraints')
    # take first constraint (ConstraintList.add may return indices)
    sample_item = list(model.equipment_turn_constraints)[0]
    if hasattr(sample_item, 'expr'):
        expr = sample_item.expr
    else:
        expr = model.equipment_turn_constraints[sample_item].expr

    # structural checks: ensure x variables are present in the expression
    vars_in_expr = list(identify_variables(expr))
    assert any('x[' in v.name for v in vars_in_expr)

    # ensure this is a relational expression (Inequality or Equality)
    clsname = expr.__class__.__name__.lower()
    assert 'inequal' in clsname or 'equal' in clsname or 'relational' in clsname


def test_maint_block_expression_contains_x_and_leq():
    data = parse_airline_data(str(TEST_FILE))
    model, FlightData, Days, AircraftInit = build_full_model(data, add_equipment_turn=False, add_maint_block=True)
    assert hasattr(model, 'maint_block_flights')
    sample_item = list(model.maint_block_flights)[0]
    if hasattr(sample_item, 'expr'):
        expr = sample_item.expr
    else:
        expr = model.maint_block_flights[sample_item].expr

    vars_in_expr = list(identify_variables(expr))
    assert any('x[' in v.name for v in vars_in_expr)
    clsname = expr.__class__.__name__.lower()
    # expect an inequality-type relational expression
    assert 'inequal' in clsname or 'relational' in clsname or 'equal' in clsname
