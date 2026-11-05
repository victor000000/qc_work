"""Exercise the SQLite-to-DuckDB import, including deleted-ID high-water marks."""
import hashlib
from pathlib import Path
import sqlite3  # Legacy input fixture only; runtime storage is DuckDB.
import sys

import duckdb
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from migrate_duckdb import migrate


def test_import_preserves_rows_precise_numbers_indexes_and_retired_ids(tmp_path):
    source=tmp_path/'SAMPLE.db'
    with sqlite3.connect(source) as c:
        c.executescript('''CREATE TABLE parent(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE,metric REAL,payload BLOB,optional TEXT);
CREATE TABLE child(id INTEGER PRIMARY KEY,parent_id INTEGER REFERENCES parent(id));
CREATE TABLE settings(category TEXT,key TEXT,value TEXT,PRIMARY KEY(category,key));
CREATE INDEX idx_child_parent ON child(parent_id);
INSERT INTO parent(id,name) VALUES(99,'retired'); DELETE FROM parent;
INSERT INTO settings VALUES('credentials','token','private-example');''')
        c.execute('INSERT INTO parent VALUES(?,?,?,?,?)',(5,'kept',.123456789012345,b'\x00\xff',None))
        c.execute('INSERT INTO child VALUES(1,5)')
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    audit=tmp_path/'audit';audit.mkdir()
    record=migrate(source,audit)
    assert record['tables']['parent']['rows']==1
    assert record['legacy_sequence_high_water']['parent']==99
    assert record['indexes']==['idx_child_parent']
    assert not (audit/'SAMPLE_parquet/settings.parquet').exists()
    with duckdb.connect(str(source.with_suffix('.duckdb'))) as c:
        assert c.execute('SELECT count(*) FROM settings').fetchone() == (0,)
        assert c.execute('SELECT * FROM parent').fetchone()==(5,'kept',.123456789012345,b'\x00\xff',None)
        assert c.execute("INSERT INTO parent(name) VALUES('new') RETURNING id").fetchone()==(100,)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    with pytest.raises(FileExistsError):
        migrate(source,audit)
