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

from src.model import (
    LegacyCorrectedMILPScheduler,
    LegacyCorrectedStrengthenedMILPScheduler,
    MILP_Sheduler,
)

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

        self.assertTrue(hasattr(strict, "c13_exact_state"))
        self.assertGreater(len(list(strict.c13_exact_state)), 0)
        self.assertFalse(hasattr(strict, "c13"))
        self.assertFalse(hasattr(strict, "c13b"))

    def test_strengthened_corrected_state_is_sparse_and_smaller(self):
        baseline_scheduler = LegacyCorrectedMILPScheduler(
            str(SOURCE), enabled_checks=["A"]
        )
        baseline = baseline_scheduler.build_model()
        strengthened_scheduler = LegacyCorrectedStrengthenedMILPScheduler(
            str(SOURCE), enabled_checks=["A"]
        )
        strengthened = strengthened_scheduler.build_model()

        self.assertEqual(len(strengthened.h), len(strengthened.P) * len(strengthened.D))
        sample = next(iter(strengthened.h.values()))
        self.assertEqual(sample.lb, 0.0)
        self.assertEqual(sample.ub, strengthened_scheduler.check_hrs["A"] * 60.0)
        self.assertLess(
            len(list(strengthened.c13_exact_state)),
            len(list(baseline.c13_exact_state)),
        )
        self.assertFalse(hasattr(strengthened, "c4_pairwise_overlap"))
        self.assertTrue(hasattr(strengthened, "c5_clique_overlap"))


if __name__ == "__main__":
    unittest.main()
