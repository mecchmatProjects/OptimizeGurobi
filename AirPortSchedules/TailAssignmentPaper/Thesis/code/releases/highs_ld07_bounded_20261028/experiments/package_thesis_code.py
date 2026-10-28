"""Create a new hashed code release without overwriting archived thesis trees."""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from experiment_utils import experiment_metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('Choose a new release directory; existing snapshots are never overwritten.')
    paths = sorted(path for folder in ('src', 'experiments', 'tests')
                   for path in (ROOT / folder).glob('*.py'))
    manifest = experiment_metadata(ROOT, [], {'purpose': 'thesis code snapshot', 'build_only': True})
    manifest['files'] = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in paths}
    if args.dry_run:
        print(f'Would package {len(paths)} files into {args.output}; no files written.')
        return
    args.output.mkdir(parents=True)
    for path in paths:
        target = args.output / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Packaged {len(paths)} files into {args.output}')


if __name__ == '__main__':
    main()