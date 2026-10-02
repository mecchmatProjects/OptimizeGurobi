import argparse
import csv
import json
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
from src.solver_utils import (parse_deferral_days, apply_time_limit, extract_bounds,
                              solve_and_load, relax_integrality)
from src.experiment_utils import ExperimentCSV
from types import SimpleNamespace


class Step4WorkflowTests(unittest.TestCase):
    def test_real_routing_lp_infeasibility_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = json.loads((ROOT / 'data/instances/ABCD_no_maint_test.json').read_text())
            data['AIRCRAFT_INIT_POS'] = {str(aid): 'ISOLATED' for aid in data['Aircrafts']}
            path = Path(temporary) / 'unreachable.json'
            path.write_text(json.dumps(data))
            status = step4.routing_feasibility_status(path, solver_name='highs', time_limit=5)
            self.assertEqual(status, 'infeasible')

    def test_unknown_and_error_preflights_retain_instances(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('first.json', 'second.json'):
                (root / name).write_text('{}')
            output = root / 'bounds.csv'
            def fake_lp(path, **_kwargs):
                return {'instance': path.stem, 'status': 'optimal', 'lp_bound': 10, 'wall_s': 0.01}
            with patch.object(step4, 'routing_feasibility_status',
                              side_effect=['maxTimeLimit', RuntimeError('test failure')]), \
                    patch.object(step4, 'solve_lp_lower_bound', side_effect=fake_lp) as solve:
                step4.main(['--input-dir', str(root), '--formulation', 'integrated',
                            '--routing-preflight', '--output', str(output)])
            self.assertEqual(solve.call_count, 2)
            with output.open(newline='') as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row['routing_status'] for row in rows], ['maxTimeLimit', 'error'])

    def test_no_solution_plot_is_suppressed_and_solver_called_once(self):
        from model import MILP_Sheduler
        from pyomo.environ import ConcreteModel, Var, Objective
        scheduler = MILP_Sheduler.__new__(MILP_Sheduler)
        scheduler.model = ConcreteModel()
        scheduler.model.assignment = Var()
        scheduler.model.obj = Objective(expr=scheduler.model.assignment)
        result = SimpleNamespace(termination_condition='maxTimeLimit')
        solver = SimpleNamespace(options={})
        with patch.object(solver, 'solve', create=True, return_value=result) as solve, \
                patch('model.SolverFactory', return_value=solver), \
                patch('model._plot_gantt') as plot:
            summary = scheduler.solve(solver_name='highs', time_limit=5)
            scheduler.plot_gantt(show=False)
        self.assertFalse(summary['solution_loaded'])
        self.assertIsNone(summary['obj'])
        solve.assert_called_once()
        plot.assert_not_called()

    def test_validator_rejects_nonfinite_and_incompatible_reference(self):
        row = {'instance': 'test', 'status': 'optimal', 'lp_bound': 'nan'}
        self.assertTrue(step4.validate_lp_results([row])['violations'])
        row.update(lp_bound='100', max_deferral_days='3', restrictive_deferral='True')
        summary = step4.validate_lp_results([row], reference={
            'test': {'objective': 50, 'config': {'max_deferral_days': None}}})
        self.assertFalse(summary['violations'])
        self.assertEqual(summary['uncompared'], 1)

    def test_default_cap_and_explicit_none_have_different_domains(self):
        from model import MILP_Sheduler
        source = ROOT / 'data/feasible_family_smoke/A/DataCplex_density=0.5_p=4_h=7_test_0.json'
        capped = MILP_Sheduler(source)
        uncapped = MILP_Sheduler(source, max_hour_check_deferral_days=None)
        self.assertEqual(capped.max_hour_check_deferral_days, 3)
        self.assertIsNone(uncapped.max_hour_check_deferral_days)
        self.assertGreater(sum(map(len, uncapped.z_days_by_flight_check.values())),
                           sum(map(len, capped.z_days_by_flight_check.values())))
        self.assertEqual(step4.parse_args([]).max_hour_check_deferral_days, 3)
        self.assertIsNone(step4.parse_args(['--max-hour-check-deferral-days', 'none']).max_hour_check_deferral_days)

    def test_relaxation_preserves_continuous_bounds_and_fractional_routing(self):
        from pyomo.environ import ConcreteModel, Var, Binary, NonNegativeReals, Objective, Constraint, SolverFactory
        model = ConcreteModel()
        model.assignment = Var(domain=Binary)
        model.hours = Var(domain=NonNegativeReals, bounds=(0, 1000))
        model.fractional = Constraint(expr=2 * model.assignment == 1)
        model.obj = Objective(expr=model.assignment)
        relax_integrality(model)
        self.assertEqual(model.hours.ub, 1000)
        scheduler = SimpleNamespace(model=model, flight_ids=[1], aircraft_ids=[1], days=[1],
                                    z_var_count=0, build_model=lambda **_kw: model)
        with patch('src.model.MILP_Sheduler', return_value=scheduler):
            self.assertEqual(step4.routing_feasibility_status(ROOT / 'AGENTS.md', solver_name='highs'), 'optimal')
        self.assertTrue(SolverFactory('highs').available())

    def test_no_incumbent_is_not_loaded_or_resolved(self):
        solver = SimpleNamespace()
        with patch.object(solver, 'solve', create=True,
                          return_value=SimpleNamespace(termination_condition='maxTimeLimit')) as solve:
            _result, loaded, objective = solve_and_load(solver, SimpleNamespace())
        self.assertFalse(loaded)
        self.assertIsNone(objective)
        solve.assert_called_once()

    def test_time_limited_loader_and_zero_objective(self):
        from pyomo.environ import ConcreteModel, Var, Objective
        model = ConcreteModel()
        model.assigned = Var(initialize=0)
        model.obj = Objective(expr=model.assigned)
        loader = SimpleNamespace(load_vars=lambda: model.assigned.set_value(2))
        result = SimpleNamespace(termination_condition='maxTimeLimit',
                                 incumbent_objective=2, objective_bound=1, solution_loader=loader)
        solver = SimpleNamespace(solve=lambda *_args, **_kwargs: result)
        _result, loaded, objective = solve_and_load(solver, model)
        self.assertTrue(loaded)
        self.assertEqual(objective, 2)

    def test_resume_rejects_config_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'bounds.csv'
            with ExperimentCSV(path, ['instance'], {'cap': 3}) as output:
                output.write({'instance': 'test'})
            with ExperimentCSV(path, ['instance'], {'cap': 3}, resume=True) as output:
                self.assertEqual(len(output.previous), 1)
            with self.assertRaises(ValueError):
                ExperimentCSV(path, ['instance'], {'cap': None}, resume=True)

    def test_deferral_none_and_numeric_limits(self):
        self.assertIsNone(parse_deferral_days('none'))
        self.assertIsNone(parse_deferral_days(None))
        self.assertEqual(parse_deferral_days(3), 3)
        self.assertEqual(parse_deferral_days('0'), 0)
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_deferral_days('-1')

    def test_backend_budgets_and_zero_gap(self):
        for name, key in [('cplexamp', 'timelimit'), ('highs', 'time_limit'),
                          ('gurobi', 'TimeLimit'), ('glpk', 'tmlim')]:
            solver = SimpleNamespace(options={})
            apply_time_limit(solver, name, 5)
            self.assertEqual(solver.options[key], 5)
        result = SimpleNamespace(problem=SimpleNamespace(lower_bound=0, upper_bound=0))
        self.assertEqual(extract_bounds(result)[:3], (0, 0, 0))

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
                '--routing-preflight',
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
