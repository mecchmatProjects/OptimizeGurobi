"""Regression tests for event route-arc construction."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.event_model import EventMILPScheduler


INSTANCES = (
    ROOT / "data" / "instances" / "event_vs_legacy_clean_test.json",
    ROOT / "data" / "instances" / "ABCD_capacity_bottleneck_test.json",
    ROOT / "data" / "instances" / "DataCplex_density=0.5_p=10_h=21_test_0.json",
)


class EventRouteArcTests(unittest.TestCase):
    def test_indexed_builder_matches_reference_pair_scan(self):
        for instance in INSTANCES:
            scheduler = EventMILPScheduler(str(instance))
            optimized = set(scheduler._build_route_arcs())
            reference = set()
            for aircraft in scheduler.aircraft_ids:
                flights = scheduler._x_flights_for_aircraft(aircraft)
                for first in flights:
                    first_data = scheduler.flight_data[first]
                    for second in flights:
                        if first == second:
                            continue
                        second_data = scheduler.flight_data[second]
                        if (
                            first_data["destination"] == second_data["origin"]
                            and second_data["departureTime"]
                            >= first_data["arrivalTime"] + scheduler.MIN_TURN
                        ):
                            reference.add((first, second, aircraft))
            self.assertEqual(optimized, reference, str(instance))


if __name__ == "__main__":
    unittest.main()
