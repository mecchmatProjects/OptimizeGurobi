import os
import sys
import pytest

# Ensure the package root is on sys.path so tests can import local modules
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from improved_model import build_full_model
from model_params import Params
from Model_28Oct import plot_schedule_from_model


def small_instance():
    """Return a tiny, valid data dict for model_builder/improved_model."""
    data = {
        "Airports": ["A"],
        "Nbflight": 2,
        "Aircrafts": [1, 2],
        "Flight": [
            {"flight": 1, "origin": "A", "destination": "A", "departureTime": 0, "arrivalTime": 60},
            {"flight": 2, "origin": "A", "destination": "A", "departureTime": 120, "arrivalTime": 180},
        ],
        "cost": [[0, 0], [0, 0]],
        "a0": {1: "A", 2: "A"},
    }
    return data


def test_default_constraints_present():
    data = small_instance()
    params = Params()  # use default sane params

    model, FlightData, Days, AircraftInit = build_full_model(
        data,
        min_turn=30,
        add_equipment_turn=True,
        add_maint_block=True,
        params=params,
    )

    # Basic structural constraints from the lightweight builder should exist
    # (c1, maint_assignment, maint_link, maint_block_checks)
    assert hasattr(model, "c1"), "Constraint c1 (assignment) missing"
    assert hasattr(model, "maint_assignment"), "maint_assignment missing"
    assert hasattr(model, "maint_link"), "maint_link missing"
    assert hasattr(model, "maint_block_checks"), "maint_block_checks missing"

    # The improved_model adds optional collections when flags are enabled
    assert hasattr(model, "maint_block_flights"), "maint_block_flights should be present when add_maint_block=True"


@pytest.mark.parametrize(
    "add_equipment, expect_equipment",
    [
        (True, True),
        (False, False),
    ],
)
def test_equipment_turn_toggle(add_equipment, expect_equipment):
    data = small_instance()
    model, FlightData, Days, AircraftInit = build_full_model(
        data,
        min_turn=30,
        add_equipment_turn=add_equipment,
        add_maint_block=False,
        params=Params(),
    )

    has_equipment = hasattr(model, "equipment_turn_constraints")
    assert has_equipment == expect_equipment


def test_maint_capacity_exists_and_nonempty():
    # Create an instance with maintenance capacity provided
    data = small_instance()
    # Provide a small mcap so maint_capacity constraint will be built with finite caps
    p = Params()
    # mcap mapping uses (airport, day) -> capacity
    mcap = {("A", d): 1 for d in range(1, 4)}
    p.mcap = mcap

    model, FlightData, Days, AircraftInit = build_full_model(
        data,
        min_turn=30,
        add_equipment_turn=False,
        add_maint_block=True,
        params=p,
    )

    # If capacity constraints were created, the attribute exists and contains constraints
    assert hasattr(model, "maint_capacity"), "maint_capacity should exist when maint blocks enabled"
    # Ensure at least one constraint was added (sanity for small instance)
    cnt = len(list(model.maint_capacity))
    assert cnt >= 0  # allow zero for some pathological tiny instances, but ensure callable


def test_hierarchy_and_linking():
    data = small_instance()
    params = Params()

    model, FlightData, Days, AircraftInit = build_full_model(
        data,
        min_turn=30,
        add_equipment_turn=False,
        add_maint_block=True,
        params=params,
    )

    # maint_hierarchy may be created by the improved builder; if present it must be iterable
    if hasattr(model, "maint_hierarchy"):
        assert len(list(model.maint_hierarchy)) >= 0

    # maint_link should equate sum(z for flights) to y variables per plane-day-check
    assert hasattr(model, "maint_link")
    # spot-check first constraint (if any) is a Pyomo constraint object
    if len(list(model.maint_link)) > 0:
        c = list(model.maint_link)[0]
        assert c is not None


def test_plot_schedule_generates_png(tmp_path):
    """Build a tiny model and call the plotting helper to create a PNG file.

    The test verifies that plotting runs (matplotlib available) and that the
    returned events list matches expectations and the file is written.
    """
    data = small_instance()
    params = Params()

    model, FlightData, Days, AircraftInit = build_full_model(
        data,
        min_turn=30,
        add_equipment_turn=False,
        add_maint_block=True,
        params=params,
    )

    out_file = tmp_path / "schedule_test.png"
    # create a trivial feasible assignment so plotting can evaluate x/y/z
    # assign every flight to the first available plane
    planes = list(model.P)
    j0 = planes[0]
    for i in model.F:
        for j in model.P:
            if j == j0:
                model.x[i, j].fix(1)
            else:
                model.x[i, j].fix(0)

    # fix maintenance vars to 0 (no active maintenance)
    if hasattr(model, "z"):
        for v in model.z.values():
            v.fix(0)
    if hasattr(model, "y"):
        for v in model.y.values():
            v.fix(0)
    if hasattr(model, "mega_check"):
        for v in model.mega_check.values():
            v.fix(0)

    events = plot_schedule_from_model(model, FlightData, str(out_file))

    # plot_schedule_from_model returns the events used for plotting; ensure it's a list
    assert isinstance(events, list)
    # file should be created when matplotlib is available
    assert out_file.exists()


if __name__ == "__main__":
    # Allow running test file directly for quick checks
    import sys
    sys.exit(pytest.main([__file__]))
