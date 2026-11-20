"""Build a deterministic, content-addressed profile-evidence archive."""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INCLUDE_GLOBS = (
    "requirements.txt",
    "AGENTS.md",
    "src/model.py",
    "src/benchmark_validation.py",
    "src/experiment_utils.py",
    "src/solver_utils.py",
    "src/generate_instances.py",
    "experiments/generate_profile_timing.py",
    "experiments/run_profile_matrix.py",
    "experiments/summarize_profile_timing.py",
    "experiments/plot_profile_timing.py",
    "experiments/package_profile_evidence.py",
    "tests/test_profile_timing.py",
    "tests/test_formulation_profiles.py",
    "tests/test_benchmark_validation.py",
    "docs/REPRODUCIBILITY.md",
    "data/validation/profile_timing_20261118/*.json",
    "data/validation/profile_scale_20261118/*.json",
    "data/validation/profile_heterogeneous_20261119/*.json",
    "data/validation/profile_heterogeneous_repeat_20261120/*.json",
    "data/validation/profile_overnight_20261119/*.json",
    "results/tables/profile_timing_*_20261118.csv",
    "results/tables/profile_timing_*_20261118.metadata.json",
    "results/tables/profile_timing_*_20261118.schedules.json",
    "results/tables/profile_timing_*_20261118.sources.zip",
    "results/tables/profile_scale_*_cplex129_20261118.csv",
    "results/tables/profile_scale_*_cplex129_20261118.metadata.json",
    "results/tables/profile_scale_*_cplex129_20261118.schedules.json",
    "results/tables/profile_scale_*_cplex129_20261118.sources.zip",
    "results/tables/profile_heterogeneous_*_repeats3_20261119.csv",
    "results/tables/profile_heterogeneous_*_repeats3_20261119.metadata.json",
    "results/tables/profile_heterogeneous_*_repeats3_20261119.schedules.json",
    "results/tables/profile_heterogeneous_*_repeats3_20261119.sources.zip",
    "results/tables/profile_heterogeneous_*_repeats3_20261120.csv",
    "results/tables/profile_heterogeneous_*_repeats3_20261120.metadata.json",
    "results/tables/profile_heterogeneous_*_repeats3_20261120.schedules.json",
    "results/tables/profile_heterogeneous_*_repeats3_20261120.sources.zip",
    "results/tables/profile_overnight_*_20261120.csv",
    "results/tables/profile_overnight_*_20261120.metadata.json",
    "results/tables/profile_overnight_*_20261120.schedules.json",
    "results/tables/profile_overnight_*_20261120.sources.zip",
    "paper/main.tex",
    "paper/main.pdf",
    "paper/refs.bib",
    "paper/sections/*.tex",
    "paper/figures/profile_timing_20261118.png",
    "paper/figures/option_a_b_paired_timing_repeats3_20261118.png",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_files() -> list[Path]:
    paths = set()
    for pattern in INCLUDE_GLOBS:
        paths.update(path for path in ROOT.glob(pattern) if path.is_file())
    return sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix())


def git_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def write_zip(archive: Path, files: list[Path]) -> None:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as bundle:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 11, 20, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED,
                            compresslevel=9)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "results" / "archive" / "profile_evidence_20261120")
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("output directory exists; immutable archives are never overwritten")

    files = collect_files()
    if not files:
        parser.error("no evidence files matched the archive manifest")
    repeated_results = [
        path for path in files if path.suffix == ".csv"
        and path.name.endswith("20261120.csv")
        and "repeats3" in path.name
    ]
    heterogeneous_results = {
        path.name for path in repeated_results
        if "profile_heterogeneous" in path.name
    }
    overnight_results = {
        path.name for path in repeated_results
        if "profile_overnight" in path.name
    }
    if len(heterogeneous_results) != 6:
        parser.error(
            "expected six 20261120 heterogeneous repeated CSVs, "
            f"found {len(heterogeneous_results)}"
        )
    if len(overnight_results) != 2:
        parser.error(
            "expected two 20261120 overnight repeated CSVs, "
            f"found {len(overnight_results)}"
        )
    missing_sidecars = []
    file_set = set(files)
    for path in repeated_results:
        for suffix in (".metadata.json", ".schedules.json", ".sources.zip"):
            sidecar = path.with_suffix(suffix)
            if sidecar not in file_set:
                missing_sidecars.append(sidecar.relative_to(ROOT).as_posix())
    if missing_sidecars:
        parser.error("missing evidence sidecars: " + ", ".join(sorted(missing_sidecars)))

    args.output_dir.mkdir(parents=True)
    archive = args.output_dir / "profile_evidence_20261120.zip"
    write_zip(archive, files)
    manifest = {
        "archive": archive.name,
        "archive_sha256": sha256(archive),
        "created_for": "Tail Assignment Paper Q1 evidence snapshot",
        "fixed_zip_timestamp": "2026-11-20T00:00:00Z",
        "git_revision": git_revision(),
        "platform": platform.platform(),
        "files": {
            path.relative_to(ROOT).as_posix(): {
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in files
        },
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "SHA256SUMS.txt").write_text(
        f"{manifest['archive_sha256']}  {archive.name}\n", encoding="ascii"
    )
    print(f"Wrote {archive} with {len(files)} files")
    print(f"SHA256 {manifest['archive_sha256']}")


if __name__ == "__main__":
    main()
