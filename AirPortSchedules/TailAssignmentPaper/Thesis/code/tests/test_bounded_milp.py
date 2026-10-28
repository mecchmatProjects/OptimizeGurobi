import json

import pytest

from experiments.run_bounded_milp import run_bounded


def test_bounded_cli_completes_and_records_log(tmp_path):
    log_path = tmp_path / 'help.log'
    report = run_bounded(['--help'], 30, log_path)
    assert report['status'] == 'completed'
    assert report['process_exit_code'] == 0
    assert '--time-limit' in log_path.read_text(encoding='utf-8')
    assert json.loads(log_path.with_suffix('.run.json').read_text()) == report


def test_bounded_cli_terminates_at_wall_deadline(tmp_path):
    report = run_bounded(['--help'], 0.001, tmp_path / 'deadline.log')
    assert report['status'] == 'wall_time_limit'
    assert report['process_exit_code'] is not None
    assert report['wall_s'] < 10
    assert 'does not certify infeasibility' in report['note']


def test_bounded_cli_rejects_nonpositive_limit(tmp_path):
    with pytest.raises(ValueError, match='positive'):
        run_bounded(['--help'], 0, tmp_path / 'invalid.log')