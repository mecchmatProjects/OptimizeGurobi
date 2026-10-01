import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import step4_lp_lower_bounds as step4
from experiments import validate_lp_bounds


class Step4WorkflowTests(unittest.TestCase):
    def test_routing_infeasible_instance_is_skipped_and_next_instance_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_dir = root / 'instances'
            input_dir.mkdir()
            (input_dir / 'a_infeasible.json').write_text('{}')
            (input_dir / 'b_feasible.json').write_text('{}')
            output = root / 'bounds.csv'

            def fake_preflight(path, **_kwargs):
                return 'infeasible' if path.stem.startswith('a_') else 'optimal'

            def fake_lp(path, **_kwargs):
                return {
                    'instance': path.stem,
                    'n_var': 2,
                    'n_con': 1,
                    'z_vars': 0,
                    'status': 'optimal',
                    'lp_bound': 10.0,
                    'runtime_s': 0.01,
                }

            argv = [
                'step4_lp_lower_bounds.py',
                '--input-dir', str(input_dir),
                '--formulation', 'classical',
                '--output', str(output),
            ]
            with patch.object(sys, 'argv', argv), \
                    patch.object(step4, 'routing_feasibility_status', side_effect=fake_preflight), \
                    patch.object(step4, 'solve_lp_lower_bound', side_effect=fake_lp):
                step4.main()

            with output.open(newline='', encoding='utf-8') as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual([row['instance'] for row in rows], ['b_feasible'])
            self.assertEqual(rows[0]['routing_status'], 'optimal')

    def test_include_routing_infeasible_records_explicit_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_dir = root / 'instances'
            input_dir.mkdir()
            (input_dir / 'a_infeasible.json').write_text('{}')
            output = root / 'bounds.csv'

            fake_lp_result = {
                'instance': 'a_infeasible',
                'n_var': 2,
                'n_con': 1,
                'z_vars': 0,
                'status': 'infeasible',
                'lp_bound': None,
                'runtime_s': 0.01,
            }
            argv = [
                'step4_lp_lower_bounds.py',
                '--input-dir', str(input_dir),
                '--formulation', 'classical',
                '--include-routing-infeasible',
                '--output', str(output),
            ]
            with patch.object(sys, 'argv', argv), \
                    patch.object(step4, 'solve_lp_lower_bound', return_value=fake_lp_result):
                step4.main()

            with output.open(newline='', encoding='utf-8') as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row['routing_status'], 'included_without_preflight')

    def test_validator_accepts_small_rounding_excess(self):
        rows = [{
            'instance': 'ABCD_no_maint_test',
            'formulation': 'integrated',
            'status': 'optimal',
            'lp_bound': '14000.0000001',
        }]
        summary = step4.validate_lp_results(
            rows,
            reference={'ABCD_no_maint_test': 14000.0},
        )
        self.assertFalse(summary['violations'])
        self.assertEqual(summary['n_lower_bound_valid'], 1)

    def test_validator_returns_nonzero_for_missing_csv(self):
        status = validate_lp_bounds.main(['--csv', 'missing-step4-file.csv'])
        self.assertEqual(status, 2)


if __name__ == '__main__':
    unittest.main()
