"""Incremental experiment records with configuration-checked resume."""

import csv
import hashlib
import json
import logging
import platform
import os
import subprocess
from pathlib import Path

import pyomo
from pyomo.environ import SolverFactory


def instance_paths(directory, pattern='*.json'):
    excluded = ('.manifest.json', '.solution.json', '.validation.json', '.metrics.json')
    return sorted(path for path in Path(directory).glob(pattern)
                  if path.name != 'manifest.json' and not path.name.endswith(excluded))


def experiment_metadata(root, paths, config):
    root = Path(root)
    digest = hashlib.sha256()
    for folder in ('src', 'experiments'):
        for path in sorted((root / folder).glob('*.py')):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root,
                                         text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = 'unavailable'
    solver_version = 'not queried'
    if config.get('solver') and not config.get('build_only'):
        try:
            options = {'executable': str(config['executable'])} if config.get('executable') else {}
            solver = SolverFactory(config['solver'], **options)
            if solver.available(False):
                solver_version = str(solver.version())
            else:
                solver_version = 'unavailable'
        except (OSError, ValueError, RuntimeError, AttributeError):
            solver_version = 'unavailable'
    return {
        'commit': commit, 'source_sha256': digest.hexdigest(),
        'python': platform.python_version(), 'pyomo': pyomo.__version__,
        'platform': platform.platform(),
        'processor': platform.processor(), 'cpu_count': os.cpu_count(),
        'solver_version': solver_version,
        'threads': config.get('threads') if config.get('threads') is not None else 'solver default',
        'inputs': {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in paths if path.exists()},
        'config': {key: str(value) if isinstance(value, Path) else value
                   for key, value in config.items()
                   if key not in ('output', 'resume', 'overwrite')},
    }


CANONICAL_FIELDS = ['stem', 'P', 'H', 'F', 'vars', 'constraints', 'nodes_max',
                    'gap_pct', 'cpu_s', 'objective']


def canonical_row(row):
    aliases = {'stem': 'instance', 'P': 'aircraft', 'H': 'days', 'F': 'flights',
               'vars': 'n_var', 'constraints': 'n_con', 'nodes_max': 'nodes',
               'cpu_s': 'runtime_s'}
    result = dict(row)
    if 'max_deferral_days' in result and result['max_deferral_days'] is None:
        result['max_deferral_days'] = 'none'
    for target, source in aliases.items():
        result.setdefault(target, row.get(source))
    if result.get('vars') is None:
        result['vars'] = row.get('variables')
    if 'objective' not in result:
        result['objective'] = row.get('lp_bound')
    if 'gap_pct' not in result:
        gap = row.get('mip_gap')
        result['gap_pct'] = 100 * gap if gap is not None else None
    return result


class ExperimentCSV:
    def __init__(self, path, fields, metadata, resume=False, overwrite=False):
        self.path = Path(path)
        self.fields = list(dict.fromkeys(fields + CANONICAL_FIELDS))
        self.previous = []
        sidecar = self.path.with_suffix('.metadata.json')
        if self.path.exists():
            if resume:
                if not sidecar.exists() or json.loads(sidecar.read_text()) != metadata:
                    raise ValueError(f'Resume configuration/source mismatch: {self.path}')
                with self.path.open(newline='', encoding='utf-8') as handle:
                    reader = csv.DictReader(handle)
                    if reader.fieldnames != self.fields:
                        raise ValueError(f'Resume CSV schema mismatch: {self.path}')
                    self.previous = list(reader)
            elif not overwrite:
                raise FileExistsError(f'Output exists: {self.path}; use --resume or --overwrite.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        self.handle = self.path.open('a' if resume and self.path.exists() else 'w',
                                     newline='', encoding='utf-8')
        self.writer = csv.DictWriter(self.handle, fieldnames=self.fields, extrasaction='ignore')
        if not resume or self.path.stat().st_size == 0:
            self.writer.writeheader()
            self.handle.flush()
        self.log_handler = logging.FileHandler(self.path.with_suffix('.log'), encoding='utf-8')
        self.log_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logging.getLogger().addHandler(self.log_handler)

    def write(self, row):
        self.writer.writerow(canonical_row(row))
        self.handle.flush()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.handle.close()
        logging.getLogger().removeHandler(self.log_handler)
        self.log_handler.close()