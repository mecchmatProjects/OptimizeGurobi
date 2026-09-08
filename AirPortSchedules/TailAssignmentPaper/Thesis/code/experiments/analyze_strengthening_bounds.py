"""Summarise the strengthening bound study and emit thesis tables and figures.

Reads the raw per-run CSVs produced by ``run_strengthening_bounds.py`` and
writes, for each declared tier, a machine-readable summary plus the LaTeX
fragments and figures consumed by the strengthening chapter. Every reported
value is derived here from recorded runs, never transcribed by hand.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "tables"
FIGURES = ROOT / "Thesis" / "figures"
TABLES = ROOT / "Thesis" / "tables"

SOLVED = {"optimal", "feasible"}


def latex_escape(text):
    return str(text).replace("_", r"\_").replace("%", r"\%")


def write_table(path, caption, label, header, rows, column_format):
    lines = [
        r"\begin{table}[htbp]",
        r"\centering\small",
        rf"\caption{{{caption}}}",
        rf"\label{{{label}}}",
        rf"\begin{{tabular}}{{{column_format}}}",
        r"\toprule",
        " & ".join(header) + r" \\",
        r"\midrule",
    ]
    lines.extend(" & ".join(str(cell) for cell in row) + r" \\" for row in rows)
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def fmt(value, digits=2):
    if value is None or pd.isna(value):
        return "--"
    return f"{value:,.{digits}f}"


def load_tier(path, tier):
    frame = pd.read_csv(path)
    frame["tier"] = tier
    return frame


def solved(frame, mode, variant):
    subset = frame[(frame["mode"] == mode) & (frame["variant"] == variant)]
    return subset[subset["status"].isin(SOLVED)]


def build_pairs(frame):
    """One row per instance holding both variants' MILP and LP evidence."""
    records = []
    for instance, group in frame.groupby("instance"):
        record = {"instance": instance, "tier": group["tier"].iloc[0]}
        for variant in ("baseline", "combined"):
            for mode in ("lp", "milp"):
                rows = group[(group["variant"] == variant) & (group["mode"] == mode)]
                if rows.empty:
                    continue
                row = rows.iloc[0]
                prefix = f"{variant}_{mode}"
                record[f"{prefix}_status"] = row["status"]
                record[f"{prefix}_objective"] = row["objective"]
                record[f"{prefix}_dual"] = row["dual_bound"]
                record[f"{prefix}_primal"] = row["primal_bound"]
                record[f"{prefix}_gap"] = row["mip_gap"]
                record[f"{prefix}_runtime"] = row["runtime_s"]
                record[f"{prefix}_vars"] = row["variables"]
                record[f"{prefix}_cons"] = row["constraints"]
                record[f"{prefix}_z"] = row["z_variables"]
                record[f"{prefix}_flights"] = row["flights"]
                record[f"{prefix}_aircraft"] = row["aircraft"]
        heuristic = group[group["mode"] == "heuristic"]
        if not heuristic.empty:
            record["heuristic_objective"] = heuristic.iloc[0]["objective"]
            record["heuristic_primal"] = heuristic.iloc[0]["primal_bound"]
            record["heuristic_status"] = heuristic.iloc[0]["status"]
            record["heuristic_coverage"] = heuristic.iloc[0]["coverage"]
        records.append(record)
    return pd.DataFrame(records)


def tier_summary(pairs):
    rows = []
    for tier, group in pairs.groupby("tier", sort=False):
        for variant in ("baseline", "combined"):
            milp_status = group[f"{variant}_milp_status"]
            gaps = pd.to_numeric(group[f"{variant}_milp_gap"], errors="coerce")
            runtime = pd.to_numeric(group[f"{variant}_milp_runtime"], errors="coerce")
            rows.append({
                "tier": tier,
                "variant": variant,
                "instances": len(group),
                "flights": pd.to_numeric(group[f"{variant}_milp_flights"],
                                         errors="coerce").mean(),
                "variables": pd.to_numeric(group[f"{variant}_milp_vars"],
                                           errors="coerce").mean(),
                "constraints": pd.to_numeric(group[f"{variant}_milp_cons"],
                                             errors="coerce").mean(),
                "z_variables": pd.to_numeric(group[f"{variant}_milp_z"],
                                             errors="coerce").mean(),
                "optimal": int((milp_status == "optimal").sum()),
                "feasible_only": int((milp_status == "feasible").sum()),
                "mean_gap_pct": 100 * gaps.mean() if gaps.notna().any() else None,
                "max_gap_pct": 100 * gaps.max() if gaps.notna().any() else None,
                "mean_runtime_s": runtime.mean(),
                "median_runtime_s": runtime.median(),
            })
    return pd.DataFrame(rows)


