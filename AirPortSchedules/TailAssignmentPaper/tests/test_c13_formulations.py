"""Tests for the C13 formulation toggles ported from the thesis_version branch.

Covers the paper-vs-split selector (``use_paper_c13``) and the interval-tight
big-M option (``use_tight_c13_m``) merged into ``src/model.py``.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model import MILP_Sheduler

SOURCE = ROOT / "data" / "instances" / "ABCD_near_threshold_test.json"


class C13FormulationTests(unittest.TestCase):
    def test_tight_c13_m_is_opt_in_and_interval_bounded(self):
        scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
        baseline = scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_tight_c13_m=False,
        )
        tight_scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
        tight = tight_scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_tight_c13_m=True,
        )

        self.assertEqual(len(list(baseline.c13)), len(list(tight.c13)))
        self.assertGreaterEqual(tight_scheduler._c13_big_m("A", 0, 1, 3), 0)
        self.assertIn("9999999", str(next(iter(baseline.c13.values())).expr))
        self.assertNotIn("9999999", str(next(iter(tight.c13.values())).expr))

    def test_paper_c13_is_opt_in_and_keeps_row_count(self):
        scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
        split = scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_paper_c13=False,
        )
        paper_scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
        paper = paper_scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_paper_c13=True,
        )

        # Split builds two rows per window; paper builds one.
        self.assertEqual(len(list(paper.c13)) * 2, len(list(split.c13)))

    def test_strict_hour_state_removes_endpoint_relaxation(self):
        scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
        strict = scheduler.build_model(
            allow_ferry=False,
            use_overlap=False,
            use_strict_hour_state=True,
        )

        c13_text = "\n".join(str(row.expr) for row in strict.c13.values())
        c13b_text = "\n".join(str(row.expr) for row in strict.c13b.values())
        self.assertIn("mega", c13_text)
        self.assertIn("mega", c13b_text)
        self.assertTrue(list(strict.c13))
        self.assertTrue(list(strict.c13b))


if __name__ == "__main__":
    unittest.main()
