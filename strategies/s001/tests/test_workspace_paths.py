"""Reorganisation must retain research gates, round history and unique numbering."""
import qc_storage as storage
from s001 import gen_s001_strategies as research
from s001 import next_round_s001


def test_moved_cohort_evidence_is_still_loaded(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(research, 'RESEARCH_DIR', tmp_path)
    cohort = dict(parent='synthetic', sector=10, regimes=['up', 'down'], rate=.75)
    for name in ['cohort_silent_signatures.json', 'cohort_productive_signatures.json']:
        (tmp_path / name).write_text(json.dumps([cohort]))
    (tmp_path / 'silent_sec_signatures.json').write_text(json.dumps([
        dict(parent='synthetic', sector=10, regime_pair='up+down', gate_class='test')]))
    assert research._load_dead_cohort_signatures() == {('synthetic', 10, ('down', 'up'))}
    assert research._load_productive_cohort_signatures() == [dict(parent='synthetic', sector=10, regimes=('down', 'up'), rate=.75)]
    assert research._load_silent_sec_sigs() == {('synthetic', 10, ('down', 'up'), 'test')}


def test_round_id_uses_numeric_max_and_completed_history(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    data.mkdir()
    archive = tmp_path / 'strategies/s001/archive/rounds'
    archive.mkdir(parents=True)
    (archive / 'gen_s001_R10002.py').write_text('pass')
    with storage.connect(data / 'S001.duckdb') as conn:
        conn.execute('CREATE TABLE backtest_queue(name TEXT)')
        conn.execute('CREATE TABLE experiments(name TEXT)')
        conn.executemany('INSERT INTO backtest_queue VALUES (?)',
                         [(f'S001_R9999_probe_{i}',) for i in range(128)] + [('S001_R10000_probe',)])
        conn.execute("INSERT INTO experiments VALUES ('S001_R10003_cleaned_from_queue')")
    monkeypatch.setattr(next_round_s001, 'DATA_DIR', data)
    monkeypatch.setattr(next_round_s001, 'WORKSPACE_ROOT', tmp_path)
    assert next_round_s001._next_rid() == 10004
