"""Smoke test for gen_s001_R603_mega.py dry-run mode."""
import hashlib
import importlib.util
import sqlite3
from pathlib import Path

import pytest

GEN_PATH = Path('/home/txy/qc_work/data/gen_s001_R603_mega.py')


def _load_gen_module():
    spec = importlib.util.spec_from_file_location('gen_s001_R603_mega', GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_min_db(tmp_db, base_path):
    """Seed: 2 templated fields, 1 settings row with the live base.py md5."""
    md5 = hashlib.md5(Path(base_path).read_bytes()).hexdigest()
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO fundamental_fields "
            "(id, category, field_name, accessor, container, period, probe_op, probe_threshold, probe_gate, probe_boost, data_type_hint) "
            "VALUES (1, 'ops', 'revenue_growth', '_ops_z.revenue_growth.one_year', "
            "'operation_ratios', 'one_year', '>', '0.10', 'decline > .12', 1.10, 'numeric')")
        cur.execute(
            "INSERT INTO fundamental_fields "
            "(id, category, field_name, accessor, container, period, probe_op, probe_threshold, probe_gate, probe_boost, data_type_hint) "
            "VALUES (2, 'vr', 'pe_ratio', '_vr_z.pe_ratio', 'valuation_ratios', NULL, "
            "'<', '15', 'decline > .10', 1.10, 'numeric')")
        cur.execute("INSERT INTO settings (category, key, value) VALUES ('strategy', 'current_bake_hash', ?)", (md5,))
        con.commit()
    return md5


def test_dry_run_emits_expected_specs(tmp_db):
    base = '/home/txy/qc_work/data/s001/s001_20260425_base.py'
    md5 = _seed_min_db(tmp_db, base)

    mod = _load_gen_module()
    specs = mod.build_specs(db_path=tmp_db, base_path=base, round_n=603,
                            expected_hash=md5, dry_run=True)
    # 2 fields × 6 mechanisms + 3 NOOPs = 15
    assert len(specs) == 15

    noops = [s for s in specs if 'VBAKEMG_NOOP_' in s[0]]
    mega = [s for s in specs if 'VBAKEMG_NOOP_' not in s[0]]
    assert len(noops) == 3
    assert len(mega) == 12

    for name, code, _ in mega:
        assert '_ops_z.revenue_growth.one_year' in code or '_vr_z.pe_ratio' in code


def test_dry_run_all_specs_ast_parse(tmp_db):
    import ast
    base = '/home/txy/qc_work/data/s001/s001_20260425_base.py'
    md5 = _seed_min_db(tmp_db, base)
    mod = _load_gen_module()
    specs = mod.build_specs(db_path=tmp_db, base_path=base, round_n=603,
                            expected_hash=md5, dry_run=True)
    for name, code, _ in specs:
        ast.parse(code)


def test_hash_mismatch_aborts(tmp_db):
    base = '/home/txy/qc_work/data/s001/s001_20260425_base.py'
    _seed_min_db(tmp_db, base)
    mod = _load_gen_module()
    with pytest.raises(AssertionError, match='Hash mismatch'):
        mod.build_specs(db_path=tmp_db, base_path=base, round_n=603,
                        expected_hash='deadbeef', dry_run=True)


def test_anchors_required(tmp_db, tmp_path):
    fake_base = tmp_path / 'fake_base.py'
    fake_base.write_text('# no anchors here\nprint("hi")\n')
    md5 = hashlib.md5(fake_base.read_bytes()).hexdigest()
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO settings (category, key, value) VALUES ('strategy', 'current_bake_hash', ?)", (md5,))
    mod = _load_gen_module()
    with pytest.raises(AssertionError, match='anchor'):
        mod.build_specs(db_path=tmp_db, base_path=str(fake_base), round_n=603,
                        expected_hash=md5, dry_run=True)
