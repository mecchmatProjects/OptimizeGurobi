"""Shared solver budgets, result handling, and maintenance-domain options."""

import argparse
import math

from pyomo.environ import NonNegativeReals, TransformationFactory, Var, value


def parse_deferral_days(raw):
    if raw is None or str(raw).lower() == 'none':
        return None
    try:
        days = int(raw)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError('Use a nonnegative integer or none.') from exc
    if days < 0 or str(days) != str(raw).strip():
        raise argparse.ArgumentTypeError('Use a nonnegative integer or none.')
    return days


def finite(raw):
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def apply_time_limit(solver, solver_name, time_limit):
    if time_limit is None:
        return False
    if time_limit <= 0:
        raise ValueError('time_limit must be positive or None.')
    config = getattr(solver, 'config', None)
    if config is not None and hasattr(config, 'time_limit'):
        config.time_limit = float(time_limit)
        return True
    name = solver_name.lower()
    keys = {'cplex': 'timelimit', 'gurobi': 'TimeLimit',
            'highs': 'time_limit', 'glpk': 'tmlim', 'cbc': 'seconds',
            'scip': 'limits/time'}
    for backend, key in keys.items():
        if backend in name:
            solver.options[key] = float(time_limit)
            return True
    raise ValueError(f'No verified time-limit option for {solver_name}.')


def termination_of(result):
    condition = getattr(result, 'termination_condition', None)
    if condition is None:
        condition = getattr(getattr(result, 'solver', None), 'termination_condition', None)
    return str(condition) if condition is not None else 'unknown'


def apply_threads(solver, solver_name, threads):
    if threads is None:
        return
    if threads == 0 and 'cplex' in solver_name.lower():
        solver.options['threads'] = 0
        return
    if threads < 1:
        raise ValueError('threads must be positive; CPLEX also supports 0 for automatic.')
    for backend, key in (('cplex', 'threads'), ('gurobi', 'Threads'), ('highs', 'threads')):
        if backend in solver_name.lower():
            solver.options[key] = threads
            return
    raise ValueError('Thread control is verified only for CPLEX, Gurobi and HiGHS.')


def apply_cplex_lp_method(solver, solver_name, method=None, no_crossover=False):
    if method is None and not no_crossover:
        return
    if solver_name.lower() != 'cplex':
        raise ValueError('LP algorithm controls currently require the cplex shell interface.')
    methods = {'auto': 0, 'primal': 1, 'dual': 2, 'barrier': 4, 'concurrent': 6}
    if method not in methods:
        raise ValueError('Unknown CPLEX LP algorithm.')
    if no_crossover and method != 'barrier':
        raise ValueError('No crossover requires the barrier LP algorithm.')
    solver.options['lpmethod'] = methods[method]
    if no_crossover:
        solver.options['barrier crossover'] = -1


def completed_status(status):
    return str(status).lower() in {
        'optimal', 'feasible', 'maxtimelimit', 'maxiterations', 'maxevaluations',
        'maxsolutions', 'infeasible', 'unbounded', 'infeasibleorunbounded',
        'built', 'complete', 'partial',
    }


def solver_details(result, solver=None):
    info = getattr(result, 'solver', None)
    message = getattr(info, 'message', None)
    if message is None:
        message = getattr(result, 'message', None)
    code = getattr(info, 'return_code', None)
    if (code is None or str(code) == '<undefined>') and solver is not None:
        code = getattr(solver, '_rc', None)
    return {'solver_message': str(message) if message is not None else '',
            'solver_return_code': str(code) if code is not None else ''}


def extract_bounds(result):
    dual = finite(getattr(result, 'objective_bound', None))
    primal = finite(getattr(result, 'incumbent_objective', None))
    if dual is None:
        dual = finite(getattr(result, 'best_objective_bound', None))
    if primal is None:
        primal = finite(getattr(result, 'best_feasible_objective', None))
    problem = getattr(result, 'problem', None)
    if dual is None:
        dual = finite(getattr(problem, 'lower_bound', None))
    if primal is None:
        primal = finite(getattr(problem, 'upper_bound', None))
    solutions = getattr(result, 'solution', None)
    if primal is None and solutions is not None and len(solutions):
        objectives = solutions[0].objective
        if len(objectives) == 1:
            primal = finite(next(iter(objectives.values())).get('Value'))
    if dual is None and primal is not None and termination_of(result).lower() == 'optimal':
        dual = primal
    gap = None
    if dual is not None and primal is not None and dual <= primal + 1e-7 * max(1, abs(primal)):
        difference = max(0.0, primal - dual)
        if abs(primal) > 1e-12:
            gap = difference / abs(primal)
        elif difference <= 1e-12:
            gap = 0.0
    nodes = None
    for holder in (result, getattr(result, 'solver', None)):
        for attribute in ('nodes_explored', 'number_of_nodes', 'node_count'):
            candidate = finite(getattr(holder, attribute, None))
            if candidate is not None:
                nodes = int(candidate)
                break
    return dual, primal, gap, nodes


def relax_integrality(model, legacy_unit_bounds=False):
    if legacy_unit_bounds:
        for variable in model.component_data_objects(Var):
            if variable.is_binary():
                variable.domain = NonNegativeReals
                variable.bounds = (0, 1)
        return
    TransformationFactory('core.relax_integer_vars').apply_to(model)


def solve_and_load(solver, model, load_solution=True, **kwargs):
    result = solver.solve(model, load_solutions=False, **kwargs)
    dual, primal, _gap, _nodes = extract_bounds(result)
    status = termination_of(result).lower()
    if not load_solution and (status != 'optimal' or dual is not None):
        return result, False, None
    loaded = False
    if not any(item in status for item in ('infeasible', 'unbounded', 'error')):
        solutions = getattr(result, 'solution', None)
        if solutions is not None and len(solutions):
            model.solutions.load_from(result)
            loaded = True
        else:
            _, primal, _, _ = extract_bounds(result)
            loader = getattr(result, 'solution_loader', None)
            if primal is not None and loader is not None:
                loader.load_vars()
                loaded = True
    objective = finite(value(model.obj)) if loaded else None
    if loaded and status == 'optimal':
        dual = objective if dual is None else dual
        primal = objective if primal is None else primal
    problem = getattr(result, 'problem', None)
    if loaded and problem is not None:
        problem.lower_bound = dual
        problem.upper_bound = primal
    return result, loaded, objective