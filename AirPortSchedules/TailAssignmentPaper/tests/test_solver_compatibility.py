import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pyomo.opt import TerminationCondition
import diagnostics
from src.model import MILP_Sheduler, _run_one_milp


SOURCE = ROOT / "data" / "instances" / "ABCD_near_threshold_test.json"


class SolverCompatibilityTests(unittest.TestCase):
    def test_gurobi_runner_and_no_incumbent_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            runner = home / "python311" / "bin" / "python.exe"
            runner.parent.mkdir(parents=True)
            runner.touch()
            (home / "python311" / "lib" / "gurobipy").mkdir(parents=True)

            result = SimpleNamespace(
                solver=SimpleNamespace(
                    termination_condition=TerminationCondition.infeasible,
                    time=0.01,
                ),
                problem=SimpleNamespace(lower_bound="-", upper_bound="-"),
                solution=[],
            )
            solver = SimpleNamespace(options={}, solve=Mock(return_value=result))
            scheduler = MILP_Sheduler(str(SOURCE), enabled_checks=["A"])
            scheduler.build_model(
                allow_ferry=False,
                use_overlap=False,
                use_maintenance=False,
            )

            with patch.dict(os.environ, {
                "GUROBI_HOME": str(home),
                "TAP_PYOMO_SOLVER_EXECUTABLE": "",
            }), patch("src.model.SolverFactory", return_value=solver) as factory:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    summary = scheduler.solve(
                        solver_name="gurobi",
                        time_limit=12,
                    )

            self.assertEqual(solver.options["TimeLimit"], 12)
            self.assertFalse(solver.solve.call_args.kwargs["load_solutions"])
            factory.assert_called_once_with("gurobi", executable=str(runner))
            self.assertEqual(summary["status"], "infeasible")
            self.assertFalse(summary["has_solution"])
            self.assertIn("No feasible incumbent was returned", output.getvalue())

    def test_batch_row_preserves_infeasible_status_without_fake_objective(self):
        optimizer = SimpleNamespace(model=SimpleNamespace(F=[1]))
        summary = {
            "status": "infeasible",
            "has_solution": False,
            "obj": None,
            "gap": None,
        }

        with patch("src.model.run_milp", return_value=(optimizer, summary)) as run:
            row = _run_one_milp(
                "instance.json",
                "results",
                "instance",
                "gurobi",
                False,
                False,
                30,
                executable="gurobi-python.exe",
            )

        self.assertEqual(row["status"], "infeasible")
        self.assertEqual(row["assigned"], 0)
        self.assertEqual(row["unassigned"], 1)
        self.assertIsNone(row["obj"])
        self.assertEqual(run.call_args.kwargs["executable"], "gurobi-python.exe")

    def test_gurobi_iis_mode_uses_group_scan(self):
        output = io.StringIO()
        with patch("diagnostics.deactivation_scan") as scan, contextlib.redirect_stdout(output):
            scan_performed = diagnostics.find_iis(
                str(SOURCE),
                solver_name="gurobi",
                executable="gurobi-python.exe",
            )

        self.assertTrue(scan_performed)
        scan.assert_called_once()
        self.assertEqual(scan.call_args.kwargs["solver_name"], "gurobi")
        self.assertIn("Native IIS extraction is not configured for gurobi", output.getvalue())

    def test_diagnostic_scan_accepts_time_limit_with_incumbent(self):
        result = SimpleNamespace(
            solver=SimpleNamespace(
                termination_condition=TerminationCondition.maxTimeLimit,
            ),
            solution=[object()],
        )
        solver = SimpleNamespace(options={}, solve=Mock(return_value=result))
        output = io.StringIO()

        with patch("diagnostics.CONSTRAINT_GROUPS", ["c1"]), \
             patch("pyomo.opt.SolverFactory", return_value=solver), \
             contextlib.redirect_stdout(output):
            statuses = diagnostics.deactivation_scan(
                str(SOURCE),
                solver_name="gurobi",
                time_limit=5,
                build_kwargs={"use_maintenance": False},
                executable="gurobi-python.exe",
            )

        self.assertEqual(solver.options["TimeLimit"], 5)
        self.assertEqual(statuses["c1"], "maxTimeLimit")
        self.assertIn("FEASIBLE (this group caused infeasibility!)", output.getvalue())


if __name__ == "__main__":
    unittest.main()
