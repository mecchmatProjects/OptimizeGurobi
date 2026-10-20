import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import run_four_method_suite
from experiments.run_four_method_suite import write_run_metadata


class FourMethodSuiteTests(unittest.TestCase):
    def test_replicate_generation_is_reproducible_by_index(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            suite_dir = Path(temp_dir) / "replicate_suite"
            with patch.object(run_four_method_suite, "SUITE_DIR", suite_dir):
                run_four_method_suite.generate_suite(
                    [(3, 7)],
                    flights_per_aircraft=2,
                    spread_rotations=True,
                    replicate_indices=[0, 1],
                )
                first_run = {
                    path.name: path.read_bytes()
                    for path in suite_dir.glob("perf_*.json")
                }
                manifest = json.loads(
                    (suite_dir / "manifest.json").read_text(encoding="utf-8")
                )

                run_four_method_suite.generate_suite(
                    [(3, 7)],
                    flights_per_aircraft=2,
                    spread_rotations=True,
                    replicate_indices=[0, 1],
                )
                second_run = {
                    path.name: path.read_bytes()
                    for path in suite_dir.glob("perf_*.json")
                }

            self.assertEqual(set(first_run), {"perf_p=3_h=7_r=0.json", "perf_p=3_h=7_r=1.json"})
            self.assertEqual(first_run, second_run)
            self.assertEqual(manifest["replicate_indices"], [0, 1])
            self.assertEqual(
                [case["replicate_index"] for case in manifest["performance_grid"]],
                [0, 1],
            )

    def test_run_metadata_records_a_only_profile_and_hashes(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "case.json"
            input_path.write_text(
                json.dumps({
                    "Aircrafts": [4],
                    "Flights": [[1, "A", "M", 0, 1440]],
                    "Maintenance_Families": ["A"],
                }),
                encoding="utf-8",
            )
            output_path = temp_path / "results.csv"
            output_path.write_text("case,status\ncase,optimal\n", encoding="utf-8")

            metadata_path = write_run_metadata(
                output=output_path,
                input_paths=[input_path],
                solver="cplexamp",
                executable="CPLEXamp.exe",
                solver_version="12.9.0",
                threads=1,
                time_limit=60,
                configuration="presolve_on",
                warm_start=False,
                legacy_deferral_days=None,
                lp_relaxation=False,
                formulations=["event_based_optimized"],
                append=False,
            )

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            run = metadata["runs"][0]
            input_record = run["inputs"][str(input_path.relative_to(ROOT))]
            self.assertEqual(input_record["sha256"], hashlib.sha256(input_path.read_bytes()).hexdigest())
            self.assertEqual(input_record["P"], 1)
            self.assertEqual(input_record["observed_H"], 2)
            self.assertEqual(input_record["F"], 1)
            self.assertEqual(input_record["declared_maintenance_families"], ["A"])
            self.assertEqual(input_record["effective_enabled_checks"], ["A"])
            self.assertEqual(run["configuration"]["solver_version"], "12.9.0")
            self.assertEqual(run["configuration"]["threads"], 1)
            self.assertIsNone(run["configuration"]["legacy_max_hour_check_deferral_days"])
            self.assertEqual(
                run["result_csv_sha256"],
                hashlib.sha256(output_path.read_bytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()