#!/usr/bin/env python3
"""Publish immutable, checksummed Parquet research snapshots from QC DuckDB stores."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

import qc_storage as storage


def export_database(source, destination):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.parquet-',dir=destination.parent))
    manifest=dict(source=str(source),created_utc=datetime.now(timezone.utc).isoformat(),
        excluded_tables=['settings','code_blobs','_qc_storage_meta'],tables={})
    with storage.connect(source.as_uri()+'?mode=ro',uri=True) as wrapper:
        wrapper._open()
        con=wrapper._native
        tables=[r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main' AND table_type='BASE TABLE'").fetchall()]
        for table in sorted(set(tables)-set(manifest['excluded_tables'])):
            if not table.replace('_','').isalnum():
                raise ValueError('Unsafe export table name')
            query=f'SELECT * FROM "{table}"'
            if table=='backtest_queue':
                query=f'SELECT * EXCLUDE (code,extra_files) FROM "{table}"'
            path=stage/(table+'.parquet')
            con.execute(f'COPY ({query} ORDER BY ALL) TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(path)])
            os.chmod(path,0o600)
            count=con.execute('SELECT count(*) FROM read_parquet(?)',[str(path)]).fetchone()[0]
            expected=con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            if count!=expected:
                raise ValueError('Incomplete Parquet export')
            schema=[dict(name=r[0],type=r[1]) for r in con.execute('DESCRIBE SELECT * FROM read_parquet(?)',[str(path)]).fetchall()]
            manifest['tables'][table]=dict(rows=count,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),schema=schema)
    (stage/'manifest.json').write_text(json.dumps(manifest,indent=2))
    stage.rename(destination)
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    for source in sorted(args.data_dir.glob('S*.duckdb')):
        m=export_database(source,args.output/source.stem)
        print(source.name+': '+str(sum(t['rows'] for t in m['tables'].values()))+' exported rows')


if __name__=='__main__':
    main()
