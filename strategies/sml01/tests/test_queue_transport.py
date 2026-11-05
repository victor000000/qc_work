"""SML01's producer uses the generic server schema without silent result corruption."""
import json
from pathlib import Path
import qc_storage as storage

import pytest
from lb.harness import constants, qc_client


@pytest.fixture
def queue_db(tmp_path, monkeypatch):
    path = tmp_path / 'SML01.duckdb'
    schema = Path(__file__).resolve().parents[3] / 'crates/qc-server/schema.sql'
    with storage.connect(path) as conn:
        conn.executescript(schema.read_text())
    monkeypatch.setattr(constants, 'SML01_DB_PATH', str(path))
    return path


def test_missing_database_is_not_created_by_read_or_submit(tmp_path, monkeypatch):
    path = tmp_path / 'missing.duckdb'
    monkeypatch.setattr(constants, 'SML01_DB_PATH', str(path))
    with pytest.raises(storage.OperationalError):
        qc_client.read_backtest('1')
    with pytest.raises(storage.OperationalError):
        qc_client.submit_backtest('pass', 'test')
    assert not path.exists()


def test_long_repeated_names_still_have_unique_queue_handles(queue_db):
    ids = [qc_client.submit_backtest('pass', 'x'*300) for _ in range(2)]
    assert ids[0] != ids[1]
    with storage.connect(queue_db) as conn:
        names = [row[0] for row in conn.execute('SELECT name FROM backtest_queue')]
    assert len(set(names)) == 2
    assert all(len(name) <= 240 for name in names)


def test_multifile_submission_and_completed_result_round_trip(queue_db):
    bid = qc_client.submit_backtest('import extra', 'train', {'extra.py':'x=1'})
    result = {'status':'Completed.', 'statistics':{'Total Orders':'2'},
              'runtimeStatistics':{'n_predictions':'3'}}
    with storage.connect(queue_db) as conn:
        assert json.loads(conn.execute('SELECT extra_files FROM backtest_queue WHERE id=?',(bid,)).fetchone()[0]) == {'extra.py':'x=1'}
        conn.execute("UPDATE backtest_queue SET status='done',result_json=? WHERE id=?",(json.dumps(result),bid))
    assert qc_client.read_backtest_status(bid) == ('Completed.', {'n_predictions':'3'}, '')
    assert qc_client.read_backtest(bid)['statistics'] == {'Total Orders':'2'}


@pytest.mark.parametrize('payload', [None, '{invalid', '[]', '{}', '{"statistics":{}}'])
def test_completed_row_with_missing_or_corrupt_result_fails(queue_db,payload):
    bid = qc_client.submit_backtest('pass','bad-result')
    with storage.connect(queue_db) as conn:
        conn.execute("UPDATE backtest_queue SET status='done',result_json=? WHERE id=?",(payload,bid))
    with pytest.raises(RuntimeError,match='invalid result_json'):
        qc_client.read_backtest(bid)


def test_driver_cancellation_cannot_overwrite_server_running_state(queue_db):
    bid = qc_client.submit_backtest('pass','running')
    with storage.connect(queue_db) as conn:
        conn.execute("UPDATE backtest_queue SET status='running' WHERE id=?",(bid,))
    assert not qc_client.delete_backtest(bid)
    assert qc_client.read_backtest_status(bid)[0] == 'Running'
