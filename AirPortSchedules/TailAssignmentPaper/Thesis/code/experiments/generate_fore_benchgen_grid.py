"""Generate a certified fore-benchgen grid from a versioned JSON specification."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import fore_benchgen
from benchmark_validation import validate_benchmark_certificate, verify_milp_certificate
from model import MILP_Sheduler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    specification = json.loads(args.config.read_text(encoding="utf-8"))
    published = []
    for profile in specification["profiles"]:
        preset_name = profile["preset"]
        overrides = {key: value for key, value in profile.items() if key != "preset"}
        if "topology" in overrides:
            overrides["route_topology"] = overrides.pop("topology")
        if "thresholds" in overrides:
            overrides["threshold_mode"] = overrides.pop("thresholds")
        for replicate in specification["replicates"]:
            instance, certificate, generator_report = fore_benchgen.generate(
                fore_benchgen.preset(preset_name, **overrides), replicate
            )
            certificate_report = validate_benchmark_certificate(instance, certificate)
            if generator_report["feasibility_status"] != "PASS" or certificate_report["status"] != "PASS":
                raise RuntimeError(f"certificate validation failed for {instance['Original_Filename']}")
            with tempfile.TemporaryDirectory() as temporary_directory:
                temporary_path = Path(temporary_directory) / instance["Original_Filename"]
                temporary_path.write_text(json.dumps(instance), encoding="utf-8")
                milp_report = verify_milp_certificate(MILP_Sheduler(str(temporary_path)), certificate)
            if milp_report["status"] != "PASS":
                raise RuntimeError(
                    f"MILP certificate validation failed for {instance['Original_Filename']}: "
                    f"{milp_report['errors'][:3]}"
                )
            metrics = fore_benchgen.compute_metrics(instance, certificate)
            fore_benchgen.export(
                instance, certificate, generator_report, args.output_dir, ["json"], metrics=metrics
            )
            published.append(instance["Original_Filename"])

    print(f"Published {len(published)} certified instances to {args.output_dir}")


if __name__ == "__main__":
    main()