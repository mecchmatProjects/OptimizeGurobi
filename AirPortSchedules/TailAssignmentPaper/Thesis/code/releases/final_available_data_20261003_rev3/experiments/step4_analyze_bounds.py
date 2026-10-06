#!/usr/bin/env python3
"""
Step 4 Validation: Heuristic Gap Analysis vs LP Lower Bounds

Compares heuristic results (greedy, local-search) from Step 3
with LP relaxation lower bounds to quantify solution quality.
"""

import csv
import argparse
import json
import sys
from pathlib import Path

def emit_thesis_evidence(runs, output, table_dir, figure_dir):
    import pandas as pd
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    tables = []
    frames = []
    for index, specification in enumerate(runs, 1):
        label, separator, filename = specification.partition('=')
        if not separator:
            raise ValueError('Use --run LABEL=CSV.')
        path = Path(filename)
        metadata_path = path.with_suffix('.metadata.json')
        if not metadata_path.exists():
            raise ValueError(f'Missing provenance sidecar: {metadata_path}')
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        config = metadata['config']
        frame = pd.read_csv(path)
        required = {'instance', 'status', 'lp_bound', 'n_var', 'n_con', 'z_vars', 'build_s', 'runtime_s', 'wall_s'}
        if not required.issubset(frame.columns) or frame.empty:
            raise ValueError(f'Empty or incompatible LP CSV: {path}')
        if frame['instance'].duplicated().any():
            raise ValueError(f'Duplicate attempts require separate review: {path}')
        if config.get('formulation') != 'integrated':
            raise ValueError('These tables require integrated LP evidence.')
        frame['study'] = label
        frame['source_csv'] = str(path)
        frame['solver'] = config.get('solver')
        frame['cap'] = config.get('max_hour_check_deferral_days')
        frame['policy'] = config.get('lp_relaxation', 'not-recorded')
        frame['threads'] = metadata.get('threads', 'not-recorded')
        frames.append(frame)
        def escape(raw):
            return str(raw).replace('_', r'\_').replace('%', r'\%')
        def number(raw, digits=0):
            return '--' if pd.isna(raw) else f'{float(raw):,.{digits}f}'
        cap = config.get('max_hour_check_deferral_days')
        cap_text = 'unrestricted' if cap is None else f'{cap}-day cap'
        policy = config.get('lp_relaxation', 'not recorded in this historical sidecar')
        lines = [r'\begin{table}[htbp]', r'\centering\scriptsize',
                 rf'\caption{{{escape(label)}: recorded integrated LP evidence with {escape(config.get("solver"))} '
                 rf'{escape(metadata.get("solver_version"))}, {escape(cap_text)}, '
                 rf'LP policy {escape(policy)}. Time is end-to-end wall time; unavailable bounds are dashes.}}',
                 rf'\label{{tab:validated_lp_{index}}}', r'\begin{tabular}{lrrrrlrr}', r'\toprule',
                 r'Instance & Vars & Rows & $z$ & LP bound & Status & Build (s) & Total (s) \\', r'\midrule']
        if index == 1:
            lines.insert(4, r'\label{tab:step4_long_family_lp}')
        for _, row in frame.iterrows():
            bound = row['lp_bound'] if str(row['status']).lower() == 'optimal' else float('nan')
            lines.append(' & '.join([r'\texttt{' + escape(row['instance']) + '}',
                         number(row['n_var']), number(row['n_con']), number(row['z_vars']),
                         number(bound, 1), escape(row['status']), number(row['build_s'], 1),
                         number(row['wall_s'], 1)]) + r' \\')
        lines.extend([r'\bottomrule', r'\end{tabular}', r'\end{table}', ''])
        table_path = table_dir / f'validated_lp_{index}.tex'
        table_path.parent.mkdir(parents=True, exist_ok=True)
        table_path.write_text('\n'.join(lines), encoding='utf-8')
        tables.append(table_path.name)
    combined = pd.concat(frames, ignore_index=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output, index=False)
    manifest = {'runs': runs, 'tables': tables, 'summary': str(output)}
    output.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    figure_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(len(frames), 1, figsize=(10, 3.2 * len(frames)), squeeze=False)
    for axis, frame in zip(axes[:, 0], frames):
        ordered = frame.sort_values('instance')
        axis.bar(ordered['instance'], ordered['wall_s'], color='#367c96')
        axis.set_title(str(frame['study'].iloc[0]))
        axis.set_ylabel('Total wall time (s)')
        axis.tick_params(axis='x', rotation=20)
    fig.tight_layout()
    fig.savefig(figure_dir / 'validated_lp_runtime.png', dpi=160)
    plt.close(fig)
    print(f'Wrote source-backed LP evidence: {output}')


def main(argv=None):
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='append', help='Generate thesis evidence from LABEL=CSV.')
    parser.add_argument('--output', type=Path, default=root / 'results/tables/thesis_final_20261003/lp_evidence.csv')
    parser.add_argument('--table-dir', type=Path, default=root / 'Thesis/tables')
    parser.add_argument('--figure-dir', type=Path, default=root / 'Thesis/figures')
    args = parser.parse_args(argv)
    if args.run:
        emit_thesis_evidence(args.run, args.output, args.table_dir, args.figure_dir)
        return 0
    return legacy_summary()


def legacy_summary():
    """
    Read LP bounds and exact-feasible heuristic results.
    Compute gaps and generate comparison table.
    """
    
    # Read LP bounds
    lp_csv = Path("results/tables/step4_lp_lower_bounds.csv")
    lp_data = {}
    with open(lp_csv) as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row['instance'], row['formulation'])
            if row['status'] == 'optimal':
                lp_data[key] = float(row['lp_bound'])
    
    print(f"✓ Loaded LP bounds for {len(lp_data)} instances")
    print("\nLP Lower Bounds Summary:")
    print("-" * 70)
    print(f"{'Instance':<45} {'Classical LP':<20} {'Integrated LP':<20}")
    print("-" * 70)
    
    instances_seen = set()
    for (inst, form), bound in sorted(lp_data.items()):
        if inst not in instances_seen:
            instances_seen.add(inst)
            classical_key = (inst, 'classical')
            integrated_key = (inst, 'integrated')
            c_bound = lp_data.get(classical_key, '')
            i_bound = lp_data.get(integrated_key, '')
            
            c_str = f"{c_bound:,.0f}" if isinstance(c_bound, (int, float)) else "-"
            i_str = f"{i_bound:,.0f}" if isinstance(i_bound, (int, float)) else "-"
            
            print(f"{inst:<45} {c_str:>18} {i_str:>18}")
    
    print("-" * 70)
    print("\nKey Findings:")
    print('Status/objective summaries alone do not certify runtime or solver provenance.')
    print('Compare only compatible model/solver settings and complete validated schedules.')
    
    print("\nNext: Pair with Step 3 exact-feasible results to compute heuristic gaps")
    print("      (greedy_cost - lp_bound) / lp_bound × 100%")

if __name__ == '__main__':
    sys.exit(main())
