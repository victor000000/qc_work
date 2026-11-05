"""A local poll failure must not authorize claiming remote completion or shutdown."""
import copy
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('strangle_runner_evidence',HERE/'run.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)


def test_real_poll_transport_failure_does_not_verify_remote_completion():
    path=HERE/'results/strangle_basket-calmar_20261019_204146/local_poll_interruption.json'
    record=json.loads(path.read_text());record['result']={}
    assert record['status']=='failed' and 'error sending request' in record['error_message']
    assert runner.cloud_terminal_evidence(record) is None


def completed_example():
    campaign=HERE/'results/strangle_basket_20261018_191012'
    payload=json.loads(next(campaign.glob('*/backtest.json')).read_text())
    full=payload['backtest']
    return dict(project_id=full['projectId'],backtest_id=full['backtestId'],result=payload,status='done')


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
