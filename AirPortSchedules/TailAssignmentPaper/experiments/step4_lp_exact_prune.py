#!/usr/bin/env python3
"""
Step 4 companion: LP bounds with *exact* domain pruning only.

This is not a drop-in alias of ``step4_lp_lower_bounds.py --reachability``.
That flag drops deferred trigger days whenever *any* timetable departure
leaves the station — including flights that belong to other tails. That
restriction is not lossless.

Exact reductions implemented here
---------------------------------
T2  Physical x-arc pruning.  Label-correcting earliest-presence over the
    flight graph.  If tail j cannot be at origin(i) by dep(i) under C2–C3
    (no teleport), then x[i,j] and every z[i,j,*,*] are infeasible and
    are removed.  Kept arcs are a *superset* of the truly feasible ones
    (the shortest-path pass may reuse another tail's flight as a hop),
    so nothing feasible is deleted.

    After T2, z is indexed only over surviving (flight, tail) arcs
    (``use_sparse_maint_aircraft_domain=True``).  On DataCplex files the
    cost-matrix 9999 filter removes nothing; T2 is what actually thins z.

Not implemented (not exact)
---------------------------
- Station-wait ``use_maint_reachability`` (other-tail departures).
- Last-arrival deferred-trigger thinning (T3).
- Check-dimension factorisation (T4; different formulation).
- Calendar-window widening (adds variables; changes C/D start domain).

Optional and *restrictive* (off by default)
-------------------------------------------
--max-hour-check-deferral-days N   Caps A/B trigger windows.  Shrinks z
                                   a lot on long horizons but can cut
                                   genuine overnight parking.  The CSV
                                   column ``restrictive_deferral`` flags
                                   this so the bound is not mixed with
                                   the unreduced model.

``z_vars`` is ``len(model.Z)`` after the Pyomo index is built, not the
stale ``scheduler.z_var_count`` computed in ``MILP_Sheduler.__init__``.

C2–C3 are always left ON when T2 is applied.  Turning routing off would
make teleportation feasible and T2 would then be incorrect.
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from step4_lp_lower_bounds import apply_time_limit  # noqa: E402

from model import MILP_Sheduler  # noqa: E402


# ---------------------------------------------------------------------------
# T2: earliest presence (standalone; no Pyomo)
# ---------------------------------------------------------------------------

def earliest_presence(flight_data: Dict[int, Dict], airports: Sequence[str],
                      start_airport: str, turn: float) -> Dict[str, float]:
    """Earliest time a tail starting at ``start_airport`` can be at each airport.

    Label-correcting pass over flights in departure order.  The tail is at
    its base at time 0 with no turn penalty; every subsequent hop needs
    the turn.  Using every flight as a possible hop over-approximates
    reachability (C1 uniqueness is ignored), which is the safe direction
    for pruning: we never delete an arc a feasible schedule could use.
    """
    best = {a: math.inf for a in airports}
    best[start_airport] = 0.0
    order = sorted(flight_data, key=lambda i: flight_data[i]["departureTime"])
    changed = True
    while changed:
        changed = False
        for fid in order:
            fd = flight_data[fid]
            origin, dest = fd["origin"], fd["destination"]
            if not math.isfinite(best[origin]):
                continue
            ready = best[origin] + (0.0 if best[origin] == 0.0 else turn)
            if (fd["departureTime"] >= ready - 1e-9
                    and fd["arrivalTime"] < best[dest] - 1e-9):
                best[dest] = fd["arrivalTime"]
                changed = True
    return best


def count_z_index(scheduler: MILP_Sheduler, sparse: bool) -> int:
    """Count the z tuples ``_add_sets_and_variables`` would actually create."""
    total = 0
    for fid in scheduler.maint_flight_ids:
        aircraft_ids = (
            scheduler._x_aircrafts_for_flight(fid) if sparse
            else scheduler.aircraft_ids
        )
        for _aid in aircraft_ids:
            for check in scheduler.CHECK_LIST:
                total += len(scheduler._z_days_for(fid, check))
    return total


class ExactPruneMILP(MILP_Sheduler):
    """``MILP_Sheduler`` with exact T2 x-arc pruning applied in ``__init__``."""

    def __init__(self, data_path, *, prune_x: bool = True, **kwargs):
        super().__init__(data_path, **kwargs)
        self.z_vars_before_prune = count_z_index(self, sparse=False)
        self.x_vars_before_prune = self.x_var_count
        self.x_arcs_removed = 0
        self.prune_x = bool(prune_x)
        if self.prune_x:
            self._apply_physical_reachability()
        self.z_vars_after_prune = count_z_index(self, sparse=True)
        self.z_var_count = self.z_vars_after_prune

    def _arc_is_reachable(self, fid, aid, reach: Dict[int, Dict[str, float]]) -> bool:
        fd = self.flight_data[fid]
        earliest = reach[aid].get(fd["origin"], math.inf)
        if not math.isfinite(earliest):
            return False
        ready = earliest + (0.0 if earliest == 0.0 else self.min_turn)
        return ready <= fd["departureTime"] + 1e-9

    def _apply_physical_reachability(self) -> None:
        reach = {
            aid: earliest_presence(
                self.flight_data, self.airports,
                self.aircraft_init[aid], self.min_turn,
            )
            for aid in self.aircraft_ids
        }
        removed = 0
        new_by_flight = {}
        for fid in self.flight_ids:
            keep = tuple(
                aid for aid in self.x_arcs_by_flight[fid]
                if self._arc_is_reachable(fid, aid, reach)
            )
            if not keep:
                # Empty coverage would make C1 infeasible and hide the cause.
                keep = self.x_arcs_by_flight[fid]
            removed += len(self.x_arcs_by_flight[fid]) - len(keep)
            new_by_flight[fid] = keep
        self.x_arcs_removed = removed
        self.x_arcs_by_flight = new_by_flight
        self.x_arcs_by_aircraft = {aid: [] for aid in self.aircraft_ids}
        self.x_arcs_set = set()
        self.x_var_count = 0
        for fid, arcs in new_by_flight.items():
            self.x_var_count += len(arcs)
            for aid in arcs:
                self.x_arcs_by_aircraft[aid].append(fid)
                self.x_arcs_set.add((fid, aid))
        self._rebuild_c8_caches()

    def _rebuild_c8_caches(self) -> None:
        """Parent built these from the pre-prune arc set."""
        for fid in self.maint_flight_ids:
            apt = self.flight_data[fid]["destination"]
            for ck in self.CHECK_LIST:
                same = self.c8_same_day_block[(fid, ck)]
                esc = self.c8_escape[(fid, ck)]
                for aid in self.aircraft_ids:
                    self.c8_same_day_block_feasible[(fid, ck, aid)] = tuple(
                        f2 for f2 in same if self._x_has_arc(f2, aid)
                    )
                    self.c8_escape_feasible[(fid, ck, aid)] = tuple(
                        f2 for f2 in esc if self._x_has_arc(f2, aid)
                    )
            for day in self.days:
                day_deps = tuple(self._dep_flights_by_day_airport[(day, apt)])
                for aid in self.aircraft_ids:
                    self.c8_check_day_departures_feasible[(fid, day, aid)] = (
                        tuple(f2 for f2 in day_deps if self._x_has_arc(f2, aid))
                    )

    def build_model(self, *args, **kwargs):
        if kwargs.get("allow_ferry") is False:
            raise ValueError(
                "Exact T2 pruning assumes C2–C3 routing (allow_ferry=True). "
                "Do not combine --no-routing with --prune-x."
            )
        kwargs.setdefault("allow_ferry", True)
        kwargs.setdefault("use_sparse_maint_aircraft_domain", True)
        # Never turn on the inexact station-wait filter.
        kwargs["use_maint_reachability"] = False
        return super().build_model(*args, **kwargs)


def _parse_checks(text: str) -> Optional[list]:
    checks = [c.strip().upper() for c in (text or "").split(",") if c.strip()]
    return checks or None


def report_pruning(instance_path: Path, enabled_checks=None,
                   max_deferral_days=None, prune_x: bool = True) -> dict:
    """Size the domain without constructing Pyomo constraints."""
    baseline = MILP_Sheduler(
        instance_path,
        enabled_checks=enabled_checks,
        max_hour_check_deferral_days=max_deferral_days,
    )
    pruned = ExactPruneMILP(
        instance_path,
        prune_x=prune_x,
        enabled_checks=enabled_checks,
        max_hour_check_deferral_days=max_deferral_days,
    )
    z_base = count_z_index(baseline, sparse=False)
    z_sparse_only = count_z_index(baseline, sparse=True)
    return {
        "instance": instance_path.stem,
        "flights": len(baseline.flight_ids),
        "tails": len(baseline.aircraft_ids),
        "horizon_days": len(baseline.days),
        "maint_flights": len(baseline.maint_flight_ids),
        "x_before": baseline.x_var_count,
        "x_after": pruned.x_var_count,
        "x_arcs_removed": pruned.x_arcs_removed,
        "z_before": z_base,
        "z_cost_sparse_only": z_sparse_only,
        "z_after": pruned.z_vars_after_prune,
        "z_reduction": round(z_base / max(1, pruned.z_vars_after_prune), 3),
        "restrictive_deferral": max_deferral_days,
        "prune_x": prune_x,
    }


def solve_pruned_lp(instance_path: Path, *, solver_name: str, time_limit: int,
                    use_maintenance: bool, executable=None,
                    enabled_checks=None, max_deferral_days=None,
                    prune_x: bool = True, tight_c13_m: bool = False) -> dict:
    from pyomo.environ import (
        Binary, Constraint, NonNegativeReals, SolverFactory, Var,
        TerminationCondition, value as pyo_value,
    )

    name = instance_path.stem
    log.info("Building pruned model: %s", name)
    scheduler = ExactPruneMILP(
        instance_path,
        prune_x=prune_x,
        enabled_checks=enabled_checks,
        max_hour_check_deferral_days=max_deferral_days,
    )
    sizes = report_pruning(
        instance_path, enabled_checks=enabled_checks,
        max_deferral_days=max_deferral_days, prune_x=prune_x,
    )
    log.info(
        "  x %s -> %s (removed %s)   z %s -> %s (%.2fx)",
        sizes["x_before"], sizes["x_after"], sizes["x_arcs_removed"],
        sizes["z_before"], sizes["z_after"], sizes["z_reduction"],
    )
    model = scheduler.build_model(
        use_maintenance=use_maintenance,
        use_sparse_maint_aircraft_domain=True,
        use_maint_reachability=False,
        use_tight_c13_m=tight_c13_m,
        allow_ferry=True,
    )
    z_built = len(list(model.Z))
    if z_built != scheduler.z_vars_after_prune:
        log.warning(
            "len(Z)=%s differs from pre-count %s",
            z_built, scheduler.z_vars_after_prune,
        )

    for var in model.component_data_objects(ctype=Var):
        if var.domain == Binary:
            var.domain = NonNegativeReals
            var.bounds = (0, 1)

    solver_kwargs = {"executable": str(executable)} if executable else {}
    solver = SolverFactory(solver_name, **solver_kwargs)
    apply_time_limit(solver, solver_name, time_limit)
    log.info("Solving LP (%s, %ss)", solver_name, time_limit)
    results = solver.solve(model, tee=False)

    n_var = len(list(model.component_data_objects(ctype=Var)))
    n_con = len(list(model.component_data_objects(ctype=Constraint)))
    status = str(results.solver.termination_condition)
    lp_bound = (
        pyo_value(model.obj)
        if results.solver.termination_condition == TerminationCondition.optimal
        else None
    )
    runtime = getattr(results.solver, "time", None) or 0.0
    return {
        **sizes,
        "formulation": "integrated" if use_maintenance else "classical",
        "n_var": n_var,
        "n_con": n_con,
        "z_vars": z_built,
        "status": status,
        "lp_bound": lp_bound,
        "runtime_s": runtime,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--data", type=Path, default=None,
                        help="Single JSON instance.")
    parser.add_argument("--input-dir", type=Path, default=None,
                        help="Folder of JSON instances (used with --pattern).")
    parser.add_argument("--pattern", default="*.json")
    parser.add_argument("--output", type=Path,
                        default=Path("results/tables/step4_lp_exact_prune.csv"))
    parser.add_argument("--solver", default="highs")
    parser.add_argument("--executable", type=Path, default=None)
    parser.add_argument("--time-limit", type=int, default=60)
    parser.add_argument("--formulation", choices=("classical", "integrated", "both"),
                        default="integrated")
    parser.add_argument("--enabled-checks", default="",
                        help="Comma-separated subset of A,B,C,D.")
    parser.add_argument("--max-hour-check-deferral-days", type=int, default=None,
                        help="RESTRICTIVE cap on A/B trigger windows. Off by default.")
    parser.add_argument("--no-prune-x", action="store_true",
                        help="Disable T2 (still reports cost-sparse z for comparison).")
    parser.add_argument("--tight-c13-m", action="store_true")
    parser.add_argument("--report-only", action="store_true",
                        help="Print/write domain sizes; do not build or solve the LP.")
    return parser.parse_args()


def iter_instances(args: argparse.Namespace) -> Iterable[Path]:
    if args.data is not None:
        yield args.data
        return
    if args.input_dir is not None:
        paths = sorted(args.input_dir.glob(args.pattern))
        if not paths:
            log.warning("No instances matched %s/%s", args.input_dir, args.pattern)
        yield from paths
        return
    yield ROOT / "data/instances/DataCplex_density=1_p=10_h=7_test_0.json"


def main() -> None:
    args = parse_args()
    enabled_checks = _parse_checks(args.enabled_checks)
    prune_x = not args.no_prune_x
    output_path = args.output
    if output_path.suffix.lower() != ".csv":
        output_path = output_path / "step4_lp_exact_prune.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    formulations = (
        ["classical", "integrated"] if args.formulation == "both"
        else [args.formulation]
    )
    for inst_path in iter_instances(args):
        inst_path = Path(inst_path)
        if not inst_path.exists():
            log.warning("Instance not found: %s", inst_path)
            continue
        log.info("=== %s ===", inst_path.name)
        if args.report_only:
            row = report_pruning(
                inst_path,
                enabled_checks=enabled_checks,
                max_deferral_days=args.max_hour_check_deferral_days,
                prune_x=prune_x,
            )
            log.info(
                "  x %s -> %s (removed %s)   z %s -> %s (cost-sparse-only %s, %.2fx)",
                row["x_before"], row["x_after"], row["x_arcs_removed"],
                row["z_before"], row["z_after"], row["z_cost_sparse_only"],
                row["z_reduction"],
            )
            rows.append(row)
            continue
        for formulation in formulations:
            try:
                row = solve_pruned_lp(
                    inst_path,
                    solver_name=args.solver,
                    time_limit=args.time_limit,
                    use_maintenance=(formulation == "integrated"),
                    executable=args.executable,
                    enabled_checks=enabled_checks,
                    max_deferral_days=args.max_hour_check_deferral_days,
                    prune_x=prune_x,
                    tight_c13_m=args.tight_c13_m,
                )
                row["formulation"] = formulation
                rows.append(row)
                log.info(
                    "  %s status=%s bound=%s z_vars=%s",
                    formulation, row["status"], row["lp_bound"], row["z_vars"],
                )
            except Exception as exc:
                log.error("Failed %s (%s): %s", inst_path.name, formulation, exc)
                import traceback
                log.error(traceback.format_exc())
                rows.append({
                    "instance": inst_path.stem,
                    "formulation": formulation,
                    "status": "error",
                    "lp_bound": None,
                    "z_vars": None,
                })

    if not rows:
        log.warning("No results to write.")
        return

    fieldnames = [
        "instance", "formulation", "flights", "tails", "horizon_days",
        "maint_flights", "x_before", "x_after", "x_arcs_removed",
        "z_before", "z_cost_sparse_only", "z_after", "z_vars", "z_reduction",
        "n_var", "n_con", "status", "lp_bound", "runtime_s",
        "restrictive_deferral", "prune_x",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})
    log.info("Wrote %s", output_path)


if __name__ == "__main__":
    main()
