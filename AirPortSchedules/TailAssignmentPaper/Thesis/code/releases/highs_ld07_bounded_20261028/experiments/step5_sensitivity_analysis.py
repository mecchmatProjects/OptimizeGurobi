#!/usr/bin/env python3
"""
Step 5: Sensitivity Analysis on the MILP Model

Objective: Identify which parameters most affect runtime and feasibility by
systematically varying key MILP parameters and measuring:
  1. Model size (variables, constraints)
  2. Solver runtime
  3. Feasibility status
  4. Solution quality

Key parameters to vary:
  - Maintenance_Thresholds (A, B, C_days, D_days) → controls check frequency
  - Maintenance_Durations (A, B, C, D) → controls maintenance window length
  - Station_Capacity → controls parallel maintenance slots
  - Problem scale (flights, aircraft, horizon) → controls model size

Design:
  1. Start with a base instance (ABCD_check_hierarchy_test)
  2. Create parameter variants by scaling thresholds and durations
  3. Run MILP on each variant with fixed solver limit
  4. Collect results: model size, runtime, status, objective
  5. Analyze correlation between parameter changes and outcomes
"""

import json
import csv
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional
import sys
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# Import MILP scheduler
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from model import MILP_Sheduler

@dataclass
class SensitivityResult:
    """One result from a sensitivity experiment."""
    base_instance: str
    experiment_id: str
    parameter_set: str
    param_change: str  # e.g., "T_A=50%", "Capacity=-30%"
    n_var: int
    n_con: int
    model_size_ratio: float  # relative to baseline
    runtime_s: float
    solver_status: str
    objective: Optional[float]
    feasible: bool
    infeasibility_reason: Optional[str]

# ============================================================================
# PARAMETER PERTURBATION FUNCTIONS
# ============================================================================

def scale_threshold(base_value: float, scale_factor: float) -> float:
    """Scale a maintenance threshold by a factor."""
    return base_value * scale_factor

def scale_duration(base_value: float, scale_factor: float) -> float:
    """Scale a maintenance duration by a factor."""
    return base_value * scale_factor

def scale_capacity(base_capacity: int, scale_factor: float) -> int:
    """Scale a station capacity.

    An airport whose base capacity is 0 (maintenance forbidden there) must stay
    at 0 so scaling never silently introduces a maintenance slot that changes
    instance semantics.  Positive capacities keep a floor of 1 so a downward
    scale never drops a real maintenance station to 0.
    """
    if base_capacity <= 0:
        return 0
    return max(1, int(round(base_capacity * scale_factor)))