def emit_model_size_table(summary):
    rows = []
    for tier, group in summary.groupby("tier", sort=False):
        base = group[group["variant"] == "baseline"].iloc[0]
        comb = group[group["variant"] == "combined"].iloc[0]
        reduction = (
            100 * (base["z_variables"] - comb["z_variables"]) / base["z_variables"]
            if base["z_variables"] else None
        )
        rows.append([
            latex_escape(tier), int(base["instances"]),
            fmt(base["flights"], 0),
            fmt(base["z_variables"], 0), fmt(comb["z_variables"], 0),
            fmt(base["constraints"], 0), fmt(comb["constraints"], 0),
            fmt(reduction, 1) + r"\%",
        ])
    write_table(
        TABLES / "strength_bounds_model_size.tex",
        "Average model size per tier: baseline versus combined strengthening.",
        "tab:strength_bounds_model_size",
        ["Tier", "Inst.", "Flights", r"$z$ base", r"$z$ comb.",
         "Cons. base", "Cons. comb.", r"$z$ reduction"],
        rows,
        "lrrrrrrr",
    )


def emit_bounds_table(summary):
    rows = []
    for _, row in summary.iterrows():
        rows.append([
            latex_escape(row["tier"]), latex_escape(row["variant"]),
            int(row["instances"]),
            f"{row['optimal']}/{int(row['instances'])}",
            fmt(row["mean_gap_pct"], 3) if row["mean_gap_pct"] is not None else "--",
            fmt(row["max_gap_pct"], 3) if row["max_gap_pct"] is not None else "--",
            fmt(row["mean_runtime_s"], 2),
            fmt(row["median_runtime_s"], 2),
        ])
    write_table(
        TABLES / "strength_bounds_summary.tex",
        "Exact-solve outcome per tier: proven optimality, residual MIP gap and runtime.",
        "tab:strength_bounds_summary",
        ["Tier", "Variant", "Inst.", "Optimal", r"Mean gap (\%)",
         r"Max gap (\%)", "Mean time (s)", "Median time (s)"],
        rows,
        "llrrrrrr",
    )


def emit_bracket_table(pairs):
    """Per-instance bracket evidence for the focus tier."""
    rows = []
    for _, row in pairs.iterrows():
        lp_bound = row.get("combined_lp_objective")
        dual = row.get("combined_milp_dual")
        primal = row.get("combined_milp_primal")
        coverage = row.get("heuristic_coverage")
        gap = row.get("combined_milp_gap")
        integrality = None
        if pd.notna(lp_bound) and pd.notna(primal) and abs(primal) > 1e-12:
            integrality = 100 * (primal - lp_bound) / abs(primal)
        rows.append([
            latex_escape(row["instance"]),
            fmt(lp_bound, 1), fmt(dual, 1), fmt(primal, 1),
            fmt(integrality, 3) if integrality is not None else "--",
            fmt(100 * gap, 3) if pd.notna(gap) else "--",
            fmt(100 * coverage, 1) if pd.notna(coverage) else "--",
        ])
    write_table(
        TABLES / "strength_bounds_bracket.tex",
        "Bound bracket under the combined formulation. The integrality gap "
        "separates the LP bound from the incumbent; the residual gap is what "
        "remained unproved at termination. Heuristic coverage below 100\\% means "
        "the heuristic cost is not a valid upper bound.",
        "tab:strength_bounds_bracket",
        ["Instance", "LP bound", "Dual bound", "Incumbent",
         r"Integrality gap (\%)", r"Residual gap (\%)", r"Heur. coverage (\%)"],
        rows,
        "lrrrrrr",
    )


def plot_bracket(pairs, output):
    frame = pairs.dropna(subset=["combined_milp_primal", "combined_lp_objective"])
    if frame.empty:
        return False
    positions = list(range(len(frame)))
    plt.figure(figsize=(10, 5))
    plt.fill_between(positions, frame["combined_lp_objective"],
                     frame["combined_milp_primal"], alpha=0.25,
                     label="LP bound to incumbent")
    plt.plot(positions, frame["combined_lp_objective"], "o-",
             label="LP lower bound")
    plt.plot(positions, frame["combined_milp_primal"], "s-",
             label="Incumbent (upper bound)")
    if frame["combined_milp_dual"].notna().any():
        plt.plot(positions, frame["combined_milp_dual"], "x--",
                 label="Dual bound at termination")
    plt.xticks(positions, frame["instance"], rotation=45, ha="right",
               fontsize=7)
    plt.ylabel("Objective value")
    plt.legend()
    plt.grid(alpha=0.2)
    plt.tight_layout()
    plt.savefig(output, dpi=180)
    plt.close()
    return True


