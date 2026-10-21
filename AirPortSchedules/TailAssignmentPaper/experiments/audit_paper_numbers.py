"""Audit section 07 numbers and benchmark provenance against source artifacts."""
import argparse
import csv
import hashlib
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEX = (ROOT / "paper/sections/07_computational.tex").read_text(encoding="utf8")
CSV = ROOT / "results/tables/a_only_policy_matched_20261020.csv"
METADATA = CSV.with_suffix(".metadata.json")
DATA_DIR = ROOT / "data/five_method_longflight_e14_e21_compact"
MANIFEST = DATA_DIR / "manifest.json"
PREFIX_LP_CSV = ROOT / "results/tables/a_only_hour_prefix_lp_20261020.csv"
PREFIX_MIP_CSV = ROOT / "results/tables/a_only_hour_prefix_milp_p5_p10_20261020.csv"
MULTISEED_CSV = ROOT / "results/tables/a_only_multiseed_20261020.csv"
MULTISEED_METADATA = MULTISEED_CSV.with_suffix(".metadata.json")
PRUNING_CSV = ROOT / "results/tables/a_check_pruning_20261020.csv"
PRUNING_METADATA = PRUNING_CSV.with_suffix(".metadata.json")
LABELS = {
    "legacy_paper_c13": "Legacy paper",
    "legacy_endpoint_split": "Legacy split",
    "legacy_corrected_strengthened": "Legacy corrected",
    "event_based_optimized": "Event optimized",
    "event_based_flex": "Event flex",
}

with CSV.open(encoding="utf8", newline="") as handle:
    rows = list(csv.DictReader(handle))
