from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

THIS_FILE = Path(__file__).resolve()
PKG_ROOT = THIS_FILE.parents[1]
REPO_ROOT = THIS_FILE.parents[2]
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tap_bench.benchmark.runner import BenchmarkRunner
from tap_bench.contracts.method import MethodConfig, MethodRegistry
from tap_bench.criteria.score import CriteriaProfile
from tap_bench.io.instance_loader import InstanceLoader
from tap_bench.methods import DynamicProgrammingExactSmallMethod, GreedyBaselineMethodAdapter


class SmokeTests(unittest.TestCase):
    def test_smoke_greedy_and_dp(self) -> None:
        instance = InstanceLoader.load(
            "data/instances/DataCplex_density=0.5_p=10_h=7_test_0.json"
        )

        registry = MethodRegistry()
        registry.register(GreedyBaselineMethodAdapter())
        registry.register(DynamicProgrammingExactSmallMethod())

        runner = BenchmarkRunner(
            registry=registry,
            config=MethodConfig(time_limit_s=30),
            profile=CriteriaProfile(),
        )

        records = runner.run([instance], ["greedy_baseline", "dp_exact_small"])
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].instance_stem, instance.stem)

        with tempfile.TemporaryDirectory() as tmp:
            out_csv = Path(tmp) / "smoke.csv"
            legacy_csv = Path(tmp) / "smoke_legacy.csv"
            runner.write_csv(records, str(out_csv))
            runner.write_legacy_csv(records, str(legacy_csv))

            self.assertTrue(out_csv.exists())
            self.assertTrue(legacy_csv.exists())


if __name__ == "__main__":
    unittest.main()
