"""Smoke test for pytest infrastructure."""

from s001.paths import WORKSPACE_ROOT, DATA_DIR
import ast
import re
import qc_storage as storage
from pathlib import Path


def test_pytest_works():
    assert 1 + 1 == 2


def test_tmp_db_has_tables(tmp_db):
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = {r[0] for r in cur.fetchall()}
        assert 'fundamental_fields' in tables
        assert 'probe_results' in tables
        assert 'experiments' in tables
        assert 'backtest_queue' in tables


BASE_PATH = Path(str(WORKSPACE_ROOT / 'strategies/s001/s001_20260425_base.py'))


class TestBaseRefactor:
    def test_file_parses(self):
        ast.parse(BASE_PATH.read_text())

    def test_entry_anchor_present(self):
        assert '   # --- ENTRY INJECT POINT ---' in BASE_PATH.read_text()

    def test_exit_anchor_present(self):
        assert '   # --- EXIT INJECT POINT ---' in BASE_PATH.read_text()

    def test_compute_regime_method_defined(self):
        assert re.search(r'def _compute_regime\(self\)', BASE_PATH.read_text())

    def test_regime_assigned_in_on_data(self):
        src = BASE_PATH.read_text()
        on_data_match = re.search(
            r'def on_data\(self, data\):.*?(?=\n def )', src, re.DOTALL)
        assert on_data_match
        body = on_data_match.group(0)
        regime_pos = body.find('self._regime = self._compute_regime()')
        exits_pos = body.find('self._scan_exits(')
        assert regime_pos > 0 and exits_pos > 0
        assert regime_pos < exits_pos, 'regime must be computed before scan_exits'

    def test_aliases_set_in_compute_regime(self):
        src = BASE_PATH.read_text()
        assert 'self._qa_scan = qa' in src
        assert 'self._ha_scan = ha' in src

    def test_baked_probes_intact(self):
        src = BASE_PATH.read_text()
        for marker in ('BAKE-8', 'BAKE-16', 'BAKE-29', 'BAKE-53', 'BAKE-58', 'BAKE-62'):
            assert marker in src, f'{marker} missing — refactor broke baked code'

    def test_stale_perfopt_cache_removed(self):
        src = BASE_PATH.read_text()
        scan_entries_match = re.search(
            r'def _scan_entries\(self.*?(?=\n def )', src, re.DOTALL)
        assert scan_entries_match
        body = scan_entries_match.group(0)
        assert 'self._ha_scan = list(self.history' not in body
        assert 'self._qa_scan = list(self.history' not in body
