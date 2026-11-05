"""Tests for the universe scanner log parser."""
import qc_storage as storage
from s001.tools.parse_scan_log import parse_scan_log


def _seed_field(db, field_id):
    with storage.connect(db) as con:
        con.execute("""INSERT INTO fundamental_fields
            (id, category, field_name, accessor, container, probe_op,
             probe_threshold, probe_boost)
            VALUES (?, 'bs', 'cash', ?, 'balance_sheet', '>', '1e9', 1.08)""",
            (field_id, f'_bs_z.cash_{field_id}'))
        con.commit()


def test_parses_pct_line_and_inserts_percentiles(tmp_db):
    _seed_field(tmp_db, 1)
    log_lines = ['PCT,1,10.9,25.75,50.5,75.25,90.1,100']

    n = parse_scan_log(db_path=tmp_db, log_lines=log_lines, bake_hash='BAKE_TEST',
                       scanned_at='2026-04-27T00:00:00+00:00')

    assert n == 1
    with storage.connect(tmp_db) as con:
        row = con.execute(
            "SELECT p10, p25, p50, p75, p90, sample_size FROM field_universe_stats "
            "WHERE field_id=1 AND bake_hash='BAKE_TEST'").fetchone()
    p10, p25, p50, p75, p90, sample_size = row
    assert p10 == 10.9
    assert p25 == 25.75
    assert p50 == 50.5
    assert p75 == 75.25
    assert p90 == 90.1
    assert sample_size == 100


def test_skips_pct_below_sample_threshold(tmp_db):
    _seed_field(tmp_db, 1)
    log_lines = ['PCT,1,1.0,2.0,3.0,4.0,5.0,29']  # n=29 below threshold

    parse_scan_log(db_path=tmp_db, log_lines=log_lines, bake_hash='BAKE_TEST')

    with storage.connect(tmp_db) as con:
        row = con.execute(
            "SELECT COUNT(*) FROM field_universe_stats WHERE field_id=1").fetchone()
    assert row[0] == 0


def test_ignores_non_pct_log_lines(tmp_db):
    _seed_field(tmp_db, 1)
    log_lines = [
        'some unrelated log line',
        '{"hello": "world"}',
        'PCT,malformed',
        'PCT,1,a,b,c,d,e,f',  # non-numeric
        'PCT,1,1.0,2.0,3.0,4.0,5.0,75',  # valid
    ]

    n = parse_scan_log(db_path=tmp_db, log_lines=log_lines, bake_hash='BAKE_TEST')

    assert n == 1
    with storage.connect(tmp_db) as con:
        row = con.execute(
            "SELECT sample_size FROM field_universe_stats WHERE field_id=1").fetchone()
    assert row[0] == 75


def test_replaces_existing_row_on_rerun(tmp_db):
    _seed_field(tmp_db, 1)
    parse_scan_log(db_path=tmp_db,
                   log_lines=['PCT,1,1.0,2.0,3.0,4.0,5.0,75'],
                   bake_hash='BAKE_TEST')
    parse_scan_log(db_path=tmp_db,
                   log_lines=['PCT,1,10.0,20.0,30.0,40.0,50.0,80'],
                   bake_hash='BAKE_TEST')
    with storage.connect(tmp_db) as con:
        row = con.execute(
            "SELECT p25, sample_size FROM field_universe_stats "
            "WHERE field_id=1 AND bake_hash='BAKE_TEST'").fetchone()
    assert row == (20.0, 80)
