"""Regression tests for event-model state bounds."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.event_model import EventMILPScheduler


class EventBoundTests(unittest.TestCase):
    def test_initial_hours_big_m_covers_overdue_history(self):
        self.assertEqual(
            EventMILPScheduler._initial_hours_big_m(800, 600, 120),
            920,
        )

    def test_initial_hours_big_m_uses_threshold_for_normal_history(self):
        self.assertEqual(
            EventMILPScheduler._initial_hours_big_m(400, 600, 120),
            720,
        )

    def test_route_hours_big_m_is_asymmetric_and_valid(self):
        self.assertEqual(
            EventMILPScheduler._route_hours_big_m(600, 120),
            (720, 480),
        )
        self.assertEqual(
            EventMILPScheduler._route_hours_big_m(600, 720),
            (1320, 0),
        )


if __name__ == "__main__":
    unittest.main()
