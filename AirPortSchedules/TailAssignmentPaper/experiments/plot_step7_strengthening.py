"""Generate thesis figures from the validated strengthening results."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "tables"
FIGURES = ROOT / "Thesis" / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)


def load_pair(baseline_name, combined_name, value):
    baseline = pd.read_csv(RESULTS / baseline_name).query("variant == 'baseline'")
    combined = pd.read_csv(RESULTS / combined_name)
    combined = combined[combined["variant"].str.contains("strong_link")]
    pair = baseline[["instance", value]].rename(columns={value: "baseline"})
    pair = pair.merge(
        combined[["instance", value]].rename(columns={value: "combined"}),
        on="instance",
        how="inner",
    )
    return pair


def paired_plot(pair, ylabel, output, log=False):
    positions = range(len(pair))
    plt.figure(figsize=(10, 4.8))
    plt.plot(positions, pair["baseline"], "o-", label="Baseline")
    plt.plot(positions, pair["combined"], "s-", label="Combined Strengthening")
    if log:
        plt.yscale("log")
    plt.xlabel("Instance index")
    plt.ylabel(ylabel)
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIGURES / output, dpi=180)
    plt.close()


lp = load_pair(
    "step7_feasible_large_A_cplexamp_lp.csv",
    "step7_feasible_large_A_combined_cplexamp_lp.csv",
    "objective",
)
lp_runtime = load_pair(
    "step7_feasible_large_A_cplexamp_lp.csv",
    "step7_feasible_large_A_combined_cplexamp_lp.csv",
    "runtime_s",
)
milp_runtime = load_pair(
    "step7_feasible_large_A_cplexamp_milp.csv",
    "step7_feasible_large_A_combined_cplexamp_milp.csv",
    "runtime_s",
)
milp_obj = load_pair(
    "step7_feasible_large_A_cplexamp_milp.csv",
    "step7_feasible_large_A_combined_cplexamp_milp.csv",
    "objective",
)

paired_plot(lp, "LP objective / lower bound", "strength_lp_bounds.png")
paired_plot(lp_runtime, "LP runtime (s)", "strength_lp_runtime.png", log=True)
paired_plot(milp_runtime, "MILP runtime (s)", "strength_milp_runtime.png", log=True)

plt.figure(figsize=(6.5, 5.5))
plt.scatter(milp_obj["baseline"], milp_obj["combined"], label="20 feasible instances")
lo = min(milp_obj["baseline"].min(), milp_obj["combined"].min())
hi = max(milp_obj["baseline"].max(), milp_obj["combined"].max())
plt.plot([lo, hi], [lo, hi], "k--", label="Objective parity")
plt.xlabel("Baseline MILP objective")
plt.ylabel("Combined MILP objective")
plt.legend()
plt.tight_layout()
plt.savefig(FIGURES / "strength_objective_parity.png", dpi=180)
plt.close()

speedup = milp_runtime["baseline"] / milp_runtime["combined"]
plt.figure(figsize=(10, 4.8))
plt.bar(range(len(speedup)), speedup)
plt.axhline(1.0, color="black", linestyle="--")
plt.xlabel("Instance index")
plt.ylabel("Baseline runtime / combined runtime")
plt.tight_layout()
plt.savefig(FIGURES / "strength_speedup.png", dpi=180)
plt.close()

# Model-size figure uses a heterogeneous feasible structural family.
structure_base = pd.read_csv(RESULTS / "step7_heterogeneous_baseline_structure.csv")
structure_combined = pd.read_csv(RESULTS / "step7_heterogeneous_combined_structure.csv")
structure_base = structure_base.query("variant == 'baseline'")
structure_combined = structure_combined[
    structure_combined["variant"].str.contains("sparse_z")
]
structure = structure_base[["instance", "z_variables", "constraints"]].merge(
    structure_combined[["instance", "z_variables", "constraints"]],
    on="instance",
    suffixes=("_baseline", "_combined"),
)
manifest = pd.read_json(
    ROOT / "data" / "step7_feasible_heterogeneous" / "manifest.json"
)
manifest["instance"] = manifest["file"].str.replace(".json", "", regex=False)
structure = structure.merge(
    manifest[["instance", "p", "h", "maintenance_family", "flights"]],
    on="instance",
)
structure["z_reduction"] = (
    structure["z_variables_baseline"] - structure["z_variables_combined"]
)
structure["constraint_reduction"] = (
    structure["constraints_baseline"] - structure["constraints_combined"]
)
plt.figure(figsize=(8, 5.8))
for family, group in structure.groupby("maintenance_family"):
    plt.scatter(
        group["z_variables_baseline"],
        group["z_reduction"],
        label=family,
        s=42,
    )
plt.xlabel("Baseline maintenance-trigger variables")
plt.ylabel("Reduction in maintenance-trigger variables")
plt.legend(title="Maintenance family")
plt.grid(alpha=0.2)
plt.tight_layout()
plt.savefig(FIGURES / "strength_model_size.png", dpi=180)
plt.close()

print(f"Generated figures in {FIGURES}")
