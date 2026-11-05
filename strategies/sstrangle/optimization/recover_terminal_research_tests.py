import json
import pytest
from recover_terminal_research import terminal_values,apply_terminal,shared


def row():return dict(name='immutable',project_id=7,backtest_id='native',code_hash='source',status='running',error_message=None,result_json=None)
def payload(**changes):
    full=dict(projectId=7,backtestId='native',completed=True,status='Completed.',error=None)
    full.update(changes);return dict(success=True,backtest=full)


def test_live_execution_cannot_be_converted_to_local_completion():
    with pytest.raises(ValueError,match='nonterminal'):
        terminal_values(row(),payload(completed=False,status='In Progress...'))


def test_actual_cloud_completion_can_repair_local_poll_failure_without_losing_identity():
    r=row();r['status']='failed';r['error_message']='local timeout'
    v=terminal_values(r,payload())
    assert v['status']=='done' and v['error_message'] is None
    assert json.loads(v['result_json'])['backtestId']=='native'
    assert r['status']=='failed' and r['error_message']=='local timeout'


def test_genuine_cloud_failure_stays_failed():
    v=terminal_values(row(),payload(status='Runtime Error',error='Actual native error'))
    assert v['status']=='failed' and v['error_message']=='Actual native error'


@pytest.mark.parametrize('kind',['remote','stored','api'])
def test_identity_or_api_error_is_not_recoverable(kind):
    r=row();p=payload()
    if kind=='remote':p['backtest']['backtestId']='other'
    elif kind=='stored':r['result_json']=json.dumps(dict(backtestId='other'))
    else:p['success']=False
    with pytest.raises(ValueError):terminal_values(r,p)


def test_real_duckdb_update_is_guarded_by_frozen_identity_and_preserves_other_fields(tmp_path):
    db=tmp_path/'queue.duckdb'
    with shared.storage.connect(str(db)) as c:
        c.row_factory=shared.storage.Row
        c.execute('CREATE TABLE backtest_queue(name TEXT,project_id INTEGER,backtest_id TEXT,code_hash TEXT,status TEXT,error_message TEXT,result_json TEXT,runtime_seconds DOUBLE)')
        c.execute('INSERT INTO backtest_queue VALUES(?,?,?,?,?,?,?,?)',('immutable',7,'native','source','running',None,None,12.5))
    with shared.storage.connect(str(db)) as c:
        c.row_factory=shared.storage.Row;apply_terminal(c,row(),terminal_values(row(),payload()))
    with shared.storage.connect(str(db)) as c:
        c.row_factory=shared.storage.Row;r=dict(c.execute('SELECT * FROM backtest_queue').fetchone())
        assert r['status']=='done' and r['runtime_seconds']==12.5 and r['code_hash']=='source'
    wrong=row();wrong['backtest_id']='replaced'
    with pytest.raises(ValueError,match='identity/source changed'):
        with shared.storage.connect(str(db)) as c:
            c.row_factory=shared.storage.Row;apply_terminal(c,wrong,terminal_values(row(),payload()))
    with shared.storage.connect(str(db)) as c:
        assert c.execute('SELECT backtest_id,status FROM backtest_queue').fetchone()==('native','done')
