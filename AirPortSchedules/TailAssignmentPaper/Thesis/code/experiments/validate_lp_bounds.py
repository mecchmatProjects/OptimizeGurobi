#!/usr/bin/env python3
"""
LP Bounds Validation & Quality Assurance

Verifies that:
1. LP lower bounds are mathematically correct (computed properly)
2. LP bounds are indeed ≤ MILP optimal costs
3. Integrality gaps are correctly calculated
4. Data consistency between CSV and paper section
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.step4_lp_lower_bounds import validate_lp_results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, default=ROOT / 'results/tables/step4_lp_lower_bounds.csv')
    parser.add_argument('--reference', type=Path,
                        help='JSON mapping instance names to objective/config records.')
    args = parser.parse_args(argv)
    if not args.csv.exists():
        print(f'Missing CSV: {args.csv}', file=sys.stderr)
        return 2
    try:
        with args.csv.open(newline='', encoding='utf-8') as handle:
            rows = list(csv.DictReader(handle))
        if not rows or not {'instance', 'status', 'lp_bound'}.issubset(rows[0]):
            raise ValueError('Empty CSV or missing instance/status/lp_bound columns.')
        reference = json.loads(args.reference.read_text()) if args.reference else {}
        summary = validate_lp_results(rows, reference=reference)
    except (OSError, ValueError, KeyError) as exc:
        print(f'Validation input error: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    if not args.reference:
        print('No reference supplied: finite-bound checks only, no optimality certification.')
    return 1 if summary['violations'] else 0


if __name__ == '__main__':
    sys.exit(main())
