import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import run_batch
from src.generate_feasible_instances import build_feasible_instance


class BatchRunnerTests(unittest.TestCase):
    def test_spread_rotations_generate_longer_a_only_schedule(self):
        data = build_feasible_instance(
            density=1.0,
            p=3,
            h=15,
            index=0,
            flights_per_aircraft=4,
            maintenance_families="A",
            spread_rotations=True,
        )

        self.assertEqual(data["Maintenance_Families"], ["A"])
        self.assertEqual(len(data["Flights"]), 24)
        self.assertTrue(all(len(rotation) == 8 for rotation in data["_SeededRotation"].values()))
        self.assertGreater(max(float(flight[4]) for flight in data["Flights"]), 14 * 1440)

    def test_solver_limit_status_is_detected(self):
        result = run_batch._classify_result(
            returncode=1,
            stdout='',
            stderr='CPLEX Error 1016: Community Edition. Problem size limits exceeded.',
        )
        self.assertEqual(result['status'], 'solver_limit')
        self.assertIn('size limits exceeded', result['error'])

    def test_generic_failure_stays_error(self):
        result = run_batch._classify_result(
            returncode=1,
            stdout='',
            stderr='some unexpected solver failure',
        )
        self.assertEqual(result['status'], 'ERROR')


if __name__ == '__main__':
    unittest.main()
