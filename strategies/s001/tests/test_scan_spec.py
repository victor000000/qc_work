"""Tests for the universe scanner spec generator."""
import qc_storage as storage
from s001.tools.gen_scan_spec import generate_scan_spec


# Mini base that mimics the real anchor: `  for sym in equities:` at 2-space indent
_BASE_PY = """\
import math
class MeanReversionAlgorithm(QCAlgorithm):
 def Initialize(self): pass
 def _scan_entries(self, data, equities):
  candidates = []
  for sym in equities:
   score = 1.0
   candidates.append((sym, score, conv))
"""


def test_generate_scan_spec_inserts_priority_zero_spec(tmp_db, tmp_path):
    base = tmp_path / 'base.py'
    base.write_text(_BASE_PY)
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("""INSERT INTO fundamental_fields
            (id, category, field_name, accessor, container, probe_op,
             probe_threshold, probe_boost, data_type_hint)
            VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                    '>', '1e9', 1.08, 'absolute_amount')""")
        con.commit()

    generate_scan_spec(db_path=tmp_db, base_path=str(base), bake_hash='BAKE_TEST')

    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("SELECT name, priority FROM backtest_queue "
                    "WHERE name LIKE 'S001_SCAN_FUNDAMENTALS_%'")
        row = cur.fetchone()
    assert row is not None
    assert row[0] == 'S001_SCAN_FUNDAMENTALS_BAKE_TEST'
    assert row[1] == 0


def test_generate_scan_spec_skips_categorical(tmp_db, tmp_path):
    """Categorical fields aren't scanned — only numeric fields are included in _SF_FIELDS."""
    base = tmp_path / 'base.py'
    base.write_text(_BASE_PY)
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("""INSERT INTO fundamental_fields
            (id, category, field_name, accessor, container, probe_op,
             probe_threshold, probe_boost, data_type_hint)
            VALUES (1, 'ac', 'fin_health', '_ac_z.fin_health', 'asset_classification',
                    'eq', '"A"', 1.08, 'categorical')""")
        cur.execute("""INSERT INTO fundamental_fields
            (id, category, field_name, accessor, container, probe_op,
             probe_threshold, probe_boost, data_type_hint)
            VALUES (2, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                    '>', '1e9', 1.08, 'absolute_amount')""")
        con.commit()

    generate_scan_spec(db_path=tmp_db, base_path=str(base), bake_hash='BAKE_TEST')

    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        code = cur.execute(
            "SELECT code FROM backtest_queue "
            "WHERE name = 'S001_SCAN_FUNDAMENTALS_BAKE_TEST'").fetchone()[0]
    assert "'cash'" in code
    assert "'fin_health'" not in code
    assert 'PCT,' in code


def test_scan_spec_emits_pct_format(tmp_db, tmp_path):
    """Scanner block computes percentiles inline and logs in PCT format."""
    base = tmp_path / 'base.py'
    base.write_text(_BASE_PY)
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("""INSERT INTO fundamental_fields
            (id, category, field_name, accessor, container, probe_op,
             probe_threshold, probe_boost, data_type_hint)
            VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                    '>', '1e9', 1.08, 'absolute_amount')""")
        con.commit()

    generate_scan_spec(db_path=tmp_db, base_path=str(base), bake_hash='BAKE_TEST')

    with storage.connect(tmp_db) as con:
        code = con.execute(
            "SELECT code FROM backtest_queue "
            "WHERE name = 'S001_SCAN_FUNDAMENTALS_BAKE_TEST'").fetchone()[0]
    assert '_SF_DATA' in code
    assert '_scanner_done' in code
    assert "self.log(f'PCT," in code
    assert '_SF_FIELDS' in code
    assert '(1,' in code
    assert 'for _ssym in equities:' in code


def test_scan_spec_under_size_limit(tmp_db, tmp_path):
    """Scanner spec must fit within QC's 128k-character limit even with 900 fields."""
    base = tmp_path / 'base.py'
    base.write_text(_BASE_PY)
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        for i in range(1, 901):
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint)
                VALUES (?, 'bs', ?, ?, 'balance_sheet', '>', '1e9', 1.08, 'absolute_amount')""",
                (i, f'field_name_with_some_length_{i}', f'_bs_z.field_name_with_some_length_{i}'))
        con.commit()

    name, code_size, field_count = generate_scan_spec(
        db_path=tmp_db, base_path=str(base), bake_hash='BAKE_TEST')
    assert name is not None
    assert field_count == 900
    assert code_size < 128000, f'Spec is {code_size} chars, must be under 128k'
