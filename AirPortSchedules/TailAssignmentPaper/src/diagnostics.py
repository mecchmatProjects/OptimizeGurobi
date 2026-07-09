"""
diagnostics.py — MILP infeasibility diagnosis for the Tail Assignment Problem.

Two complementary tools:
  1. find_iis()          — CPLEX conflict refiner (IIS finder) + LP file export.
  2. deactivation_scan() — Systematically deactivate one constraint group at a
                           time and report whether the problem becomes feasible.
                           Useful when CPLEX IIS is not available.

Usage (command line):
  python diagnostics.py --data data/instances/ABCD_all_checks_test.json --mode iis
  python diagnostics.py --data data/instances/ABCD_all_checks_test.json --mode scan
  python diagnostics.py --data data/instances/... --mode both
"""

import sys
import os
import time
import argparse

# Allow running from the project root or from src/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model import MILP_Sheduler
from pyomo.environ import Constraint


# ---------------------------------------------------------------------------
# Constraint groups that can be deactivated independently
# ---------------------------------------------------------------------------
CONSTRAINT_GROUPS = [
    "c1",           # flight coverage (always active; disabling = trivial feasibility)
    "c23",          # equipment continuity + turn time
    "c8",           # maintenance blocks subsequent same-day flights
    "c9",           # maintenance requires assignment (z <= x)
    "c10",          # maintenance airport capacity
    "c11",          # link z -> y (aggregation)
    "c_hierarchy",  # check hierarchy (D resets C/B/A, etc.)
    "c12",          # calendar-day spacing (C/D checks)
    "c12b",         # initial-days enforcement
    "c12_days",     # multi-day spacing extension
    "c13",          # flight-hour accumulation (A/B checks)  ← paper constraint (13)
    "c13b",         # pre-horizon accumulated-hours (extension)
    "c14",          # at most one check type per aircraft per day
    "c14b",         # multi-day check duration (consecutive days)
    "c15",          # no flights during active maintenance window
    "c_overlap",    # non-overlapping flight constraint
]


# ---------------------------------------------------------------------------
# Tool 1: CPLEX IIS / conflict refiner
# ---------------------------------------------------------------------------

def find_iis(data_path: str,
             out_lp: str | None = None,
             build_kwargs: dict | None = None) -> None:
    """
    Attempt to find the Irreducible Infeasible Subsystem (IIS) using CPLEX.

    Falls back to deactivation_scan() if the CPLEX conflict refiner is
    not accessible via Pyomo.

    Parameters
    ----------
    data_path   : Path to the JSON instance file.
    out_lp      : If given, write the model LP file to this path.
    build_kwargs: Extra kwargs forwarded to MILP_Sheduler.build_model().
    """
    if build_kwargs is None:
        build_kwargs = {}

    print(f"\n{'='*60}")
    print(f"IIS Finder — {os.path.basename(data_path)}")
    print(f"{'='*60}")

    sch = MILP_Sheduler(data_path)
    m = sch.build_model(**build_kwargs)

    n_vars = sum(1 for _ in m.component_data_objects(
        ctype=__import__('pyomo.core', fromlist=['Var']).Var, active=True))
    n_cons = sum(1 for _ in m.component_data_objects(
        ctype=Constraint, active=True))
    print(f"Model built: {n_vars:,} variables, {n_cons:,} constraints")

    if out_lp:
        os.makedirs(os.path.dirname(os.path.abspath(out_lp)), exist_ok=True)
        m.write(out_lp, format='lp')
        print(f"LP written to {out_lp}")

    print("\nRunning CPLEX conflict refiner...")
    try:
        from pyomo.opt import SolverFactory
        solver = SolverFactory('cplex')
        if not solver.available():
            raise RuntimeError("CPLEX solver not available on PATH.")
        solver.options['conflict'] = 1
        solver.options['conflictdisplay'] = 2
        result = solver.solve(m, tee=True, symbolic_solver_labels=True)
        print(f"\nSolver status: {result.solver.termination_condition}")
    except Exception as exc:
        print(f"IIS via CPLEX failed: {exc}")
        print("Falling back to constraint-group deactivation scan...\n")
        deactivation_scan(data_path, build_kwargs=build_kwargs)


# ---------------------------------------------------------------------------
# Tool 2: Constraint-group deactivation scan
# ---------------------------------------------------------------------------

