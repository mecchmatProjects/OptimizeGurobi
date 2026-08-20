import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import run_batch


class BatchRunnerTests(unittest.TestCase):
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
