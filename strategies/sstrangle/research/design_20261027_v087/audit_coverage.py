"""Read-only audit of a pinned provider Parquet release; no live DB or network."""
import json,hashlib
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import duckdb
OUT=Path(__file__).resolve().parent
ROOT=Path('/home/vic/data_providers')
lake=ROOT/'runtime/lake'; release=(lake/'CURRENT').read_text().strip()
m=lake/'snapshots'/release/'manifest.json'; raw=m.read_bytes(); manifest=json.loads(raw)
c=duckdb.connect(':memory:');c.execute('SET threads=2')
result={'checked_shanghai':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'release':release,'manifest_sha256':hashlib.sha256(raw).hexdigest(),'period':['2022-05-16','2026-10-22'],'tables':{},'limitations':['Counts are not selection-window completeness or strict timing acceptance.','Only published same-day contracts in the target window counted; raw/staged progress excluded.']}
for name in ['option_nbbo','option_intraday_greeks']:
 table=manifest['stores']['history']['tables'][name]
 c.read_parquet([str(lake/p['path']) for p in table['partitions']]).create_view('v',replace=True)
 extra=', count(gamma) gamma_nonnull' if name.endswith('greeks') else ''
 sql="""select underlying,count(*) row_count,count(distinct session_date) sessions,
 min(session_date) first_session,max(session_date) last_session,
 count(quote_ts) quote_ts_nonnull,count(available_at) available_at_nonnull"""+extra+""" from v
 where underlying in ('SPX','QQQ') and try_cast(split_part(contract_id,':',4) as date)=session_date
 and session_date between '2022-05-16' and '2026-10-22' group by 1 order by 1"""
 cur=c.execute(sql);result['tables'][name]=[dict(zip([x[0] for x in cur.description],row)) for row in cur.fetchall()]
 c.execute("create or replace temp table "+('qs' if name=='option_nbbo' else 'gs')+" as select distinct underlying,session_date from v where underlying in ('SPX','QQQ') and try_cast(split_part(contract_id,':',4) as date)=session_date and session_date between '2022-05-16' and '2026-10-22'")
result['quote_greek_session_overlap']=[{'underlying':s,'sessions':n} for s,n in c.execute('select underlying,count(*) from qs inner join gs using(underlying,session_date) group by 1').fetchall()]
result['source_receipts']=[]
for name in ['CURRENT_DATA_READINESS_20261027.json','TWELVE_TICKER_VERIFIED_COVERAGE_20261027.json','THETA_GAMMA_ACCESS_20261026.json','SPXW_SETTLEMENT_DATE_COVERAGE_20261026.json','QC_OO_TIMING_COMPLETED_QA_20261027.json']:
 p=ROOT/'docs/requirements'/name;b=p.read_bytes();(OUT/'evidence'/name).write_bytes(b);result['source_receipts'].append({'path':str(p),'sha256':hashlib.sha256(b).hexdigest()})
(OUT/'coverage_snapshot.json').write_text(json.dumps(result,indent=2,default=str)+'\n')
print(json.dumps(result,indent=2,default=str))
