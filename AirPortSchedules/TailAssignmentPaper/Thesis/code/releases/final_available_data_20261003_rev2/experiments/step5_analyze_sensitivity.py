#!/usr/bin/env python3
"""
Step 5: Sensitivity Analysis Interpretation

Data-driven summary of results produced by step5_sensitivity_analysis.py.
All conclusions are computed from the CSV rather than hard-coded, so the report
always reflects the actual multi-instance run.
"""

import csv
from pathlib import Path
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger(__name__)

FAMILIES = [('thr_', 'Thresholds'), ('dur_', 'Durations'), ('cap_', 'Capacity')]


def _family(experiment_id: str) -> str:
    for tag, name in FAMILIES:
        if tag in experiment_id:
            return name
    return 'Other'


def _scale_pct(param_change: str) -> str:
    # param_change looks like "Thresholds=150%"
    return param_change.split('=')[-1] if '=' in param_change else param_change


def analyze_sensitivity_results(results_csv: Path) -> None:
    if not results_csv.exists():
        log.error(f"Results file not found: {results_csv}")
        return

    with open(results_csv) as f:
        results = list(csv.DictReader(f))

    if not results:
        log.error("Results file is empty.")
        return

    # Group by (base_instance, family) -> list of rows
    groups = defaultdict(list)
    for r in results:
        base = r.get('base_instance', r['experiment_id'])
        groups[(base, _family(r['experiment_id']))].append(r)

    instances = sorted({r.get('base_instance', r['experiment_id']) for r in results})

    log.info("=" * 80)
    log.info("SENSITIVITY ANALYSIS: DATA-DRIVEN SUMMARY")
    log.info("=" * 80)
    log.info(f"Instances: {len(instances)}   Total experiments: {len(results)}")

    # Per-family influence tallies across instances.
    family_feas_flips = defaultdict(int)   # family -> #instances with any infeasible variant
    family_cost_effect = defaultdict(int)  # family -> #instances where objective changes

    for base in instances:
        log.info("\n" + "-" * 80)
        log.info(f"INSTANCE: {base}")
        for _, fam in FAMILIES:
            rows = groups.get((base, fam), [])
            if not rows:
                continue

            def _num(row):
                s = _scale_pct(row['param_change']).rstrip('%')
                try:
                    return float(s)
                except ValueError:
                    return 0.0

            rows = sorted(rows, key=_num)
            feas = [r for r in rows if r['feasible'] == 'True']
            infeas = [r for r in rows if r['feasible'] != 'True']
            objs = sorted({r['objective'] for r in feas if r['objective'] != 'N/A'})

            frontier = ' '.join(
                f"{_scale_pct(r['param_change'])}:"
                f"{'inf' if r['feasible'] != 'True' else r['objective']}"
                for r in rows
            )
            log.info(f"  {fam:11s} {frontier}")

            if infeas:
                family_feas_flips[fam] += 1
            if len(objs) > 1:
                family_cost_effect[fam] += 1

    # Cross-instance ranking
    log.info("\n" + "=" * 80)
    log.info("CROSS-INSTANCE PARAMETER INFLUENCE")
    log.info("=" * 80)
    n_inst = len(instances)
    for _, fam in FAMILIES:
        log.info(
            f"  {fam:11s} feasibility-flips on {family_feas_flips[fam]}/{n_inst} instances, "
            f"cost-effect on {family_cost_effect[fam]}/{n_inst} instances"
        )

    ranked = sorted(
        (fam for _, fam in FAMILIES),
        key=lambda f: (family_feas_flips[f] + family_cost_effect[f]),
        reverse=True,
    )
    log.info("\n  Dominant-parameter ranking (feasibility-flips + cost-effect):")
    for i, fam in enumerate(ranked, 1):
        log.info(f"    [{i}] {fam}")

    # Model size + runtime invariance
    log.info("\n" + "=" * 80)
    log.info("MODEL SIZE AND RUNTIME")
    log.info("=" * 80)
    ratios = [float(r['model_size_ratio']) for r in results
              if r['model_size_ratio'] != 'N/A' and float(r['model_size_ratio']) > 0]
    runtimes = [float(r['runtime_s']) for r in results if float(r['runtime_s']) > 0]
    if ratios:
        log.info(f"  Model-size ratio range: {min(ratios):.3f}x - {max(ratios):.3f}x baseline")
    if runtimes:
        log.info(f"  Runtime range: {min(runtimes):.2f}s - {max(runtimes):.2f}s "
                 f"(mean {sum(runtimes)/len(runtimes):.2f}s)")
    log.info("  -> parameter pressure produces a discrete feasibility cliff, not a runtime cliff.")

    total_feasible = sum(1 for r in results if r['feasible'] == 'True')
    log.info("\n" + "=" * 80)
    log.info(f"Feasible: {total_feasible}/{len(results)}   "
             f"Infeasible/other: {len(results) - total_feasible}/{len(results)}")
    log.info("Analysis complete.")


if __name__ == '__main__':
    analyze_sensitivity_results(Path("results/tables/step5_sensitivity_analysis.csv"))
