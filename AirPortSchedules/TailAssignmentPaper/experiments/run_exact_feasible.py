"""Exact-solver comparison on the exact-feasible instance subset."""
import subprocess, json, csv, time, os, sys, re
from pathlib import Path

ROOT = Path(__file__).parent.parent

INSTANCES = [
    ("feas_A_p4h7_d05",    "data/feasible_family_smoke/A/DataCplex_density=0.5_p=4_h=7_test_0.json",        "A-only"),
    ("feas_AB_p4h7_d05",   "data/feasible_family_smoke_ab/AB/DataCplex_density=0.5_p=4_h=7_test_0.json",    "A+B"),
    ("feas_ABCD_p4h7_d05", "data/feasible_family_smoke_abcd/ABCD/DataCplex_density=0.5_p=4_h=7_test_0.json","A+B+C+D"),
    ("feas_A_p4h7_d08",    "data/phase1_feasible_subset_A/DataCplex_density=0.8_p=4_h=7_test_0.json",       "A-only"),
    ("feas_A_p6h10_d05",   "data/phase1_feasible_subset_A/DataCplex_density=0.5_p=6_h=10_test_0.json",      "A-only"),
    ("ABCD_cap_botl",      "data/instances/ABCD_capacity_bottleneck_test.json",                              "curated"),
    ("ABCD_hier",          "data/instances/ABCD_check_hierarchy_test.json",                                  "curated"),
    ("ABCD_near_thr",      "data/instances/ABCD_near_threshold_test.json",                                   "curated"),
    ("ABCD_no_maint",      "data/instances/ABCD_no_maint_test.json",                                        "curated"),
]

METHODS = [
    ("classical_milp",  ["--mode", "milp", "--no-maintenance", "--solver", "highs", "--time-limit", "120"]),
    ("integrated_milp", ["--mode", "milp",                    "--solver", "highs", "--time-limit", "120"]),
    ("greedy",          ["--mode", "heuristic", "--heuristic", "greedy"]),
    ("local_search",    ["--mode", "heuristic", "--heuristic", "local_search"]),
]


def parse_output(out):
    status = "unknown"; obj = None; assigned = None; total = None
    for line in out.splitlines():
        m = re.search(r"Status\s*:\s*(\S+)", line, re.I)
        if m:
            status = m.group(1).lower()
        m = re.search(r"Total cost:\s*([\d.]+)", line)
        if m:
            obj = float(m.group(1))
        m = re.search(r"Objective\s*:\s*([\d.]+)", line, re.I)
        if m and obj is None:
            obj = float(m.group(1))
        m = re.search(r"Obj\s*:\s*([\d.]+)", line, re.I)
        if m and obj is None:
            obj = float(m.group(1))
        m = re.search(r"Flights\s*:\s*(\d+)/(\d+)", line, re.I)
        if m:
            assigned, total = int(m.group(1)), int(m.group(2))
        m = re.search(r"Assigned\s+(\d+)/(\d+)", line, re.I)
        if m and assigned is None:
            assigned, total = int(m.group(1)), int(m.group(2))
    return status, obj, assigned, total


def main():
    rows = []
    for label, rel_path, family in INSTANCES:
        path = str(ROOT / rel_path)
        with open(path) as fh:
            j = json.load(fh)
        p = len(j.get("Aircrafts", []))
        fl = len(j.get("Flights", []))

        for method, args in METHODS:
            cmd = [sys.executable, str(ROOT / "src/model.py"), "--data", path, "--no-show"] + args
            t0 = time.time()
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                wall = time.time() - t0
                status, obj, assigned, total = parse_output(r.stdout + r.stderr)
            except subprocess.TimeoutExpired:
                status, obj, assigned, total, wall = "timeout", None, None, None, 180.0
            except Exception:
                status, obj, assigned, total, wall = "error", None, None, None, 0.0

            asgn_str = f"{assigned}/{total}" if assigned is not None else "-"
            obj_str = str(int(obj)) if obj is not None else "-"
            print(f"{label:22s} {method:20s} {status:12s} obj={obj_str:10s} asgn={asgn_str:7s} {wall:.1f}s")
            rows.append({
                "label": label, "family": family, "p": p, "flights": fl,
                "method": method, "status": status,
                "obj": obj, "assigned_str": asgn_str, "wall_s": round(wall, 2),
            })

    out_dir = ROOT / "results/tables/exact_feasible"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "comparison.csv"
    with open(out_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nSaved {out_path}")


if __name__ == "__main__":
    main()
