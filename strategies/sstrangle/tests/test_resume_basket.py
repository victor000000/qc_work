from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]))
from resume_basket import terminal_status,validate_identity


def test_inflight_execution_is_never_treated_as_done_or_requeued():
    assert terminal_status(dict(status='In Progress...',completed=False)) is None
    assert terminal_status(dict(status='In Queue...',completed=False)) is None
    assert terminal_status(dict(status='Completed',completed=True))=='done'
    assert terminal_status(dict(status='Completed.',completed=True))=='done'
    assert terminal_status(dict(status='Runtime Error',completed=True,error='bad fill'))=='failed'
    assert terminal_status(dict(status='Cancelled',completed=True))=='failed'


def test_resuming_rejects_unrelated_execution():
    row=dict(project_id=123,backtest_id='frozen')
    validate_identity(dict(projectId=123,backtestId='frozen'),row)
    for remote in [dict(projectId=456,backtestId='frozen'),dict(projectId=123,backtestId='other')]:
        with pytest.raises(ValueError,match='identity'):
            validate_identity(remote,row)


@pytest.mark.parametrize('status',['In Queue...','In Progress...'])
def test_read_timeout_falls_back_without_cancel_or_replace(monkeypatch,status):
    import resume_basket as module
    calls=[]
    def request(user,token,path,body):
        calls.append(path)
        if path=='/backtests/read':raise TimeoutError('initialization read timeout')
        assert path=='/backtests/list'
        return {'backtests':[dict(projectId=123,backtestId='frozen',status=status,completed=False)]}
    monkeypatch.setattr(module,'request',request)
    result=module.read_existing_backtest('u','t',dict(project_id=123,backtest_id='frozen'))
    assert calls==['/backtests/read','/backtests/list']
    assert terminal_status(result['backtest']) is None


def test_full_terminal_read_used_without_fetching_large_listing(monkeypatch):
    import resume_basket as module
    calls=[]
    def request(user,token,path,body):
        calls.append(path)
        b=dict(projectId=123,backtestId='frozen',status='Completed.',completed=True)
        if path=='/backtests/list':return {'backtests':[b]}
        assert path=='/backtests/read'
        return {'backtest':dict(b,statistics={'Total Orders':'10'})}
    monkeypatch.setattr(module,'request',request)
    result=module.read_existing_backtest('u','t',dict(project_id=123,backtest_id='frozen'))
    assert calls==['/backtests/read']
    assert result['backtest']['statistics']['Total Orders']=='10'


def test_fresh_direct_read_does_not_use_stale_queued_listing(monkeypatch):
    import resume_basket as module
    calls=[]
    def request(user,token,path,body):
        calls.append(path)
        assert path=='/backtests/read'
        assert body==dict(projectId=123,backtestId='frozen')
        return dict(backtest=dict(projectId=123,backtestId='frozen',status='In Progress...',completed=False,progress=.1))
    monkeypatch.setattr(module,'request',request)
    result=module.read_existing_backtest('u','t',dict(project_id=123,backtest_id='frozen'))
    assert result['backtest']['progress']==.1 and calls==['/backtests/read']


@pytest.mark.parametrize('backtests',[
    [],[dict(projectId=123,backtestId='frozen',completed=True,status='Completed.')],
    [dict(projectId=123,backtestId='frozen',completed=True,status='Runtime Error',error='actual failure')]])
def test_terminal_or_missing_listing_cannot_be_exported_as_full_result(monkeypatch,backtests):
    import resume_basket as module
    def request(user,token,path,body):
        if path=='/backtests/read':raise TimeoutError('transport timeout')
        return dict(backtests=backtests)
    monkeypatch.setattr(module,'request',request)
    with pytest.raises(RuntimeError,match='complete result evidence'):
        module.read_existing_backtest('u','t',dict(project_id=123,backtest_id='frozen'))


def test_identity_failure_cannot_fall_back_to_another_endpoint(monkeypatch):
    import resume_basket as module
    def request(user,token,path,body):
        assert path=='/backtests/read'
        return dict(backtest=dict(projectId=123,backtestId='different'))
    monkeypatch.setattr(module,'request',request)
    with pytest.raises(ValueError,match='identity'):
        module.read_existing_backtest('u','t',dict(project_id=123,backtest_id='frozen'))


def test_both_endpoint_timeouts_preserve_retryable_error(monkeypatch):
    import resume_basket as module
    calls=[]
    def request(user,token,path,body):
        calls.append(path);raise TimeoutError('transport timeout')
    monkeypatch.setattr(module,'request',request)
    with pytest.raises(TimeoutError):
        module.read_existing_backtest('u','t',dict(project_id=123,backtest_id='frozen'))
    assert calls==['/backtests/read','/backtests/list']
