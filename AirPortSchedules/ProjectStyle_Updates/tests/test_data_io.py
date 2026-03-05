import os
from pathlib import Path

import pytest

from data_io import parse_airline_data
import pytest


def find_test_dat(name="DataCplex_density=0.5_p=10_h=15_test_0.dat"):
    here = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = here / "TestsData" / "tests_d_0.5" / "d=0.5" / "p=10" / "h=15" / name
        if candidate.exists():
            return candidate
        here = here.parent
    # fallback: wide search from repository root
    root = Path(__file__).resolve().parents[3]
    found = list(root.rglob(name))
    if found:
        return found[0]
    pytest.skip(f"Test data file not found: {name}")


TEST_FILE = find_test_dat()


def test_parse_airline_data_basic_fields():
    assert TEST_FILE.exists(), f"Test data file not found: {TEST_FILE}"

    data = parse_airline_data(str(TEST_FILE))

    # Basic fields
    assert "Airports" in data
    assert "Nbflight" in data
    assert "Flights" in data
    assert "Flight" in data
    assert "Aircrafts" in data
    assert "cost" in data
    assert "a0" in data

    # Check sizes and simple content expectations
    assert data["Nbflight"] == 140
    assert len(data["Flights"]) == 140
    assert len(data["Flight"]) == 140

    # First flight sanity check
    first = data["Flight"][0]
    assert first["flight"] == 1
    assert first["origin"] == "K"
    assert first["destination"] == "B"
    assert abs(first["departureTime"] - 6310.0) < 1e-6
    assert abs(first["arrivalTime"] - 6470.0) < 1e-6

    # Aircraft initial positions
    a0 = data["a0"]
    # Expect keys for 0..9
    for k in range(10):
        assert k in a0

    # cost matrix: ensure non-empty and each row has 10 columns (10 aircrafts)
    cost = data["cost"]
    assert len(cost) > 0
    assert all(len(row) == 10 for row in cost)


if __name__ == "__main__":
    pytest.main([str(TEST_FILE)])