performance = [row for row in rows if row["case"].startswith("perf_")]
problems = []
warnings = []


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_data_provenance():
    if not MANIFEST.is_file():
        problems.append(f"A-only suite manifest not found: {MANIFEST.relative_to(ROOT)}")
        return

    manifest = json.loads(MANIFEST.read_text(encoding="utf8"))
    if manifest.get("description") != "A-only five-method correctness and performance suite":
        problems.append("selected data manifest does not identify the five-method A-only suite")

    expected_methods = set(manifest.get("methods", ()))
    expected_cases = {
        Path(item["file"]).stem: item
        for item in manifest.get("performance_grid", ())
    }
    observed_cases = {row["case"] for row in performance}
    if observed_cases != set(expected_cases):
        problems.append(
            "CSV performance cases differ from the selected manifest: "
            f"csv={sorted(observed_cases)}, manifest={sorted(expected_cases)}"
        )

    for case, grid_item in expected_cases.items():
        input_path = DATA_DIR / grid_item["file"]
        if not input_path.is_file():
            problems.append(f"manifest input is missing: {input_path.relative_to(ROOT)}")
            continue
        data = json.loads(input_path.read_text(encoding="utf8"))
        if data.get("Maintenance_Families") != ["A"]:
            problems.append(f"{case}: input does not declare exactly A-only maintenance")
        observed_h = max(int(float(flight[4]) // 1440) + 1 for flight in data["Flights"])
        if len(data["Aircrafts"]) != int(grid_item["P"]):
            problems.append(
                f"{case}: JSON dimensions disagree with the manifest "
                f"(P={len(data['Aircrafts'])}, H={observed_h})"
            )
        case_rows = [row for row in performance if row["case"] == case]
        methods = {row["formulation"] for row in case_rows}
        if methods != expected_methods or len(case_rows) != len(expected_methods):
            problems.append(
                f"{case}: CSV methods/count differ from manifest "
                f"(methods={sorted(methods)}, rows={len(case_rows)})"
            )
        for row in case_rows:
            if row.get("file") != input_path.name:
                problems.append(f"{case}/{row['formulation']}: CSV input filename mismatch")
            if (
                int(row["P"]) != len(data["Aircrafts"])
                or int(row["F"]) != len(data["Flights"])
                or int(row["H"]) != observed_h
            ):
                problems.append(f"{case}/{row['formulation']}: CSV dimensions mismatch")

    if not METADATA.is_file():
        warnings.append(
            "run provenance sidecar is missing; existing CSV is historical/unverified "
            "for source and input hashes"
        )
        return

    metadata = json.loads(METADATA.read_text(encoding="utf8"))
    runs = metadata.get("runs", [])
    if not runs:
        problems.append("provenance sidecar contains no run records")
        return
    latest = runs[-1]
    if latest.get("result_csv_sha256") != sha256(CSV):
        problems.append("latest provenance record does not hash the current result CSV")
    configuration = latest.get("configuration", {})
    if configuration.get("solver") != "cplexamp":
        problems.append("matched result sidecar does not identify cplexamp")
    if configuration.get("solver_version") != "12.6":
        problems.append("matched result sidecar does not identify CPLEX 12.6")
    if configuration.get("threads") != 1:
        problems.append("matched result sidecar does not record one solver thread")
    if configuration.get("legacy_max_hour_check_deferral_days") != 0:
        problems.append("matched result sidecar does not record zero-day legacy deferral")
    if configuration.get("lp_relaxation", False) is not False:
        problems.append("matched result sidecar is not an integer-model run")
    for case, grid_item in expected_cases.items():
        relative = str((DATA_DIR / grid_item["file"]).relative_to(ROOT))
        record = latest.get("inputs", {}).get(relative)
        if record is None:
            problems.append(f"latest provenance record omits {relative}")
            continue
        input_path = ROOT / relative
        if record.get("sha256") != sha256(input_path):
            problems.append(f"input hash mismatch in provenance record: {relative}")
        if record.get("declared_maintenance_families") != ["A"]:
            problems.append(f"provenance record does not confirm A-only input: {relative}")

match = re.search(r"label\{tab:longflight_results\}(.*?)\\bottomrule", TEX, re.DOTALL)
if match is None:
    problems.append("long-flight result table not found")
else:
    table = match.group(1)
    for row in performance:
        replay = (
            "PASS" if row["replay_status"] == "pass"
            else row["replay_violation_count"] or "--"
        )
        expected = (
            f"{row['P']} & {row['H']} & {row['F']} & {LABELS[row['formulation']]} & "
            f"{row['status']} & {replay} & {int(float(row['objective']))} & "
            f"{float(row['cpu_s']):.2f} & {float(row['wall_s']):.2f} & "
            f"{row['vars']} & {row['constraints']}"
        )
        if expected not in table:
            problems.append(f"missing result row: {expected}")

summary_match = re.search(
    r"label\{tab:longflight_aggregates\}(.*?)\\bottomrule", TEX, re.DOTALL
)
if summary_match is None:
    problems.append("long-flight aggregate table not found")
else:
    summary_table = summary_match.group(1)
    cases = {row["case"] for row in performance}
    common_optimal_cases = {
        case
        for case in cases
        if {
            row["formulation"]
            for row in performance
            if row["case"] == case and row["status"] == "optimal"
        } == set(LABELS)
    }
    for formulation, label in LABELS.items():
        group = [row for row in performance if row["formulation"] == formulation]
        optimal = [row for row in group if row["status"] == "optimal"]
        paired = [row for row in group if row["case"] in common_optimal_cases]
        expected = (
            f"{label} & {len(optimal)}/{len(group)} & "
            f"{sum(float(row['vars']) for row in group)/len(group):.1f} & "
            f"{sum(float(row['constraints']) for row in group)/len(group):.1f} & "
            f"{sum(float(row['build_s']) for row in paired)/len(paired):.3f} & "
            f"{sum(float(row['cpu_s']) for row in paired)/len(paired):.3f} & "
            f"{sum(float(row['wall_s']) for row in paired)/len(paired):.3f}"
        )
        if expected not in summary_table:
            problems.append(f"missing aggregate row: {expected}")

for formulation, expected_total in (
    ("legacy_paper_c13", 663),
    ("legacy_endpoint_split", 183),
):
    total = sum(
        int(row["replay_violation_count"] or 0)
        for row in performance
        if row["formulation"] == formulation
    )
    if total != expected_total:
        problems.append(f"replay violation total {formulation}: expected {expected_total}, got {total}")

prefix_match = re.search(
    r"label\{tab:hour_prefix_ablation\}(.*?)\\bottomrule", TEX, re.DOTALL
)
if prefix_match is None:
    problems.append("cumulative-prefix ablation table not found")
elif not PREFIX_LP_CSV.is_file() or not PREFIX_MIP_CSV.is_file():
    problems.append("cumulative-prefix ablation CSVs are missing")
else:
    with PREFIX_LP_CSV.open(encoding="utf8", newline="") as handle:
        prefix_lp_rows = list(csv.DictReader(handle))
    with PREFIX_MIP_CSV.open(encoding="utf8", newline="") as handle:
        prefix_mip_rows = list(csv.DictReader(handle))
    prefix_table = prefix_match.group(1)
    for case, fleet, horizon, flights in (
        ("perf_p=5_h=29", 5, 30, 74),
        ("perf_p=5_h=49", 5, 48, 80),
        ("perf_p=10_h=29", 10, 30, 146),
        ("perf_p=10_h=49", 10, 49, 160),
    ):
        lp_by_method = {
            row["formulation"]: row
            for row in prefix_lp_rows
            if row["case"] == case
        }
        mip_by_method = {
            row["formulation"]: row
            for row in prefix_mip_rows
            if row["case"] == case
        }
        required_lp = (
            "legacy_corrected_strengthened",
            "legacy_strict_interval",
            "legacy_hour_prefix",
        )
        required_mip = required_lp
        if any(name not in lp_by_method for name in required_lp) or any(
            name not in mip_by_method for name in required_mip
        ):
            problems.append(f"{case}: missing prefix-ablation result rows")
            continue
        if any(lp_by_method[name]["status"] != "optimal" for name in required_lp):
            problems.append(f"{case}: prefix LP ablation is not fully optimal")
            continue
        if any(mip_by_method[name]["status"] != "optimal" for name in required_mip):
            problems.append(f"{case}: prefix MIP ablation is not fully optimal")
            continue

        exact_lp = float(lp_by_method["legacy_corrected_strengthened"]["objective"])
        interval_lp = float(lp_by_method["legacy_strict_interval"]["objective"])
        prefix_lp = float(lp_by_method["legacy_hour_prefix"]["objective"])
        if abs(interval_lp - prefix_lp) > 1e-6:
            problems.append(f"{case}: interval and prefix LP objectives differ")

        mip_objectives = [float(mip_by_method[name]["objective"]) for name in required_mip]
        if max(mip_objectives) - min(mip_objectives) > 1e-6:
            problems.append(f"{case}: exact-state, interval, and prefix MIP objectives differ")

        interval_model = mip_by_method["legacy_strict_interval"]
        prefix_model = mip_by_method["legacy_hour_prefix"]
        prefix_time = float(prefix_model["wall_s"])
        expected = (
            f"{fleet} & {horizon} & {flights} & {exact_lp:.2f} & "
            f"{interval_lp:.2f} & {prefix_lp:.2f} & {mip_objectives[0]:.0f} & "
            f"{interval_model['vars']}/{interval_model['constraints']} & "
            f"{prefix_model['vars']}/{prefix_model['constraints']} & {prefix_time:.2f}"
        )
        if expected not in prefix_table:
            problems.append(f"{case}: missing prefix table row '{expected}'")

    for result_path in (PREFIX_LP_CSV, PREFIX_MIP_CSV):
        sidecar = result_path.with_suffix(".metadata.json")
        if not sidecar.is_file():
            problems.append(f"prefix provenance sidecar is missing: {sidecar.name}")
            continue
        metadata = json.loads(sidecar.read_text(encoding="utf8"))
        runs = metadata.get("runs", [])
        if not runs:
            problems.append(f"prefix provenance sidecar has no run records: {sidecar.name}")
            continue
        latest = runs[-1]
        if latest.get("result_csv_sha256") != sha256(result_path):
            problems.append(f"prefix provenance does not hash {result_path.name}")
        for relative, record in latest.get("inputs", {}).items():
            input_path = ROOT / relative
            if not input_path.is_file():
                problems.append(f"prefix input is missing: {relative}")
            elif record.get("sha256") != sha256(input_path):
                problems.append(f"prefix input hash mismatch: {relative}")
            if record.get("declared_maintenance_families") != ["A"]:
                problems.append(f"prefix input is not declared A-only: {relative}")

multiseed_match = re.search(
    r"label\{tab:a_only_multiseed\}(.*?)\\bottomrule", TEX, re.DOTALL
)
if multiseed_match is None:
    problems.append("three-seed A-only table not found")
elif not MULTISEED_CSV.is_file():
    problems.append("three-seed A-only CSV is missing")
else:
    with MULTISEED_CSV.open(encoding="utf8", newline="") as handle:
        multiseed_rows = list(csv.DictReader(handle))
    expected_cells = ((5, 30, 74), (5, 48, 80), (10, 30, 146), (10, 49, 160))
    corrected_methods = (
        "legacy_corrected_strengthened",
        "event_based_optimized",
        "event_based_flex",
    )
    multiseed_table = multiseed_match.group(1)
    for fleet, horizon, flights in expected_cells:
        cell_rows = [
            row for row in multiseed_rows
            if int(row["P"]) == fleet and int(row["H"]) == horizon
        ]
        if len(cell_rows) != 15:
            problems.append(
                f"multiseed P={fleet},H={horizon}: expected 15 rows, got {len(cell_rows)}"
            )
            continue
        if any(row["status"] != "optimal" for row in cell_rows):
            problems.append(f"multiseed P={fleet},H={horizon}: non-optimal replicate found")
        if any(
            row["replay_status"] != ("fail" if row["formulation"] in LABELS and row["formulation"] in {"legacy_paper_c13", "legacy_endpoint_split"} else "pass")
            for row in cell_rows
        ):
            problems.append(f"multiseed P={fleet},H={horizon}: replay status mismatch")

        by_case = {}
        for row in cell_rows:
            by_case.setdefault(row["case"], {})[row["formulation"]] = row
        for case, methods in by_case.items():
            if any(name not in methods for name in corrected_methods):
                problems.append(f"multiseed {case}: missing corrected-method result")
                continue
            objectives = [float(methods[name]["objective"]) for name in corrected_methods]
            if max(objectives) - min(objectives) > 1e-6:
                problems.append(f"multiseed {case}: corrected-method objectives differ")

        rows_by_method = {
            name: [row for row in cell_rows if row["formulation"] == name]
            for name in corrected_methods
        }
        objectives = [float(row["objective"]) for row in rows_by_method[corrected_methods[0]]]
        wall_summaries = []
        for name in corrected_methods:
            walls = [float(row["wall_s"]) for row in rows_by_method[name]]
            wall_summaries.append(
                f"${statistics.mean(walls):.3f}\\pm{statistics.stdev(walls):.3f}$"
            )
        expected = (
            f"{fleet} & {horizon} & {flights} & {statistics.mean(objectives):.1f} & "
            + " & ".join(wall_summaries)
        )
        if expected not in multiseed_table:
            problems.append(f"P={fleet},H={horizon}: missing multiseed row '{expected}'")

    if not MULTISEED_METADATA.is_file():
        problems.append("three-seed A-only provenance sidecar is missing")
    else:
        metadata = json.loads(MULTISEED_METADATA.read_text(encoding="utf8"))
        runs = metadata.get("runs", [])
        if not runs:
            problems.append("three-seed provenance sidecar has no run records")
        else:
            latest = runs[-1]
            if latest.get("result_csv_sha256") != sha256(MULTISEED_CSV):
                problems.append("three-seed sidecar does not hash the current CSV")
            inputs = latest.get("inputs", {})
            if len(inputs) != 12:
                problems.append(f"three-seed sidecar expected 12 inputs, got {len(inputs)}")
            for relative, record in inputs.items():
                input_path = ROOT / relative
                if not input_path.is_file():
                    problems.append(f"three-seed input is missing: {relative}")
                    continue
                if record.get("sha256") != sha256(input_path):
                    problems.append(f"three-seed input hash mismatch: {relative}")
                if record.get("declared_maintenance_families") != ["A"]:
                    problems.append(f"three-seed input is not declared A-only: {relative}")

pruning_match = re.search(
    r"label\{tab:a_check_pruning\}(.*?)\\bottomrule", TEX, re.DOTALL
)
if pruning_match is None:
    problems.append("A-check pruning table not found")
elif not PRUNING_CSV.is_file() or not PRUNING_METADATA.is_file():
    problems.append("A-check pruning result CSV or metadata sidecar is missing")
else:
    with PRUNING_CSV.open(encoding="utf8", newline="") as handle:
        pruning_rows = {row["variant"]: row for row in csv.DictReader(handle)}
    baseline = pruning_rows.get("baseline")
    pruned = pruning_rows.get("pruned")
    if baseline is None or pruned is None:
        problems.append("A-check pruning CSV must contain baseline and pruned rows")
    else:
        expected_values = {
            "baseline": ("optimal", "600.0", "12", "88", "187", "pass", "0"),
            "pruned": ("optimal", "600.0", "0", "76", "172", "pass", "0"),
        }
        for name, row in (("baseline", baseline), ("pruned", pruned)):
            expected = expected_values[name]
            observed = tuple(
                row[key]
                for key in (
                    "status", "objective", "z_vars", "vars", "constraints",
                    "replay_status", "replay_violations",
                )
            )
            if observed != expected:
                problems.append(f"A-check pruning {name} row mismatch: {observed}")
            expected_tex = (
                f"{name.title()} & {row['status']} & {row['objective']} & "
                f"{row['z_vars']} & {row['vars']} & {row['constraints']} & "
                f"{float(row['wall_s']):.3f} & {row['replay_status'].upper()}"
            )
            if expected_tex not in pruning_match.group(1):
                problems.append(f"A-check pruning table missing '{expected_tex}'")

    metadata = json.loads(PRUNING_METADATA.read_text(encoding="utf8"))
    if metadata.get("results_csv_sha256") != sha256(PRUNING_CSV):
        problems.append("A-check pruning metadata does not hash its result CSV")
    if not all(
        bound.get("precondition_holds") is True
        for bound in metadata.get("profile", {}).get("tail_bounds", {}).values()
    ):
        problems.append("A-check pruning metadata does not verify all tail preconditions")

for filename in (
    "ordered_a_wall_vs_horizon_extended_p10.png",
    "ordered_a_cpu_vs_horizon_extended_p10.png",
    "a_variables_vs_fleet_extended_h30.png",
    "a_constraints_vs_fleet_extended_h30.png",
    "a_cpu_vs_fleet_extended_h30.png",
    "a_wall_vs_fleet_extended_h30.png",
):
    if not (ROOT / "paper/figures" / filename).is_file():
        problems.append(f"missing generated figure: {filename}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-provenance",
        action="store_true",
        help="Fail when the result CSV lacks a valid run-provenance sidecar.",
    )
    args = parser.parse_args()
    audit_data_provenance()
    from report_uniform_study import load_and_audit, render

    uniform_main = load_and_audit(ROOT / "results/tables/uniform_flexible_main_20261021.csv")
    uniform_night = load_and_audit(ROOT / "results/tables/uniform_night_subset_20261021.csv")
    uniform_seeds = load_and_audit(ROOT / "results/tables/uniform_flexible_multiseed_20261021.csv")
    repaired_lp = load_and_audit(ROOT / "results/tables/repaired_hour_prefix_lp_20261021.csv", allow_day_boundary=True)
    repaired_mip = load_and_audit(ROOT / "results/tables/repaired_hour_prefix_milp_20261021.csv", allow_day_boundary=True)
    uniform_tex = ROOT / "paper/sections/07_uniform_results.tex"
    if uniform_tex.read_text(encoding="ascii") != render(uniform_main, uniform_night, uniform_seeds, repaired_lp, repaired_mip):
        problems.append("uniform generated tables differ from audited result artifacts")
    for filename in ("uniform_variables_h30_20261021.png", "uniform_wall_h30_20261021.png"):
        if not (ROOT / "paper/figures" / filename).is_file():
            problems.append(f"missing uniform figure: {filename}")
    if args.require_provenance:
        problems.extend(warnings)
    if problems:
        print("\n".join(problems))
        raise SystemExit(1)
    print("SECTION 07 TABLES AND A-ONLY INPUTS MATCH")
    for warning in warnings:
        print(f"WARNING: {warning}")


if __name__ == "__main__":
    main()
