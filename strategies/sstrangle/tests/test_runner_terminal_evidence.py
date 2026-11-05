"""A local poll failure must not authorize claiming remote completion or shutdown."""
import copy
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('strangle_runner_evidence',HERE/'run.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)


def test_poll_transport_failure_does_not_verify_remote_completion():
    record=dict(project_id=42, backtest_id='synthetic-run', status='failed',
                error_message='poll: error sending request', result={})
    assert runner.cloud_terminal_evidence(record) is None


def completed_example():
    return dict(project_id=42, backtest_id='synthetic-run', status='done',
        result=dict(success=True, backtest=dict(projectId=42, backtestId='synthetic-run', completed=True)))


def test_actual_full_terminal_identity_allows_terminal_collection():
    assert runner.cloud_terminal_evidence(completed_example())=='identity_verified_full_terminal_read'


def test_matching_still_live_cloud_read_does_not_allow_stopping_owner():
    record=completed_example();record['result']['backtest']['completed']=False
    record['result']['backtest'].pop('error',None)
    assert runner.cloud_terminal_evidence(record) is None


def test_conflicting_cloud_identity_fails_closed():
    record=completed_example();record['backtest_id']='different'
    assert runner.cloud_terminal_evidence(record) is None


def test_api_error_cannot_authorize_shutdown_even_with_completion_fields():
    record=completed_example();record['result']['success']=False
    assert runner.cloud_terminal_evidence(record) is None


def test_only_rust_completed_runtime_prefix_accepts_pending_failure_export():
    record=dict(project_id=42,backtest_id='existing',result={},status='failed',error_message='poll: runtime_error: strategy failed')
    assert runner.cloud_terminal_evidence(record).startswith('rust_observed_completed_runtime_error')
    for message in ('poll: error sending request','collect: runtime_error: unknown','poll: backtest_timeout','runtime_error: user text'):
        record['error_message']=message
        assert runner.cloud_terminal_evidence(record) is None


def test_missing_ids_or_boolean_completion_cannot_prove_completion():
    record=completed_example();record['project_id']=None
    assert runner.cloud_terminal_evidence(record) is None
    record=completed_example();record['result']['backtest']['completed']=1
    assert runner.cloud_terminal_evidence(record) is None


def test_launcher_cleanup_uses_cloud_evidence_and_retains_unknown_executions():
    source=(HERE/'run.py').read_text()
    assert 'safe_to_stop = len(outcomes)==len(jobs) and all(cloud_terminal_evidence(r)' in source
    assert "if record['cloud_terminal_verified']:" in source
