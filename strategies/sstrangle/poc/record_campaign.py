#!/usr/bin/env python3
"""Snapshot only this PoC's queue identities; never changes queues or cloud runs."""
import ast
from datetime import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import qc_storage as storage

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'strategies/sstrangle/results/qc_baseline_poc_20261023'
ROLES={
    'SMOKE_V1':'invalid cost assumption; engineering failure',
    'SMOKE_V2':'quote-side engineering failure',
    'SMOKE_V3':'quote-side accounting smoke',
    'FULL_V3':'quote-side execution sensitivity; not source midpoint reproduction',
    'SMOKE_V4':'midpoint implementation failure before first fill',
    'SMOKE_V5':'documented source-convention accounting smoke',
    'FULL_V5':'primary documented source-convention baseline',
}

def main():
    records=[]
    with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as conn:
        conn.row_factory=storage.Row
        rows=conn.execute("SELECT name,status,project_id,backtest_id,code_hash,code,error_message,runtime_seconds,result_json FROM backtest_queue WHERE name LIKE 'SSTRANGLE_OO05_20261023_%' ORDER BY id").fetchall()
    for row in rows:
        d=dict(row);code=d.pop('code');result=json.loads(d.pop('result_json') or '{}')
        cfg=next(ast.literal_eval(node.value) for node in ast.walk(ast.parse(code))
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CONFIG' for t in node.targets))
        suffix=d['name'].removeprefix('SSTRANGLE_OO05_20261023_')
        d.update(role=ROLES[suffix],source_sha256=hashlib.sha256(code.encode()).hexdigest(),
                 config=cfg,runtime_statistics=result.get('runtimeStatistics',{}))
        records.append(d)
    payload=dict(observed_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                 scope='Read-only queue snapshot, not a substitute for terminal native cloud identity verification',
                 primary='SSTRANGLE_OO05_20261023_FULL_V5',trials=records)
    (OUT/'trial_ledger.json').write_text(json.dumps(payload,indent=2)+'\n')
    pd.DataFrame([{k:v for k,v in r.items() if k not in ('config','runtime_statistics')} for r in records]).to_csv(OUT/'trial_ledger.csv',index=False)
    print([(r['name'],r['status']) for r in records])

if __name__=='__main__':main()