def deactivation_scan(data_path: str,
                      solver_name: str = 'cplex',
                      time_limit: int = 30,
                      build_kwargs: dict | None = None) -> dict:
    """
    For each constraint group in CONSTRAINT_GROUPS, deactivate it, solve
    the remaining problem, and report whether feasibility is achieved.

    Returns a dict mapping group_name -> termination_condition_string.

    Parameters
    ----------
    data_path   : Path to the JSON instance file.
    solver_name : Solver to use for each sub-problem.
    time_limit  : Per-sub-problem time limit in seconds.
    build_kwargs: Extra kwargs forwarded to MILP_Sheduler.build_model().
    """
    if build_kwargs is None:
        build_kwargs = {}

    print(f"\n{'='*60}")
    print(f"Constraint-Group Deactivation Scan")
    print(f"Dataset : {os.path.basename(data_path)}")
    print(f"Solver  : {solver_name}   time_limit={time_limit}s")
    print(f"{'='*60}")
    print(f"\n  {'Group deactivated':40s}  {'Status':20s}  {'CPU':>6}")
    print(f"  {'-'*72}")

    from pyomo.opt import SolverFactory, TerminationCondition

    results = {}

    for group in CONSTRAINT_GROUPS:
        # Rebuild model fresh each time (avoid state leakage)
        sch = MILP_Sheduler(data_path)
        m = sch.build_model(**build_kwargs)

        cg = getattr(m, group, None)
        if cg is None:
            print(f"  {group:40s}  {'(not present)':20s}")
            results[group] = 'not_present'
            continue

        cg.deactivate()

        solver = SolverFactory(solver_name)
        solver.options['timelimit' if solver_name == 'cplex' else 'TimeLimit'] = time_limit

        t0 = time.time()
        try:
            r = solver.solve(m, tee=False)
            tc = str(r.solver.termination_condition)
        except Exception as e:
            tc = f'error: {e}'
        cpu = time.time() - t0

        # Flag if dropping this group restored feasibility
        flag = ' <-- FEASIBLE (this group caused infeasibility!)' \
               if tc in ('optimal', 'feasible') else ''
        print(f"  {'drop ' + group:40s}  {tc:20s}  {cpu:5.1f}s{flag}")
        results[group] = tc

    print()
    # Summary
    guilty = [g for g, tc in results.items() if tc in ('optimal', 'feasible')]
    if guilty:
        print(f"Infeasibility traced to group(s): {guilty}")
    else:
        print("No single group removal restored feasibility. "
              "Infeasibility arises from interaction of multiple groups.")
    return results


# ---------------------------------------------------------------------------
# Command-line interface
# ---------------------------------------------------------------------------

def _parse_args():
    p = argparse.ArgumentParser(
        description="MILP infeasibility diagnostics for the Tail Assignment Problem.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  iis   -- CPLEX conflict refiner (falls back to scan if unavailable)
  scan  -- Deactivate each constraint group and check feasibility
  both  -- Run IIS first, then scan

Examples:
  python diagnostics.py --data data/instances/ABCD_all_checks_test.json --mode scan
  python diagnostics.py --data data/instances/... --mode iis --out-lp debug.lp
""")
    p.add_argument('--data',     required=True, help='Path to JSON instance')
    p.add_argument('--mode',     default='scan',
                   choices=['iis', 'scan', 'both'], help='Diagnostic mode')
    p.add_argument('--solver',   default='cplex', help='Solver name (scan mode)')
    p.add_argument('--time-limit', type=int, default=30,
                   help='Time limit per sub-problem in scan mode (s)')
    p.add_argument('--out-lp',   default=None,
                   help='Write LP file to this path (iis mode)')
    p.add_argument('--no-maintenance', dest='use_maintenance',
                   action='store_false', default=True,
                   help='Build model without maintenance constraints')
    return p.parse_args()


if __name__ == '__main__':
    args = _parse_args()
    bkw = dict(use_maintenance=args.use_maintenance)

    if args.mode in ('iis', 'both'):
        find_iis(args.data, out_lp=args.out_lp, build_kwargs=bkw)
    if args.mode in ('scan', 'both'):
        deactivation_scan(args.data,
                          solver_name=args.solver,
                          time_limit=args.time_limit,
                          build_kwargs=bkw)
