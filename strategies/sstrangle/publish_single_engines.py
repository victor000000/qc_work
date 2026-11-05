#!/usr/bin/env python3
"""Publish immutable AKQuant execution/audit tables with scenario provenance."""
import argparse
import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('batch',type=Path)
    args=p.parse_args()
    for local in sorted((args.batch/'local').iterdir()):
        destination=local/'engine_warehouse'
        if destination.exists():
            continue
        fills=[];audits=[];sources={}
        for kind in ['optimization','provider','provider_selection_validation']:
            for path in sorted((local/kind).glob('*/executions.csv')):
                audit_path=path.parent/'audit.json'
                if not audit_path.exists():
                    raise ValueError('Execution ledger without audit: '+str(path))
                audit=json.loads(audit_path.read_text())
                frame=pd.read_csv(path)
                if len(frame)!=audit['engine_executions'] or not audit['fill_price_quantity_fee_audit'] or audit['residual_positions']:
                    raise ValueError('Invalid engine audit: '+str(audit_path))
                run_id=kind+'/'+path.parent.name
                frame['engine_run_id']=run_id
                frame['source_kind']=kind
                frame['ticker']=local.name
                frame['timestamp']=pd.to_datetime(frame['timestamp'],utc=True)
                fills.append(frame)
                audits.append(dict(ticker=local.name,engine_run_id=run_id,source_kind=kind,**audit))
                sources[str(path.relative_to(local))]=hashlib.sha256(path.read_bytes()).hexdigest()
                sources[str(audit_path.relative_to(local))]=hashlib.sha256(audit_path.read_bytes()).hexdigest()
        if not fills:
            continue
        summary_path=local/'optimization/summary.json'
        if summary_path.exists():
            summary=json.loads(summary_path.read_text())
            actual=sum(a['source_kind']=='optimization' for a in audits)
            previous=summary.get('unique_engine_replays')
            if previous!=actual:
                (local/'optimization/metadata_reconciliation.json').write_text(json.dumps(dict(
                    old_unique_engine_replays=previous,actual_nonempty_engine_replays=actual,
                    reason='Empty cycle subsets retain cash and require no engine execution; exclude them from engine-run counts'),indent=2))
            summary['unique_engine_replays']=actual
            summary['empty_subsets_are_flat_cash']=True
            summary_path.write_text(json.dumps(summary,indent=2))
        destination.mkdir()
        con=duckdb.connect(str(destination/'engines.duckdb'))
        manifest=dict(sources=sources,tables={},policy='Alternative engine scenarios overlap. Partition by (ticker, engine_run_id); never aggregate them as one portfolio. Prices are frozen QC fills or explicitly labeled provider trade-print sensitivities.')
        for name,frame in [('akquant_executions',pd.concat(fills,ignore_index=True)),
                           ('akquant_run_audits',pd.DataFrame(audits))]:
            con.register('frame',frame)
            con.execute(f'CREATE TABLE {name} AS SELECT * FROM frame')
            path=destination/(name+'.parquet')
            con.execute(f'COPY {name} TO ? (FORMAT PARQUET, COMPRESSION ZSTD)',[str(path)])
            schema=[dict(name=r[0],type=r[1]) for r in con.execute(f'DESCRIBE {name}').fetchall()]
            manifest['tables'][name]=dict(rows=len(frame),schema=schema,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            con.unregister('frame')
        con.close()
        (destination/'manifest.json').write_text(json.dumps(manifest,indent=2))
        print(local.name,len(audits),'audited runs,',sum(len(f) for f in fills),'executions',flush=True)


if __name__=='__main__':
    main()
