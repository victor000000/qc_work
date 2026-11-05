#!/usr/bin/env python3
"""One-time verified SQLite import. Originals remain untouched; exports omit settings."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import duckdb
from qc_storage import DATETIME_SQL


def identifier(name):
    return '"'+name.replace('"','""')+'"'


def digest_rows(rows):
    values=[]
    for row in rows:
        encoded=json.dumps(list(row),ensure_ascii=False,separators=(',',':'),
            default=lambda x: {'bytes':bytes(x).hex()}).encode()
        values.append(hashlib.sha256(encoded).digest())
    return hashlib.sha256(b''.join(sorted(values))).hexdigest()


def migrate(source, audit_root):
    target=source.with_suffix('.duckdb')
    if target.exists():
        raise FileExistsError(target)
    backup=audit_root/(source.stem+'.sqlite3')
    with sqlite3.connect(f'file:{source.resolve()}?mode=ro',uri=True) as origin:
        with sqlite3.connect(backup) as snap:
            origin.backup(snap)
    os.chmod(backup,0o600)
    old=sqlite3.connect(f'file:{backup.resolve()}?mode=ro',uri=True)
    if old.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
        raise ValueError('Source integrity check failed')
    tables=[r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    sequences=dict(old.execute('SELECT name,seq FROM sqlite_sequence')) if old.execute("SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").fetchone() else {}
    pending=set(tables);ordered=[]
    while pending:
        ready=sorted(t for t in pending if all(r[2] not in pending for r in old.execute(f'PRAGMA foreign_key_list({identifier(t)})')))
        if not ready:
            raise ValueError('Cyclic foreign keys need explicit migration')
        ordered.extend(ready);pending-=set(ready)
    temp=target.with_name(target.name+'.migrating')
    if temp.exists():
        raise FileExistsError(temp)
    con=duckdb.connect(str(temp))
    os.chmod(temp,0o600)
    con.execute("SET TimeZone='UTC'")
    con.execute(DATETIME_SQL)
    con.execute('CREATE TABLE _qc_storage_meta(key VARCHAR PRIMARY KEY,value VARCHAR)')
    con.execute('INSERT INTO _qc_storage_meta VALUES (?,?)',['user_version',str(old.execute('PRAGMA user_version').fetchone()[0])])
    counts={}
    con.execute('BEGIN')
    try:
        for table in ordered:
            columns=old.execute(f'PRAGMA table_info({identifier(table)})').fetchall()
            definitions=[]
            primary=[r[1] for r in sorted(columns,key=lambda r:r[5]) if r[5]]
            for _,name,kind,required,default,pk in columns:
                upper=(kind or '').upper()
                native=('BIGINT' if 'INT' in upper else 'DOUBLE' if any(x in upper for x in ['REAL','FLOA','DOUB'])
                        else 'BLOB' if 'BLOB' in upper else 'VARCHAR')
                definition=identifier(name)+' '+native
                if len(primary)==1 and pk and native=='BIGINT':
                    sequence=table+'_'+name+'_seq'
                    maximum=old.execute(f'SELECT coalesce(max({identifier(name)}),0) FROM {identifier(table)}').fetchone()[0]
                    maximum=max(int(maximum),int(sequences.get(table,0)))
                    con.execute(f'CREATE SEQUENCE {identifier(sequence)} START {maximum+1}')
                    definition+=f" DEFAULT nextval('{sequence}')"
                elif default is not None:
                    if 'CURRENT_TIMESTAMP' in default.upper():
                        default="(datetime('now'))"
                    definition+=' DEFAULT '+default
                if required:
                    definition+=' NOT NULL'
                definitions.append(definition)
            if primary:
                definitions.append('PRIMARY KEY ('+','.join(map(identifier,primary))+')')
            for index in old.execute(f'PRAGMA index_list({identifier(table)})').fetchall():
                if index[2] and index[3]!='pk':
                    names=[r[2] for r in old.execute(f'PRAGMA index_info({identifier(index[1])})')]
                    definitions.append('UNIQUE ('+','.join(map(identifier,names))+')')
            references={}
            for ref in old.execute(f'PRAGMA foreign_key_list({identifier(table)})'):
                references.setdefault((ref[0],ref[2]),[]).append((ref[3],ref[4]))
            for (_,parent),keys in references.items():
                definitions.append('FOREIGN KEY ('+','.join(identifier(k[0]) for k in keys)+') REFERENCES '+identifier(parent)+' ('+','.join(identifier(k[1]) for k in keys)+')')
            con.execute('CREATE TABLE '+identifier(table)+' ('+','.join(definitions)+')')
            rows=old.execute('SELECT * FROM '+identifier(table)).fetchall()
            if table == 'settings':
                names = [column[1] for column in columns]
                if {'category', 'key'} <= set(names):
                    cat_index, key_index = names.index('category'), names.index('key')
                    rows = [row for row in rows if row[cat_index] != 'credentials'
                            and not any(term in str(row[key_index]).lower()
                                        for term in ('secret', 'password', 'token', 'api_key', 'oauth'))]

            # Arrow imports bulk data with explicit target types; avoid per-row commits.
            if rows:
                import pyarrow as pa
                arrays={c[1]:[r[i] for r in rows] for i,c in enumerate(columns)}
                data=pa.table(arrays)
                con.register('legacy_rows',data)
                con.execute('INSERT INTO '+identifier(table)+' SELECT * FROM legacy_rows')
                con.unregister('legacy_rows')
            actual=con.execute('SELECT * FROM '+identifier(table)).fetchall()
            before,after=digest_rows(rows),digest_rows(actual)
            if len(actual)!=len(rows) or before!=after:
                raise ValueError('Row verification failed for '+table)
            counts[table]=dict(rows=len(rows),logical_sha256=before)
        indexes=[]
        for name,sql in old.execute("SELECT name,sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"):
            if ' WHERE ' in sql.upper():
                raise ValueError('Partial index requires explicit migration: '+name)
            con.execute(sql)
            indexes.append(name)
        con.execute('COMMIT')
    except BaseException:
        con.execute('ROLLBACK');con.close();old.close()
        raise
    release=audit_root/(source.stem+'_parquet');release.mkdir()
    os.chmod(release,0o700)
    for table,record in counts.items():
        if table in ['settings','code_blobs']:
            record['parquet']='excluded: operational/private settings or source blobs'
            continue
        path=release/(table+'.parquet')
        con.execute('COPY (SELECT * FROM '+identifier(table)+') TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(path.resolve())])
        os.chmod(path,0o600)
        record['parquet_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        if con.execute('SELECT count(*) FROM read_parquet(?)',[str(path)]).fetchone()[0]!=record['rows']:
            raise ValueError('Parquet verification failed')
    con.execute('CHECKPOINT');con.close();old.close()
    temp.replace(target)
    record=dict(source=str(source.resolve()),target=str(target.resolve()),backup=str(backup.resolve()),
        tables=counts,indexes=indexes,legacy_sequence_high_water=sequences,
        duckdb_version=duckdb.__version__,status='verified')
    (audit_root/(source.stem+'_manifest.json')).write_text(json.dumps(record,indent=2))
    print(source.name+' -> '+target.name+': '+str(sum(v['rows'] for v in counts.values()))+' verified rows',flush=True)
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data')
    p.add_argument('--audit-dir',type=Path,required=True)
    p.add_argument('--source',action='append',type=Path)
    args=p.parse_args()
    pid=args.data_dir/'qc-server.pid'
    if pid.exists():
        try:os.kill(int(pid.read_text().strip()),0)
        except (ProcessLookupError,ValueError):pass
        else:raise RuntimeError('Stop the running QC server before migrating')
    args.audit_dir.mkdir(parents=True,exist_ok=False);os.chmod(args.audit_dir,0o700)
    sources=args.source or [p for p in sorted(args.data_dir.glob('S*.db')) if p.stat().st_size>0]
    records=[migrate(source,args.audit_dir) for source in sources]
    (args.audit_dir/'manifest.json').write_text(json.dumps(dict(created_utc=datetime.now(timezone.utc).isoformat(),databases=records),indent=2))


if __name__=='__main__':
    main()
