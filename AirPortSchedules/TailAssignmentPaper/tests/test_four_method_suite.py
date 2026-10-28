import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import run_four_method_suite
from experiments.run_four_method_suite import write_run_metadata
from experiments.report_uniform_study import audit_schedule
from experiments.refresh_cplex_study import audit_batch, digest, execution_lock, render_ten_seed, verify_input
from experiments.refresh_cplex_study import PRE_MIDNIGHT_FIX_SOURCES, repair_midnight_checkpoint
from src.validate_maintenance import _validate_ordered_event_windows


class FourMethodSuiteTests(unittest.TestCase):
    def test_midnight_checkpoint_migration_revalidates_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "case.json"
            source.write_text(json.dumps({
                "Aircrafts": [0], "AIRCRAFT_INIT_POS": {"0": "M"},
                "Flights": [[1, "M", "M", 10, 20]], "Cost_Matrix": [[100]],
                "Maintenance_Thresholds": {"A": 100},
                "Maintenance_Durations": {"A": 10}, "Station_Capacity": {"M": 1},
            }), encoding="utf-8")
            sources = {str(p.relative_to(ROOT)): digest(p.read_bytes())
                       for p in run_four_method_suite.PROVENANCE_SOURCES}
            sources.update(PRE_MIDNIGHT_FIX_SOURCES)
            violation = {"type": "maintenance_start_day_link", "flight": 1,
                         "aircraft": 0, "actual_start_day": 1, "selected_days": [2]}
            checkpoint = {
                "signature": {"sources": sources, "inputs": {str(source): digest(source.read_bytes())}},
                "rows": [{
                    "case": "case", "formulation": "uniform_flexible_day",
                    "has_solution": True, "status": "optimal", "replay_status": "fail",
                    "replay_error": "", "objective": 200,
                    "_schedule": {
                        "assignments": [[1, 0]], "violations": [violation],
                        "events": [{"flight": 1, "aircraft": 0, "check": "A",
                                    "start": 1439, "completion": 1449}],
                    },
                }],
            }
            path = Path(directory) / "case.checkpoint.json"
            path.write_text(json.dumps(checkpoint), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Real day-link defect"):
                repair_midnight_checkpoint(path)
            self.assertFalse(path.with_suffix(".pre_midnight_fix.json").exists())
            checkpoint["rows"][0]["_schedule"]["events"][0].update(
                start=1440 - 1e-9, completion=1450 - 1e-9)
            path.write_text(json.dumps(checkpoint), encoding="utf-8")
            original = path.read_bytes()
            repair_midnight_checkpoint(path)
            repaired = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(path.with_suffix(".pre_midnight_fix.json").read_bytes(), original)
            self.assertEqual(repaired["rows"][0]["replay_status"], "pass")
            self.assertEqual(repaired["migration"]["corrections"][0]["previous_violations"], [violation])
            self.assertEqual(repaired["migration"]["original_checkpoint_sha256"], digest(original))
            repair_midnight_checkpoint(path)

    def test_native_replay_classifies_midnight_with_absolute_tolerance(self):
        key = (1, 0, "A")
        model = SimpleNamespace(
            Z=[key], z={key: 1}, s={key: 0},
            X={(1, 0)}, x={(1, 0): 1}, F=[1],
            c_one_check_per_start_day=True,
            Z_START=[(1, 0, 2, "A")], start_day={(1, 0, 2, "A"): 1},
        )
        opt = SimpleNamespace(
            model=model, flight_data={1: {"arrivalTime": 20, "departureTime": 10,
                                         "destination": "M"}},
            check_dur={"A": 10}, MAX_MAINT_DEFER=1440,
            MAINTENANCE_TIME_GRID=1, MIN_TURN=30, DAY_SHIFT=1440,
            FIXED_NIGHT_START=False, maint_airports=["M"], station_cap={"M": 1},
        )
        for start in (1440 - 1e-9, 1440, 1440 + 1e-9):
            with self.subTest(start=start):
                model.s[key] = start + 10 - 20
                self.assertEqual(_validate_ordered_event_windows(opt, 1e-6), [])
        for start in (1439, 1440 - 1e-3):
            with self.subTest(start=start):
                model.s[key] = start + 10 - 20
                violations = _validate_ordered_event_windows(opt, 1e-6)
                self.assertIn("maintenance_start_day_link", {v["type"] for v in violations})

    def test_saved_decision_replay_does_not_hide_duplicate_checks_at_midnight(self):
        data = {
            "Aircrafts": [0], "AIRCRAFT_INIT_POS": {"0": "M"},
            "Flights": [[1, "M", "M", 10, 20], [2, "M", "M", 1500, 1510]],
            "Cost_Matrix": [[100], [100]], "Maintenance_Thresholds": {"A": 100},
            "Maintenance_Durations": {"A": 10}, "Station_Capacity": {"M": 1},
        }
        schedule = {
            "assignments": [[1, 0], [2, 0]],
            "events": [
                {"flight": 1, "aircraft": 0, "check": "A",
                 "start": 1440 - 1e-9, "completion": 1450 - 1e-9},
                {"flight": 2, "aircraft": 0, "check": "A",
                 "start": 1520, "completion": 1530},
            ],
        }
        policy = {"time_grid_minutes": 1, "maximum_start_deferral_minutes": 1440,
                  "night_start_minute": None}
        self.assertEqual(audit_schedule(data, schedule, policy, 400),
                         ["multiple checks per actual start day"])
        schedule["events"][0].update(start=1439, completion=1449)
        self.assertEqual(audit_schedule(data, schedule, policy, 400), [])

    def test_checkpoint_resumes_after_interrupt_without_repeating_completed_solve(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "case.json"
            source.write_text("{}", encoding="utf-8")
            checkpoint = Path(directory) / "checkpoint.json"
            methods = ["uniform_flexible_day", "uniform_flexible_event"]
            def result(method):
                return {
                    "case": "case", "formulation": method, "status": "optimal",
                    "has_solution": True, "replay_status": "pass", "replay_error": "",
                    "_schedule": {"assignments": [[1, 0]], "events": []},
                }
            args = ([source], methods, "cplex", None, 30, "presolve_on",
                    False, 1, None, False, "12.9.0.0", checkpoint)
            with patch.object(run_four_method_suite, "run_case",
                              side_effect=[result(methods[0]), KeyboardInterrupt]):
                with self.assertRaises(KeyboardInterrupt):
                    run_four_method_suite.checkpointed_cases(*args)
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["rows"]), 1)
            self.assertIn("_schedule", saved["rows"][0])
            saved["migration"] = {"reason": "preserved audit evidence"}
            checkpoint.write_text(json.dumps(saved), encoding="utf-8")
            with patch.object(run_four_method_suite, "run_case",
                              return_value=result(methods[1])) as solve:
                rows = run_four_method_suite.checkpointed_cases(*args)
                self.assertEqual(solve.call_count, 1)
                self.assertEqual(solve.call_args.args[1], methods[1])
            self.assertEqual(len(rows), 2)
            self.assertEqual(json.loads(checkpoint.read_text())["migration"], saved["migration"])
            with patch.object(run_four_method_suite, "run_case") as solve:
                self.assertEqual(len(run_four_method_suite.checkpointed_cases(*args)), 2)
                solve.assert_not_called()
            source.write_text('{"changed": true}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "inputs/code/settings changed"):
                run_four_method_suite.checkpointed_cases(*args)

    def test_execution_lock_releases_on_interrupt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.lock"
            with self.assertRaises(KeyboardInterrupt):
                with execution_lock(path):
                    with self.assertRaisesRegex(RuntimeError, "Another CPLEX refresh"):
                        with execution_lock(path):
                            self.fail("Concurrent runner acquired the lock")
                    raise KeyboardInterrupt
            with execution_lock(path):
                pass

    def test_refresh_audits_no_incumbent_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            folder = Path(directory)
            source = folder / "case.json"
            source.write_text(json.dumps({
                "Aircrafts": [0], "Flights": [[1, "M", "M", 0, 60]],
                "Maintenance_Families": ["A"],
            }), encoding="utf-8")
            output = folder / "run.csv"
            row = {
                "case": "case", "formulation": "uniform_flexible_day",
                "status": "maxTimeLimit", "has_solution": "False",
                "error": "", "replay_error": "", "lp_relaxation": "False",
            }
            with output.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            output.with_suffix(".schedules.json").write_text("[]", encoding="utf-8")
            executable = Path("cplex.exe")
            metadata = write_run_metadata(
                output, [source], "cplex", str(executable), "12.9.0.0",
                1, 180, "presolve_on", False, None, False,
                ["uniform_flexible_day"], False,
            )
            original = json.loads(metadata.read_text(encoding="utf-8"))["runs"][-1]
            rows = audit_batch(output, original, executable, "12.9.0.0")
            self.assertEqual(rows[0]["status"], "maxTimeLimit")
            self.assertEqual(rows[0]["has_solution"], "False")
            output.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact hash mismatch"):
                audit_batch(output, original, executable, "12.9.0.0")

    def test_refresh_accepts_only_archived_bytes_or_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_bytes(b'{\n  "value": 1\n}\n')
            self.assertEqual(verify_input(path, digest(path.read_bytes())), "exact")
            expected = digest(path.read_bytes().replace(b"\n", b"\r\n"))
            self.assertEqual(verify_input(path, expected), "line_endings_only")
            path.write_bytes(b'{\n  "value": 2\n}\n')
            with self.assertRaisesRegex(ValueError, "Scientific input differs"):
                verify_input(path, expected)

    def test_presolve_off_reaches_both_cplex_interfaces(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.json"
            path.write_text(json.dumps({
                "Aircrafts": [0], "Flights": [[1, "M", "M", 0, 60]],
            }), encoding="utf-8")
            for backend in ("cplex", "cplexamp"):
                with self.subTest(backend=backend):
                    scheduler = Mock()
                    scheduler.solve.return_value = {"status": "infeasible", "has_solution": False}
                    with patch.dict(run_four_method_suite.FORMULATIONS, {"test": Mock(return_value=scheduler)}), \
                         patch.object(run_four_method_suite, "model_size", return_value=(1, 1)):
                        row = run_four_method_suite.run_case(
                            path, "test", backend, "cplex.exe", 30,
                            "presolve_off", False, 1, None, False,
                        )
                    self.assertEqual(row["status"], "infeasible")
                    self.assertEqual(scheduler.solve.call_args.kwargs["solver_options"], {
                        "threads": 1, "preprocessing presolve": 0,
                    })

    def test_ten_seed_report_counts_only_jointly_optimal_pairs(self):
        rows = [
            {"case": "a", "P": "5", "H": "30", "formulation": "uniform_flexible_day",
             "status": "optimal", "objective": "100", "wall_s": "1"},
            {"case": "a", "P": "5", "H": "30", "formulation": "uniform_flexible_event",
             "status": "maxTimeLimit", "objective": "101", "wall_s": "180"},
        ]
        text = render_ten_seed(rows, "test", "12.9.0.0")
        self.assertIn("5 & 30 & 1/10 & -- & 0/10 & -- & 0/10", text)
        self.assertIn("raw CSV is absent", text)
        rows[1].update(status="optimal")
        with self.assertRaisesRegex(ValueError, "objective mismatch"):
            render_ten_seed(rows, "test", "12.9.0.0")

    def test_saved_schedule_audit_rejects_cost_and_timing_tampering(self):
        data = {
            "Aircrafts": [0], "AIRCRAFT_INIT_POS": {"0": "M"},
            "Flights": [[1, "M", "M", 10, 20]], "Cost_Matrix": [[100]],
            "Maintenance_Thresholds": {"A": 15},
            "Maintenance_Durations": {"A": 10}, "Station_Capacity": {"M": 1},
        }
        policy = {
            "time_grid_minutes": 1, "maximum_start_deferral_minutes": 1440,
            "night_start_minute": None,
        }
        schedule = {
            "assignments": [[1, 0]],
            "events": [{"flight": 1, "aircraft": 0, "check": "A", "start": 20, "completion": 30}],
        }
        self.assertEqual(audit_schedule(data, schedule, policy, 200), [])
        self.assertIn("objective reconstruction", audit_schedule(data, schedule, policy, 100))
        schedule["events"][0].update(start=15, completion=25)
        self.assertIn("maintenance deferral", audit_schedule(data, schedule, policy, 200))
        schedule["events"][0].update(start=20, completion=30)
        schedule["events"].append(dict(schedule["events"][0]))
        problems = audit_schedule(data, schedule, policy, 300)
        self.assertIn("multiple checks per actual start day", problems)
        self.assertIn("maintenance bay capacity", problems)

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
            self.assertIn("src\\validate_maintenance.py", run["sources"])
            self.assertTrue(output_path.with_suffix(".sources.zip").is_file())
            self.assertIsNone(run["configuration"]["legacy_max_hour_check_deferral_days"])
            self.assertEqual(
                run["result_csv_sha256"],
                hashlib.sha256(output_path.read_bytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()