def plot_gap(pairs, output):
    frame = pairs.copy()
    base = pd.to_numeric(frame["baseline_milp_gap"], errors="coerce") * 100
    comb = pd.to_numeric(frame["combined_milp_gap"], errors="coerce") * 100
    if not base.notna().any() and not comb.notna().any():
        return False
    positions = range(len(frame))
    width = 0.4
    plt.figure(figsize=(10, 4.8))
    plt.bar([p - width / 2 for p in positions], base.fillna(0), width,
            label="Baseline")
    plt.bar([p + width / 2 for p in positions], comb.fillna(0), width,
            label="Combined Strengthening")
    plt.xticks(list(positions), frame["instance"], rotation=45, ha="right",
               fontsize=7)
    plt.ylabel("Residual MIP gap (%)")
    plt.legend()
    plt.grid(alpha=0.2, axis="y")
    plt.tight_layout()
    plt.savefig(output, dpi=180)
    plt.close()
    return True


def plot_paired(pairs, base_col, comb_col, ylabel, output, log=False):
    base = pd.to_numeric(pairs[base_col], errors="coerce")
    comb = pd.to_numeric(pairs[comb_col], errors="coerce")
    if not base.notna().any():
        return False
    positions = range(len(pairs))
    plt.figure(figsize=(10, 4.8))
    plt.plot(positions, base, "o-", label="Baseline")
    plt.plot(positions, comb, "s-", label="Combined Strengthening")
    if log:
        plt.yscale("log")
    plt.xticks(list(positions), pairs["instance"], rotation=45, ha="right",
               fontsize=7)
    plt.ylabel(ylabel)
    plt.legend()
    plt.grid(alpha=0.2)
    plt.tight_layout()
    plt.savefig(output, dpi=180)
    plt.close()
    return True


