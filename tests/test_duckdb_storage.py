"""Financial persistence, producer compatibility and interprocess access tests."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import qc_storage as storage

ROOT=Path(__file__).resolve().parents[1]


def test_duplicate_does_not_erase_prior_work_and_rollback_is_atomic(tmp_path):
    p=tmp_path/'sample.duckdb'
    with storage.connect(p) as c:
        c.execute('CREATE TABLE sample(id INTEGER PRIMARY KEY,name TEXT UNIQUE,metric REAL)')
        c.execute("INSERT INTO sample(name,metric) VALUES ('first',0.123456789012345)")
        with pytest.raises(storage.IntegrityError):
            c.execute("INSERT INTO sample(name,metric) VALUES ('first',3)")
        c.execute("INSERT INTO sample(name,metric) VALUES ('second',2)")
    with pytest.raises(RuntimeError):
        with storage.connect(p) as c:
            c.execute("UPDATE sample SET metric=99")
            raise RuntimeError('abort')
    with storage.connect(p) as c:
        rows=c.execute('SELECT name,metric FROM sample ORDER BY id').fetchall()
    assert rows==[('first',0.123456789012345),('second',2)]


def test_python_and_rust_writers_share_access_lock(tmp_path):
    binary=ROOT/'target/debug/qc-backtest-server'
    if not binary.exists():
        pytest.skip('Build the Rust server first')
    subprocess.run([str(binary),'--data-dir',str(tmp_path),'init-strategy','--strategy','sconcurrent'],check=True,capture_output=True)
    path=tmp_path/'SCONCURRENT.duckdb'
    code=tmp_path/'main.py';code.write_text('print(1)')
    python_code="""import qc_storage as s,sys
for i in range(12):
 with s.connect(sys.argv[1]) as c:
  c.execute('INSERT INTO backtest_queue(name,code) VALUES (?,?)',('python_'+str(i),'pass'))
"""
    writer=subprocess.Popen([sys.executable,'-c',python_code,str(path)],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    for i in range(8):
        subprocess.run([str(binary),'--data-dir',str(tmp_path),'queue','--strategy','sconcurrent',
            '--name','rust_'+str(i),'--code-file',str(code)],check=True,capture_output=True,timeout=20)
    out,err=writer.communicate(timeout=20)
    assert writer.returncode==0,err.decode()
    with storage.connect(path) as c:
        assert c.execute('SELECT count(*),count(distinct id),count(distinct name) FROM backtest_queue').fetchone()==(20,20,20)


def test_snapshot_excludes_private_settings_from_research_release(tmp_path):
    sys.path.insert(0,str(ROOT/'scripts'))
    from export_results import export_database
    p=tmp_path/'sample.duckdb'
    with storage.connect(p) as c:
        c.execute('CREATE TABLE settings(category TEXT,key TEXT,value TEXT)')
        c.execute("INSERT INTO settings VALUES ('credentials','token','private-example')")
        c.execute('CREATE TABLE experiments(id INTEGER PRIMARY KEY,name TEXT)')
        c.execute("INSERT INTO experiments(name) VALUES ('example')")
    m=export_database(p,tmp_path/'release')
    assert set(m['tables'])=={'experiments'}
    assert not (tmp_path/'release/settings.parquet').exists()
    dest=tmp_path/'snapshot.duckdb'
    storage.snapshot(p,dest)
    with storage.connect(dest) as c:
        assert c.execute('SELECT value FROM settings').fetchone()==('private-example',)
