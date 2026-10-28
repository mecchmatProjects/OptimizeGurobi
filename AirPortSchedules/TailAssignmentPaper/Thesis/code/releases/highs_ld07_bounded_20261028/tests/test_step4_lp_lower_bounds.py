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
    def test_partial_classical_table_keeps_timeout_and_missing_case(self):
        from experiments import run_khaled_30day as classical
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'classical.csv'
            row = dict(instance='md30_case', aircraft=20, flights=840,
                       variables=16800, constraints=17640, formulation='classical_none_overlap',
                       status='maxTimeLimit', primal_bound=100, dual_bound=99,
                       relative_gap_pct=1, wall_s=10001)
            with source.open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            source.with_suffix('.metadata.json').write_text(json.dumps({
                'config': {'instances': ['md30_case', 'ld30_case'], 'time_limit': 10000}}))
            output = root / 'table.tex'
            classical.write_latex_table(source, output)
            text = output.read_text()
            self.assertIn('1 saved records out of 2 planned', text)
            self.assertIn('time limit', text)
            self.assertNotIn('ld30 &', text)
            row['relative_gap_pct'] = 2
            with source.open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            with self.assertRaises(ValueError):
                classical.write_latex_table(source, output)

    def test_thesis_table_does_not_certify_unknown_lp_bound(self):
        from experiments import step4_analyze_bounds as analyzer
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'bounds.csv'
            fields = ['instance', 'status', 'lp_bound', 'n_var', 'n_con', 'z_vars',
                      'build_s', 'runtime_s', 'wall_s']
            with source.open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow(dict(instance='test', status='unknown', lp_bound=999999,
                                     n_var=2, n_con=1, z_vars=0, build_s=1, runtime_s=2, wall_s=3))
            source.with_suffix('.metadata.json').write_text(json.dumps({
                'config': {'formulation': 'integrated', 'solver': 'cplex'},
                'solver_version': '12.9'}))
            analyzer.emit_thesis_evidence([f'Unresolved={source}'], root / 'summary.csv',
                                          root / 'tables', root / 'figures')
            text = (root / 'tables/validated_lp_1.tex').read_text()
            self.assertNotIn('999,999', text)
            self.assertIn('unknown', text)
            self.assertIn('tab:step4_long_family_lp', text)

    def test_cplex_lp_algorithm_controls_are_explicit(self):
        from src.solver_utils import apply_cplex_lp_method
        solver = SimpleNamespace(options={})
        apply_cplex_lp_method(solver, 'cplex')
        self.assertEqual(solver.options, {})
        apply_cplex_lp_method(solver, 'cplex', 'barrier', True)
        self.assertEqual(solver.options['lpmethod'], 4)
        self.assertEqual(solver.options['barrier crossover'], -1)
        with self.assertRaises(ValueError):
            apply_cplex_lp_method(solver, 'highs', 'barrier')
        with self.assertRaises(SystemExit):
            step4.parse_args(['--barrier-no-crossover', '--lp-method', 'dual'])

    def test_cplex_automatic_threads_preserves_original_default_policy(self):
        from src.solver_utils import apply_threads
        solver = SimpleNamespace(options={})
        apply_threads(solver, 'cplex', 0)
        self.assertEqual(solver.options['threads'], 0)
        with self.assertRaises(ValueError):
            apply_threads(SimpleNamespace(options={}), 'highs', 0)

    def test_three_day_model_matches_gurobi_side_commit(self):
        import subprocess
        from pyomo.environ import Binary, Constraint, NonNegativeReals, Var
        from src.model import MILP_Sheduler

        text = subprocess.check_output(
            ['git', 'show', '828d3f0:AirPortSchedules/TailAssignmentPaper/src/model.py'],
            cwd=ROOT, text=True, encoding='utf-8')
        namespace = {'__name__': 'baseline_828d3f0'}
        exec(compile(text, 'baseline_828d3f0.py', 'exec'), namespace)
        source = ROOT / 'data/feasible_family_smoke/A/DataCplex_density=0.5_p=4_h=7_test_0.json'
        baseline = namespace['MILP_Sheduler'](source)
        current = MILP_Sheduler(source)
        self.assertEqual(baseline.max_hour_check_deferral_days, 3)
        self.assertEqual(current.max_hour_check_deferral_days, 3)
        old_model = baseline.build_model(use_sparse_maint_aircraft_domain=False)
        new_model = current.build_model(use_sparse_maint_aircraft_domain=False)
        old_variables = [(var.name, var.lb, var.ub, var.fixed) for var in old_model.component_data_objects(Var)]
        new_variables = [(var.name, var.lb, var.ub, var.fixed) for var in new_model.component_data_objects(Var)]
        self.assertEqual(old_variables, new_variables)
        self.assertEqual(str(old_model.obj.expr), str(new_model.obj.expr))
        self.assertEqual([(row.name, str(row.expr)) for row in old_model.component_data_objects(Constraint)],
                         [(row.name, str(row.expr)) for row in new_model.component_data_objects(Constraint)])
        for variable in old_model.component_data_objects(Var):
            if variable.domain == Binary:
                variable.domain = NonNegativeReals
                variable.bounds = (0, 1)
        relax_integrality(new_model)
        self.assertNotEqual([(var.name, var.lb, var.ub, var.fixed) for var in old_model.component_data_objects(Var)],
                    [(var.name, var.lb, var.ub, var.fixed) for var in new_model.component_data_objects(Var)])
        legacy_model = MILP_Sheduler(source).build_model(use_sparse_maint_aircraft_domain=False)
        relax_integrality(legacy_model, legacy_unit_bounds=True)
        self.assertEqual([(var.name, var.lb, var.ub, var.fixed) for var in old_model.component_data_objects(Var)],
                 [(var.name, var.lb, var.ub, var.fixed) for var in legacy_model.component_data_objects(Var)])
        self.assertEqual([(row.name, str(row.expr)) for row in old_model.component_data_objects(Constraint)],
                 [(row.name, str(row.expr)) for row in legacy_model.component_data_objects(Constraint)])

    def test_bounds_runner_lp_does_not_require_primal_loading(self):
        from experiments import run_strengthening_bounds as bounds
        from pyomo.environ import ConcreteModel, Var, Objective
        model = ConcreteModel()
        model.assignment = Var(initialize=0)
        model.obj = Objective(expr=model.assignment)
        scheduler = SimpleNamespace(build_model=lambda **_kw: model, flight_ids=[1],
                                    aircraft_ids=[1], days=[1], z_var_count=0)
        result = SimpleNamespace(termination_condition='optimal', objective_bound=42,
                                 incumbent_objective=42)
        with patch.object(bounds, 'MILP_Sheduler', return_value=scheduler), \
                patch.object(bounds, 'SolverFactory', return_value=SimpleNamespace(options={})), \
                patch.object(bounds, 'solve_and_load', return_value=(result, False, None)) as solve:
            row = bounds.run_solve(Path('test.json'), 'baseline', 'lp', 'highs', None, 5, None)
        self.assertFalse(solve.call_args.kwargs['load_solution'])
        self.assertEqual(row['objective'], 42)
        self.assertTrue(row['bound_validated'])

    def test_bounds_only_does_not_load_lp_values(self):
        result = SimpleNamespace(termination_condition='optimal',
                                 objective_bound=14, incumbent_objective=14)
        solver = SimpleNamespace(solve=lambda *_args, **_kw: result)
        _result, loaded, objective = solve_and_load(solver, SimpleNamespace(),
                                                   load_solution=False)
        self.assertFalse(loaded)
        self.assertIsNone(objective)
        self.assertEqual(extract_bounds(_result)[:2], (14, 14))

    def test_classical_requested_preflight_retains_cost_objective(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'instance.json').write_text('{}')
            row = {'instance': 'instance', 'status': 'optimal', 'lp_bound': 42,
                   'wall_s': 0.01, 'feasibility_only': False}
            with patch.object(step4, 'routing_feasibility_status', return_value=row) as preflight, \
                    patch.object(step4, 'solve_lp_lower_bound') as solve:
                step4.main(['--input-dir', str(root), '--formulation', 'classical',
                            '--routing-preflight', '--output', str(root / 'bounds.csv')])
            self.assertTrue(preflight.call_args.kwargs['optimize_cost'])
            solve.assert_not_called()
            with (root / 'bounds.csv').open(newline='') as handle:
                recorded = next(csv.DictReader(handle))
            self.assertEqual(recorded['lp_bound'], '42')

    def test_lazy_maintenance_preserves_routing_and_later_integrated_build(self):
        from src.model import MILP_Sheduler
        from pyomo.environ import Constraint, Var
        source = ROOT / 'data/feasible_family_smoke/A/DataCplex_density=0.5_p=4_h=7_test_0.json'
        eager = MILP_Sheduler(source)
        lazy = MILP_Sheduler(source, prepare_maintenance=False)
        self.assertFalse(lazy._maintenance_prepared)
        self.assertEqual(lazy.c8_check_day_departures_feasible, {})
        eager_routing = eager.build_model(use_maintenance=False)
        lazy_routing = lazy.build_model(use_maintenance=False)
        self.assertEqual(list(eager_routing.X), list(lazy_routing.X))
        self.assertEqual([(row.name, str(row.expr)) for row in eager_routing.component_data_objects(Constraint)],
                         [(row.name, str(row.expr)) for row in lazy_routing.component_data_objects(Constraint)])
        self.assertEqual(sum(1 for _ in eager_routing.component_data_objects(Var)),
                         sum(1 for _ in lazy_routing.component_data_objects(Var)))
        self.assertFalse(lazy._maintenance_prepared)
        eager_integrated = eager.build_model()
        lazy_integrated = lazy.build_model()
        self.assertTrue(lazy._maintenance_prepared)
        self.assertEqual(list(eager_integrated.Z), list(lazy_integrated.Z))
        self.assertEqual([(row.name, str(row.expr)) for row in eager_integrated.component_data_objects(Constraint)],
                         [(row.name, str(row.expr)) for row in lazy_integrated.component_data_objects(Constraint)])

    def test_preflight_feasibility_objective_is_not_a_classical_cost_bound(self):
        source = ROOT / 'data/instances/ABCD_no_maint_test.json'
        feasible = step4.routing_feasibility_status(source, solver_name='highs',
                                                    time_limit=5, return_details=True)
        cost = step4.routing_feasibility_status(source, solver_name='highs',
                                                time_limit=5, return_details=True,
                                                optimize_cost=True)
        self.assertEqual(feasible['status'], 'optimal')
        self.assertTrue(feasible['feasibility_only'])
        self.assertEqual(feasible['lp_bound'], 0)
        self.assertEqual(cost['status'], 'optimal')
        self.assertFalse(cost['feasibility_only'])
        self.assertEqual(cost['lp_bound'], 14000)

    def test_bounds_batch_stops_after_first_solver_failure(self):
        from experiments import run_strengthening_bounds as bounds
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'instance.json').write_text('{}')
            row = {'instance': 'instance', 'variant': 'baseline', 'mode': 'lp',
                   'status': 'internalSolverError', 'error': 'solver ran out of memory'}
            with patch.object(bounds, 'run_solve', return_value=row) as solve:
                status = bounds.main(['--input-dir', str(root), '--skip-heuristic',
                                      '--output', str(root / 'bounds.csv'), '--solver', 'highs'])
            self.assertEqual(status, 1)
            solve.assert_called_once()

    def test_internal_solver_error_is_failure_not_timeout(self):
        from experiments import run_strengthening_bounds as bounds
        from src.solver_utils import completed_status
        from pyomo.environ import ConcreteModel, Var, Objective
        model = ConcreteModel()
        model.assignment = Var(initialize=0)
        model.obj = Objective(expr=model.assignment)
        model.Z = []
        scheduler = SimpleNamespace(build_model=lambda **_kw: model,
                                    flight_ids=[1], aircraft_ids=[1], days=[1], z_var_count=0)
        result = SimpleNamespace(solver=SimpleNamespace(
            termination_condition='internalSolverError', message='out of memory', return_code=7))
        with patch.object(bounds, 'MILP_Sheduler', return_value=scheduler), \
                patch.object(bounds, 'SolverFactory', return_value=SimpleNamespace(options={})), \
                patch.object(bounds, 'solve_and_load', return_value=(result, False, None)):
            row = bounds.run_solve(Path('test.json'), 'baseline', 'lp', 'cplexamp', None, 5, None)
        self.assertIn('out of memory', row['error'])
        self.assertNotIn('within budget', row['error'])
        self.assertEqual(row['solver_return_code'], '7')
        self.assertFalse(completed_status(row['status']))
        self.assertFalse(completed_status('unknown'))
        self.assertTrue(completed_status('maxTimeLimit'))

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