def emit_macros(summary, pairs, path):
    """Expose headline values as macros so prose never transcribes a number."""
    lines = ["% Generated by experiments/analyze_strengthening_bounds.py.",
             "% Do not edit by hand."]

    def macro(name, value):
        lines.append(rf"\newcommand{{\{name}}}{{{value}}}")

    for tier, group in summary.groupby("tier", sort=False):
        key = "".join(part.capitalize() for part in str(tier).split())
        base = group[group["variant"] == "baseline"].iloc[0]
        comb = group[group["variant"] == "combined"].iloc[0]
        macro(f"Str{key}Instances", int(base["instances"]))
        macro(f"Str{key}Flights", f"{base['flights']:,.0f}")
        macro(f"Str{key}BaseZ", f"{base['z_variables']:,.0f}")
        macro(f"Str{key}CombZ", f"{comb['z_variables']:,.0f}")
        macro(f"Str{key}BaseCons", f"{base['constraints']:,.0f}")
        macro(f"Str{key}CombCons", f"{comb['constraints']:,.0f}")
        macro(f"Str{key}BaseOptimal", int(base["optimal"]))
        macro(f"Str{key}CombOptimal", int(comb["optimal"]))
        if base["z_variables"]:
            reduction = 100 * (base["z_variables"] - comb["z_variables"]) / base["z_variables"]
            macro(f"Str{key}ZReduction", f"{reduction:.1f}")
        for label, row in (("Base", base), ("Comb", comb)):
            runtime = row["mean_runtime_s"]
            macro(f"Str{key}{label}Runtime",
                  "--" if pd.isna(runtime) else f"{runtime:.2f}")
        base_rt, comb_rt = base["mean_runtime_s"], comb["mean_runtime_s"]
        if pd.notna(base_rt) and pd.notna(comb_rt) and base_rt > 0:
            macro(f"Str{key}RuntimeDrop",
                  f"{100 * (base_rt - comb_rt) / base_rt:.1f}")

    # How often the LP relaxation already proves the integer optimum.
    integral = 0
    counted = 0
    for _, row in pairs.iterrows():
        lp_value = row.get("combined_lp_objective")
        milp_value = row.get("combined_milp_primal")
        if pd.notna(lp_value) and pd.notna(milp_value):
            counted += 1
            if abs(lp_value - milp_value) <= 1e-6 * max(1.0, abs(milp_value)):
                integral += 1
    macro("StrIntegralLpCount", integral)
    macro("StrIntegralLpTotal", counted)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def emit_scaling_table(path, output):
    """Model-size scaling from build-only runs on the larger instances."""
    frame = pd.read_csv(path)
    rows = []
    for instance, group in frame.groupby("instance", sort=True):
        base = group[group["variant"] == "baseline"]
        comb = group[group["variant"] == "combined"]
        if base.empty or comb.empty:
            continue
        base, comb = base.iloc[0], comb.iloc[0]
        z_drop = (100 * (base["z_variables"] - comb["z_variables"])
                  / base["z_variables"]) if base["z_variables"] else None
        cons_change = (100 * (comb["constraints"] - base["constraints"])
                       / base["constraints"]) if base["constraints"] else None
        rows.append([
            latex_escape(instance), fmt(base["flights"], 0),
            fmt(base["aircraft"], 0),
            fmt(base["z_variables"], 0), fmt(comb["z_variables"], 0),
            fmt(z_drop, 1),
            fmt(base["constraints"], 0), fmt(comb["constraints"], 0),
            ("$+$" if cons_change is not None and cons_change > 0 else "")
            + fmt(cons_change, 1),
        ])
    write_table(
        output,
        "Model-size scaling on the larger certified instances. The trigger "
        "domain shrinks throughout, but the constraint count can rise when "
        "pairwise maintenance conflicts are disaggregated over a large fleet.",
        "tab:strength_bounds_scaling",
        ["Instance", "Flights", "Aircraft", r"$z$ base", r"$z$ comb.",
         r"$z$ drop (\%)", "Cons. base", "Cons. comb.", r"Cons. change (\%)"],
        rows,
        "lrrrrrrrr",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", action="append", required=True,
                        metavar="NAME=CSV",
                        help="Tier label and CSV path, e.g. Large=results/tables/x.csv")
    parser.add_argument("--summary-output", type=Path,
                        default=RESULTS / "strength_bounds_summary.csv")
    parser.add_argument("--pairs-output", type=Path,
                        default=RESULTS / "strength_bounds_pairs.csv")
    parser.add_argument("--figure-tier", default=None,
                        help="Tier used for per-instance figures and the bracket table.")
    parser.add_argument("--scaling-csv", type=Path, default=None,
                        help="Build-only CSV for the large-instance scaling table.")
    args = parser.parse_args()

    frames = []
    for item in args.tier:
        label, _, path = item.partition("=")
        frames.append(load_tier(Path(path), label))
    raw = pd.concat(frames, ignore_index=True)

    pairs = build_pairs(raw)
    tier_order = [item.partition("=")[0] for item in args.tier]
    pairs["tier"] = pd.Categorical(pairs["tier"], categories=tier_order,
                                   ordered=True)
    pairs = pairs.sort_values(["tier", "instance"]).reset_index(drop=True)

    summary = tier_summary(pairs)
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.summary_output, index=False)
    pairs.to_csv(args.pairs_output, index=False)

    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    emit_model_size_table(summary)
    emit_bounds_table(summary)
    emit_macros(summary, pairs, TABLES / "strength_bounds_macros.tex")
    if args.scaling_csv is not None:
        emit_scaling_table(args.scaling_csv,
                           TABLES / "strength_bounds_scaling.tex")

    focus_tier = args.figure_tier or tier_order[-1]
    focus = pairs[pairs["tier"] == focus_tier].reset_index(drop=True)
    if focus.empty:
        focus = pairs.reset_index(drop=True)
    emit_bracket_table(focus)

    plot_bracket(focus, FIGURES / "strength_bounds_bracket.png")
    plot_gap(focus, FIGURES / "strength_bounds_gap.png")
    plot_paired(focus, "baseline_milp_runtime", "combined_milp_runtime",
                "MILP runtime (s)", FIGURES / "strength_bounds_runtime.png",
                log=True)
    plot_paired(focus, "baseline_milp_z", "combined_milp_z",
                "Maintenance-trigger variables",
                FIGURES / "strength_bounds_zvars.png")

    print(summary.to_string(index=False))
    print(f"\nWrote {args.summary_output}")
    print(f"Wrote {args.pairs_output}")
    print(f"Wrote LaTeX fragments to {TABLES}")
    print(f"Wrote figures to {FIGURES}")


if __name__ == "__main__":
    main()