def create_variant_instance(
    base_instance_path: Path,
    variant_name: str,
    threshold_scales: Optional[Dict[str, float]] = None,
    duration_scales: Optional[Dict[str, float]] = None,
    capacity_scales: Optional[Dict[str, float]] = None
) -> Path:
    """
    Create a variant instance by scaling specified parameters.
    
    Parameters
    ----------
    base_instance_path : Path
        Path to base instance JSON
    variant_name : str
        Name for the variant (used in output filename)
    threshold_scales : dict, optional
        Scale factors for A, B, C, D thresholds
        E.g., {'A': 0.5, 'B': 0.5} scales A and B to 50%
    duration_scales : dict, optional
        Scale factors for maintenance durations
    capacity_scales : dict, optional
        Scale factors for station capacities
        
    Returns
    -------
    Path
        Path to the created variant instance
    """
    with open(base_instance_path) as f:
        data = json.load(f)
    
    # Scale thresholds
    if threshold_scales:
        for check_type, scale in threshold_scales.items():
            if check_type in data['Maintenance_Thresholds']:
                original = data['Maintenance_Thresholds'][check_type]
                data['Maintenance_Thresholds'][check_type] = scale_threshold(original, scale)
    
    # Scale durations
    if duration_scales:
        for check_type, scale in duration_scales.items():
            if check_type in data['Maintenance_Durations']:
                original = data['Maintenance_Durations'][check_type]
                data['Maintenance_Durations'][check_type] = scale_duration(original, scale)
    
    # Scale capacities
    if capacity_scales:
        for airport, scale in capacity_scales.items():
            if airport in data['Station_Capacity']:
                original = data['Station_Capacity'][airport]
                data['Station_Capacity'][airport] = scale_capacity(original, scale)
    
    # Write variant to temp file
    variant_dir = Path("data/instances/sensitivity_variants")
    variant_dir.mkdir(parents=True, exist_ok=True)
    variant_path = variant_dir / f"{variant_name}.json"
    
    with open(variant_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    log.info(f"Created variant: {variant_path}")
    return variant_path

def run_sensitivity_experiment(
    base_instance_path: Path,
    solver_name: str = 'highs',
    time_limit: int = 120
) -> List[SensitivityResult]:
    """
    Run systematic sensitivity analysis on base instance.
    
    Experiments:
    1. Threshold sensitivity: vary A/B/C/D thresholds (25%, 50%, 100%, 150%, 200%)
    2. Duration sensitivity: vary maintenance durations (50%, 75%, 100%, 150%)
    3. Capacity sensitivity: vary station capacity (50%, 100%, 150%)
    4. Combined effects: select high-impact combinations
    """
    
    results = []
    base_name = base_instance_path.stem
    
    log.info("=" * 80)
    log.info(f"SENSITIVITY ANALYSIS: {base_name}")
    log.info("=" * 80)
    
    # Load base instance to extract baseline metrics
    with open(base_instance_path) as f:
        base_data = json.load(f)
    
    baseline_thresholds = base_data['Maintenance_Thresholds'].copy()
    baseline_durations = base_data['Maintenance_Durations'].copy()
    baseline_capacities = base_data['Station_Capacity'].copy()
    
    # EXPERIMENT 1: Maintenance threshold sensitivity
    log.info("\n[EXP 1] Maintenance Threshold Sensitivity")
    log.info("-" * 80)
    
    threshold_scales = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
    threshold_variants = []
    
    for scale in threshold_scales:
        variant_name = f"{base_name}_thr_{int(scale*100)}"
        variant_path = create_variant_instance(
            base_instance_path,
            variant_name,
            threshold_scales={'A': scale, 'B': scale, 'C': scale, 'D': scale}
        )
        threshold_variants.append((variant_name, variant_path, f"Thresholds={int(scale*100)}%"))
    
    # EXPERIMENT 2: Maintenance duration sensitivity
    log.info("\n[EXP 2] Maintenance Duration Sensitivity")
    log.info("-" * 80)
    
    duration_scales = [0.5, 0.75, 1.0, 1.5, 2.0]
    duration_variants = []
    
    for scale in duration_scales:
        variant_name = f"{base_name}_dur_{int(scale*100)}"
        variant_path = create_variant_instance(
            base_instance_path,
            variant_name,
            duration_scales={'A': scale, 'B': scale, 'C': scale, 'D': scale}
        )
        duration_variants.append((variant_name, variant_path, f"Durations={int(scale*100)}%"))
    
    # EXPERIMENT 3: Station capacity sensitivity
    log.info("\n[EXP 3] Station Capacity Sensitivity")
    log.info("-" * 80)
    
    capacity_scales = [0.5, 1.0, 1.5, 2.0]
    capacity_variants = []
    
    for scale in capacity_scales:
        variant_name = f"{base_name}_cap_{int(scale*100)}"
        # Get all maintenance airports from baseline
        maint_airports = {k: scale for k in baseline_capacities.keys()}
        variant_path = create_variant_instance(
            base_instance_path,
            variant_name,
            capacity_scales=maint_airports
        )
        capacity_variants.append((variant_name, variant_path, f"Capacity={int(scale*100)}%"))
    
    # Combine all variants
    all_variants = threshold_variants + duration_variants + capacity_variants
    
    # SOLVE ALL VARIANTS
    log.info(f"\n[SOLVING] Starting MILP solve for {len(all_variants)} variants...")
    log.info("-" * 80)
    
    baseline_model_size = None
    
    for exp_idx, (variant_name, variant_path, param_change_str) in enumerate(all_variants, 1):
        log.info(f"\n[{exp_idx}/{len(all_variants)}] {variant_name}")
        log.info(f"  Parameter: {param_change_str}")
        
        try:
            # Build and solve MILP
            start_time = time.time()
            scheduler = MILP_Sheduler(variant_path)
            model = scheduler.build_model(use_maintenance=True)
            
            # Count variables and constraints
            from pyomo.environ import Var, Constraint
            n_var = len(list(model.component_data_objects(ctype=Var)))
            n_con = len(list(model.component_data_objects(ctype=Constraint)))
            
            if baseline_model_size is None:
                baseline_model_size = (n_var, n_con)
            
            model_size_ratio = (n_var + n_con) / (baseline_model_size[0] + baseline_model_size[1])
            
            log.info(f"  Model: {n_var} vars, {n_con} constraints (ratio: {model_size_ratio:.2f}x)")
            
            # Solve.  MILP_Sheduler.solve() returns a summary dict
            # (status, n_vars, n_cons, gap, cpu, obj); it raises when the solver
            # cannot load a solution (i.e. genuinely infeasible).
            solver_status = "unknown"
            objective = None
            feasible = False
            infeasibility_reason = None
            try:
                summary = scheduler.solve(solver_name=solver_name, time_limit=time_limit)
                runtime = time.time() - start_time
                solver_status = str(summary.get('status', 'unknown'))
                objective = summary.get('obj')
                feasible = objective is not None and 'optimal' in solver_status.lower()
                if feasible:
                    log.info(f"  ✓ {solver_status.upper()}: objective = {objective:.1f}, time = {runtime:.2f}s")
                elif 'infeasible' in solver_status.lower():
                    infeasibility_reason = "MILP infeasible"
                    log.warning(f"  ✗ INFEASIBLE, time = {runtime:.2f}s")
                else:
                    infeasibility_reason = f"status={solver_status}"
                    log.warning(f"  ? {solver_status}, time = {runtime:.2f}s")
            except Exception as solve_exc:
                runtime = time.time() - start_time
                msg = str(solve_exc)
                if ('feasible solution was not found' in msg
                        or 'infeasible' in msg.lower()
                        or 'no solution' in msg.lower()):
                    solver_status = "infeasible"
                    feasible = False
                    infeasibility_reason = "MILP infeasible (no solution loadable)"
                    log.warning(f"  ✗ INFEASIBLE (solver could not load solution), time = {runtime:.2f}s")
                else:
                    raise
            
            result = SensitivityResult(
                base_instance=base_name,
                experiment_id=variant_name,
                parameter_set=param_change_str,
                param_change=param_change_str,
                n_var=n_var,
                n_con=n_con,
                model_size_ratio=model_size_ratio,
                runtime_s=runtime,
                solver_status=solver_status,
                objective=objective,
                feasible=feasible,
                infeasibility_reason=infeasibility_reason
            )
            results.append(result)
            
        except Exception as e:
            log.error(f"  ✗ ERROR: {e}")
            result = SensitivityResult(
                base_instance=base_name,
                experiment_id=variant_name,
                parameter_set=param_change_str,
                param_change=param_change_str,
                n_var=0,
                n_con=0,
                model_size_ratio=0,
                runtime_s=0,
                solver_status="error",
                objective=None,
                feasible=False,
                infeasibility_reason=f"Exception: {str(e)[:50]}"
            )
            results.append(result)
    
    return results

def write_sensitivity_results(results: List[SensitivityResult], output_path: Path):
    """Write sensitivity results to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'base_instance', 'experiment_id', 'parameter_set', 'param_change',
            'n_var', 'n_con', 'model_size_ratio',
            'runtime_s', 'solver_status', 'objective', 'feasible', 'infeasibility_reason'
        ])
        writer.writeheader()
        for result in results:
            writer.writerow({
                'base_instance': result.base_instance,
                'experiment_id': result.experiment_id,
                'parameter_set': result.parameter_set,
                'param_change': result.param_change,
                'n_var': result.n_var,
                'n_con': result.n_con,
                'model_size_ratio': f"{result.model_size_ratio:.3f}",
                'runtime_s': f"{result.runtime_s:.2f}",
                'solver_status': result.solver_status,
                'objective': f"{result.objective:.1f}" if result.objective else "N/A",
                'feasible': result.feasible,
                'infeasibility_reason': result.infeasibility_reason or "N/A"
            })
    
    log.info(f"\nResults written to: {output_path}")

def main():
    """Run the multi-instance sensitivity analysis pipeline.

    The analysis is repeated over several small exact-feasible instances so the
    dominant-parameter conclusions can be checked for consistency across
    different maintenance topologies rather than resting on a single instance.
    """

    # Curated exact-feasible base instances (the same four the computational
    # section certifies to optimality; small enough for HiGHS).
    base_instances = [
        Path("data/instances/ABCD_no_maint_test.json"),
        Path("data/instances/ABCD_near_threshold_test.json"),
        Path("data/instances/ABCD_capacity_bottleneck_test.json"),
        Path("data/instances/ABCD_check_hierarchy_test.json"),
    ]

    all_results: List[SensitivityResult] = []
    for base_instance in base_instances:
        if not base_instance.exists():
            log.warning(f"Skipping missing base instance: {base_instance}")
            continue
        all_results.extend(
            run_sensitivity_experiment(base_instance, solver_name='highs', time_limit=120)
        )

    if not all_results:
        log.error("No base instances found; nothing to write.")
        return

    # Write results
    output_csv = Path("results/tables/step5_sensitivity_analysis.csv")
    write_sensitivity_results(all_results, output_csv)

    # Print summary
    log.info("\n" + "=" * 80)
    log.info("SENSITIVITY ANALYSIS SUMMARY (all instances)")
    log.info("=" * 80)

    feasible_count = sum(1 for r in all_results if r.feasible)
    log.info(f"\n✓ Feasible: {feasible_count}/{len(all_results)}")
    log.info(f"✗ Infeasible/other: {len(all_results) - feasible_count}/{len(all_results)}")

    runtimes = [r.runtime_s for r in all_results if r.runtime_s > 0]
    if runtimes:
        log.info(f"\nRuntime range: {min(runtimes):.2f}s – {max(runtimes):.2f}s")
        log.info(f"Average runtime: {sum(runtimes)/len(runtimes):.2f}s")

    log.info("\n✓ Sensitivity analysis complete!")
    log.info(f"✓ Output: {output_csv}")

if __name__ == '__main__':
    main()
