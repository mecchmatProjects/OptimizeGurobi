"""Run the maintained model CLI with a separate hard wall-clock deadline."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_bounded(arguments, wall_time_limit, log_path):
    if wall_time_limit <= 0:
        raise ValueError('wall_time_limit must be positive.')
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-u', str(ROOT / 'src' / 'model.py'), *arguments]
    started = time.perf_counter()
    timed_out = False
    with log_path.open('w', encoding='utf-8') as log:
        process = subprocess.Popen(
            command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            process.wait(timeout=wall_time_limit)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == 'nt':
                cleanup = subprocess.run(
                    ['taskkill', '/PID', str(process.pid), '/T', '/F'],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    check=False,
                )
                log.write('\nProcess-tree cleanup: ' + cleanup.stdout)
            else:
                process.kill()
            if process.poll() is None:
                process.kill()
            process.wait()
        except BaseException:
            process.kill()
            process.wait()
            raise

    report = {
        'status': 'wall_time_limit' if timed_out else 'completed' if process.returncode == 0 else 'process_error',
        'process_exit_code': process.returncode,
        'wall_s': time.perf_counter() - started,
        'wall_time_limit_s': wall_time_limit,
        'command': command,
        'log': str(log_path.resolve()),
        'note': (
            'Forced termination does not certify infeasibility or preserve an incumbent.'
            if timed_out else 'Read the solver summary/log for optimization status.'
        ),
    }
    report_path = log_path.with_suffix('.run.json')
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wall-time-limit', type=float, required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('model_arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    arguments = args.model_arguments
    if arguments[:1] == ['--']:
        arguments = arguments[1:]
    if not arguments:
        parser.error('Supply model arguments after --.')
    report = run_bounded(arguments, args.wall_time_limit, args.log)
    print(json.dumps(report, indent=2))
    raise SystemExit(124 if report['status'] == 'wall_time_limit' else report['process_exit_code'])


if __name__ == '__main__':
    main()