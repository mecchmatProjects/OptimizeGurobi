"""Phase-2 event-maintenance trial comparator.

Generates side-by-side build/solve metrics for:
1) legacy maintenance blocks
2) event scaffold + strict bridge
3) event scaffold + strict bridge + event-only block/capacity
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path
from typing import Iterable
from contextlib import redirect_stdout
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model import run_milp


def one_run(instance: Path, solver: str, time_limit: int, out_dir: Path, label: str, quiet: bool = False, **kwargs):
    out_dir.mkdir(parents=True, exist_ok=True)
    txt = out_dir / f"{instance.stem}_{label}.txt"
    try:
        if quiet:
            with redirect_stdout(io.StringIO()):
                _, summary = run_milp(
                    data_path=str(instance),
                    solver=solver,
                    tee=False,
                    time_limit=time_limit,
                    out_txt=str(txt),
                    show_gantt=False,
                    **kwargs,
                )
        else:
            _, summary = run_milp(
                data_path=str(instance),
                solver=solver,
                tee=False,
                time_limit=time_limit,
                out_txt=str(txt),
                show_gantt=False,
                **kwargs,
            )
        return {
            "instance": instance.name,
            "config": label,
            "status": summary.get("status"),
            "obj": summary.get("obj"),
            "n_vars": summary.get("n_vars"),
            "n_cons": summary.get("n_cons"),
            "gap": summary.get("gap"),
            "cpu": summary.get("cpu"),
            "report": str(txt),
        }
    except Exception as exc:  # pragma: no cover
        return {
            "instance": instance.name,
            "config": label,
            "status": "ERROR",
            "obj": None,
            "n_vars": None,
            "n_cons": None,
            "gap": None,
            "cpu": None,
            "report": str(txt),
            "error": str(exc),
        }


def compare_one_instance(instance: Path, solver: str, time_limit: int, out_dir: Path, quiet: bool = False):
    rows = []
    rows.append(
        one_run(
            instance,
            solver,
            time_limit,
            out_dir,
            "legacy",
            quiet=quiet,
            use_event_maintenance=False,
            use_event_bridge_strict=False,
            use_event_only_block_capacity=False,
        )
    )
    rows.append(
        one_run(
            instance,
            solver,
            time_limit,
            out_dir,
            "event_strict_bridge",
            quiet=quiet,
            use_event_maintenance=True,
            use_event_bridge_strict=True,
            use_event_only_block_capacity=False,
        )
    )
    rows.append(
        one_run(
            instance,
            solver,
            time_limit,
            out_dir,
            "event_only_block_capacity",
            quiet=quiet,
            use_event_maintenance=True,
            use_event_bridge_strict=True,
            use_event_only_block_capacity=True,
        )
    )
    return rows


def write_detailed_csv(path: Path, rows: Iterable[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "instance",
                "config",
                "status",
                "obj",
                "n_vars",
                "n_cons",
                "gap",
                "cpu",
                "report",
                "error",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _f(value, default=0.0):
    return default if value is None else float(value)


def build_delta_rows(rows: list[dict]):
    by_instance: dict[str, dict[str, dict]] = {}
    for row in rows:
        by_instance.setdefault(row["instance"], {})[row["config"]] = row

    deltas = []
    for instance, cfg in sorted(by_instance.items()):
        legacy = cfg.get("legacy", {})
        strict = cfg.get("event_strict_bridge", {})
        event_only = cfg.get("event_only_block_capacity", {})

        deltas.append(
            {
                "instance": instance,
                "status_legacy": legacy.get("status"),
                "status_event_strict": strict.get("status"),
                "status_event_only": event_only.get("status"),
                "vars_legacy": legacy.get("n_vars"),
                "vars_event_strict": strict.get("n_vars"),
                "vars_event_only": event_only.get("n_vars"),
                "cons_legacy": legacy.get("n_cons"),
                "cons_event_strict": strict.get("n_cons"),
                "cons_event_only": event_only.get("n_cons"),
                "d_vars_strict_minus_legacy": _f(strict.get("n_vars")) - _f(legacy.get("n_vars")),
                "d_cons_strict_minus_legacy": _f(strict.get("n_cons")) - _f(legacy.get("n_cons")),
                "d_vars_event_only_minus_legacy": _f(event_only.get("n_vars")) - _f(legacy.get("n_vars")),
                "d_cons_event_only_minus_legacy": _f(event_only.get("n_cons")) - _f(legacy.get("n_cons")),
                "obj_legacy": legacy.get("obj"),
                "obj_event_strict": strict.get("obj"),
                "obj_event_only": event_only.get("obj"),
                "cpu_legacy": legacy.get("cpu"),
                "cpu_event_strict": strict.get("cpu"),
                "cpu_event_only": event_only.get("cpu"),
            }
        )
    return deltas


def write_delta_csv(path: Path, delta_rows: Iterable[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "instance",
                "status_legacy",
                "status_event_strict",
                "status_event_only",
                "vars_legacy",
                "vars_event_strict",
                "vars_event_only",
                "cons_legacy",
                "cons_event_strict",
                "cons_event_only",
                "d_vars_strict_minus_legacy",
                "d_cons_strict_minus_legacy",
                "d_vars_event_only_minus_legacy",
                "d_cons_event_only_minus_legacy",
                "obj_legacy",
                "obj_event_strict",
                "obj_event_only",
                "cpu_legacy",
                "cpu_event_strict",
                "cpu_event_only",
            ],
        )
        writer.writeheader()
        for row in delta_rows:
            writer.writerow(row)


def write_status_summary_csv(path: Path, rows: list[dict]):
    configs = ["legacy", "event_strict_bridge", "event_only_block_capacity"]
    statuses = sorted({(r.get("status") or "UNKNOWN") for r in rows})

    by_cfg = {cfg: {status: 0 for status in statuses} for cfg in configs}
    for r in rows:
        cfg = r.get("config")
        status = r.get("status") or "UNKNOWN"
        if cfg in by_cfg:
            by_cfg[cfg][status] = by_cfg[cfg].get(status, 0) + 1

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = ["config", "total_runs"] + [f"status_{s}" for s in statuses]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for cfg in configs:
            row = {"config": cfg, "total_runs": sum(by_cfg[cfg].values())}
            for s in statuses:
                row[f"status_{s}"] = by_cfg[cfg].get(s, 0)
            writer.writerow(row)


def _numeric(values: list):
    out = []
    for v in values:
        if v is None or v == "":
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            continue
    return out


def _tex_escape(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\textbackslash{}")
        .replace("_", "\\_")
        .replace("%", "\\%")
        .replace("&", "\\&")
        .replace("#", "\\#")
    )


def _fmt_float(v):
    if v is None or v == "":
        return "-"
    try:
        return f"{float(v):.3f}"
    except (TypeError, ValueError):
        return str(v)


def write_aggregate_summary_csv(path: Path, delta_rows: list[dict]):
    metrics = [
        "d_vars_strict_minus_legacy",
        "d_cons_strict_minus_legacy",
        "d_vars_event_only_minus_legacy",
        "d_cons_event_only_minus_legacy",
        "cpu_legacy",
        "cpu_event_strict",
        "cpu_event_only",
    ]

    rows = []
    for metric in metrics:
        vals = _numeric([r.get(metric) for r in delta_rows])
        rows.append(
            {
                "metric": metric,
                "count": len(vals),
                "mean": mean(vals) if vals else None,
                "median": median(vals) if vals else None,
                "min": min(vals) if vals else None,
                "max": max(vals) if vals else None,
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["metric", "count", "mean", "median", "min", "max"],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_latex_tables(path: Path, delta_rows: list[dict], aggregate_rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append("% Auto-generated by experiments/phase2_event_trial_compare.py")
    lines.append("\\begin{table}[ht]")
    lines.append("\\centering")
    lines.append("\\caption{Phase 2 per-instance structural deltas}")
    lines.append("\\begin{tabular}{lrrrr}")
    lines.append("\\toprule")
    lines.append("Instance & $\\Delta$Vars (strict) & $\\Delta$Cons (strict) & $\\Delta$Vars (event-only) & $\\Delta$Cons (event-only) \\\\")
    lines.append("\\midrule")
    for r in delta_rows:
        lines.append(
            f"{_tex_escape(r.get('instance'))} & "
            f"{_fmt_float(r.get('d_vars_strict_minus_legacy'))} & "
            f"{_fmt_float(r.get('d_cons_strict_minus_legacy'))} & "
            f"{_fmt_float(r.get('d_vars_event_only_minus_legacy'))} & "
            f"{_fmt_float(r.get('d_cons_event_only_minus_legacy'))} \\\\" 
        )
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")
    lines.append("")
    lines.append("\\begin{table}[ht]")
    lines.append("\\centering")
    lines.append("\\caption{Phase 2 aggregate delta statistics}")
    lines.append("\\begin{tabular}{lrrrrr}")
    lines.append("\\toprule")
    lines.append("Metric & Count & Mean & Median & Min & Max \\\\")
    lines.append("\\midrule")
    for r in aggregate_rows:
        lines.append(
            f"{_tex_escape(r.get('metric'))} & "
            f"{r.get('count')} & "
            f"{_fmt_float(r.get('mean'))} & "
            f"{_fmt_float(r.get('median'))} & "
            f"{_fmt_float(r.get('min'))} & "
            f"{_fmt_float(r.get('max'))} \\\\" 
        )
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_markdown_report(
    path: Path,
    detailed_csv: Path,
    delta_csv: Path,
    status_summary_csv: Path,
    aggregate_csv: Path,
    delta_rows: list[dict],
):
    path.parent.mkdir(parents=True, exist_ok=True)

    total_instances = len(delta_rows)
    error_instances = sum(
        1
        for r in delta_rows
        if "ERROR" in [r.get("status_legacy"), r.get("status_event_strict"), r.get("status_event_only")]
    )

    lines = []
    lines.append("# Phase 2 Event-Maintenance Trial Summary")
    lines.append("")
    lines.append(f"- Instances processed: {total_instances}")
    lines.append(f"- Instances with at least one ERROR status: {error_instances}")
    lines.append("")
    lines.append("## Generated Artifacts")
    lines.append("")
    lines.append(f"- Detailed comparison CSV: {detailed_csv}")
    lines.append(f"- Delta CSV: {delta_csv}")
    lines.append(f"- Status summary CSV: {status_summary_csv}")
    lines.append(f"- Aggregate summary CSV: {aggregate_csv}")
    lines.append("")
    lines.append("## Per-Instance Delta Snapshot")
    lines.append("")
    lines.append("| Instance | Status (legacy/strict/event-only) | dVars strict-legacy | dCons strict-legacy | dVars event-only-legacy | dCons event-only-legacy |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for r in delta_rows:
        status = f"{r.get('status_legacy')}/{r.get('status_event_strict')}/{r.get('status_event_only')}"
        lines.append(
            f"| {r.get('instance')} | {status} | {r.get('d_vars_strict_minus_legacy')} | {r.get('d_cons_strict_minus_legacy')} | {r.get('d_vars_event_only_minus_legacy')} | {r.get('d_cons_event_only_minus_legacy')} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def filter_delta_rows(delta_rows: list[dict], exclude_errors: bool):
    if not exclude_errors:
        return delta_rows
    filtered = []
    for r in delta_rows:
        statuses = [r.get("status_legacy"), r.get("status_event_strict"), r.get("status_event_only")]
        if "ERROR" in statuses:
            continue
        filtered.append(r)
    return filtered


def main():
    parser = argparse.ArgumentParser(description="Compare Phase-2 event migration configurations")
    parser.add_argument("--instance", default=None, help="Path to one JSON instance")
    parser.add_argument("--input-dir", default=None, help="Directory of JSON instances")
    parser.add_argument("--pattern", default="*.json", help="Glob pattern under --input-dir")
    parser.add_argument("--solver", default="cplex", help="Pyomo solver name")
    parser.add_argument("--time-limit", type=int, default=30, help="MILP time limit (s)")
    parser.add_argument(
        "--output",
        default="results/tables/phase2_event_trial_compare.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--delta-output",
        default="results/tables/phase2_event_trial_compare_delta.csv",
        help="Output CSV path for per-instance deltas",
    )
    parser.add_argument(
        "--status-summary-output",
        default="results/tables/phase2_event_trial_compare_status_summary.csv",
        help="Output CSV path for status-count summary by configuration",
    )
    parser.add_argument(
        "--aggregate-output",
        default="results/tables/phase2_event_trial_compare_aggregate.csv",
        help="Output CSV path for aggregate statistics of key deltas",
    )
    parser.add_argument(
        "--report-output",
        default="results/tables/phase2_event_trial_compare_report.md",
        help="Output markdown summary report path",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose per-run stdout from model solves while still writing report files",
    )
    parser.add_argument(
        "--exclude-errors",
        action="store_true",
        help="Exclude instances with any ERROR status from delta/aggregate/report artifacts",
    )
    parser.add_argument(
        "--instance-limit",
        type=int,
        default=None,
        help="If set, only process the first N selected instances (after sorting)",
    )
    parser.add_argument(
        "--latex-output",
        default="results/tables/phase2_event_trial_compare_tables.tex",
        help="Output LaTeX tables for thesis insertion",
    )
    args = parser.parse_args()

    if not args.instance and not args.input_dir:
        parser.error("Provide either --instance or --input-dir")

    instances: list[Path] = []
    if args.instance:
        instances.append(Path(args.instance))
    if args.input_dir:
        instances.extend(sorted(Path(args.input_dir).glob(args.pattern)))

    instances = sorted({p.resolve() for p in instances})
    if not instances:
        parser.error("No instances selected")
    if args.instance_limit is not None:
        if args.instance_limit <= 0:
            parser.error("--instance-limit must be positive")
        instances = instances[: args.instance_limit]

    out_csv = Path(args.output)
    delta_csv = Path(args.delta_output)
    status_summary_csv = Path(args.status_summary_output)
    aggregate_csv = Path(args.aggregate_output)
    report_md = Path(args.report_output)
    latex_tables = Path(args.latex_output)
    out_dir = out_csv.parent / "formulation_reports"

    rows = []
    for instance in instances:
        print(f"Running phase2 compare on {instance.name}")
        rows.extend(compare_one_instance(instance, args.solver, args.time_limit, out_dir, quiet=args.quiet))

    write_detailed_csv(out_csv, rows)
    delta_rows_raw = build_delta_rows(rows)
    delta_rows = filter_delta_rows(delta_rows_raw, exclude_errors=args.exclude_errors)
    write_delta_csv(delta_csv, delta_rows)
    write_status_summary_csv(status_summary_csv, rows)
    write_aggregate_summary_csv(aggregate_csv, delta_rows)
    aggregate_rows = []
    with aggregate_csv.open("r", encoding="utf-8", newline="") as fh:
        aggregate_rows = list(csv.DictReader(fh))
    write_latex_tables(latex_tables, delta_rows, aggregate_rows)
    write_markdown_report(
        report_md,
        out_csv,
        delta_csv,
        status_summary_csv,
        aggregate_csv,
        delta_rows,
    )

    print(f"Wrote comparison CSV to {out_csv}")
    print(f"Wrote delta CSV to {delta_csv}")
    print(f"Wrote status summary CSV to {status_summary_csv}")
    print(f"Wrote aggregate summary CSV to {aggregate_csv}")
    print(f"Wrote LaTeX tables to {latex_tables}")
    print(f"Wrote markdown report to {report_md}")


if __name__ == "__main__":
    main()
