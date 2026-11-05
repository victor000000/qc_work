"""Read-only source availability survey; no trade or feature-performance claim."""
import argparse,json,sys,re,hashlib,ast
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import report as shared
ROOTS={'CL','RB','HO','NG','ZN','ZT','ZB','ZC','ZS','ZW','NQ','ES','HG','GC','SI'}
def audit(full,orders,rust,log):
 if orders or rust or int(full['statistics']['Total Orders'])!=0:raise ValueError('Availability survey traded')
 rt=full['runtimeStatistics']
 if shared.money(rt['Equity'])!=60000 or any(shared.money(rt[k])!=0 for k in ['Fees','Holdings','Unrealized']):raise ValueError('Availability account changed')
 rows=[json.loads(s) for s in re.findall(r'VOLATILITY_AVAILABILITY (\{[^\n]*\})',log)]
 if len(rows)!=60 or int(rt.get('availability_records',0))!=60 or int(rt.get('availability_roots',0))!=15 or rt.get('availability_no_trades')!='1':raise ValueError('Incomplete source survey')
 if {r['root'] for r in rows}!=ROOTS or len({(r['root'],r['native_id'],r['session']) for r in rows})!=60:raise ValueError('Source identities/dates incomplete')
 for root in ROOTS:
  subset=[r for r in rows if r['root']==root]
  if len({r['native_id'] for r in subset})!=2 or {r['session'] for r in subset}!={'2017-07-03','2017-07-04'}:raise ValueError('Two native deliveries/dates required per root')
 for r in rows:
  if set(r)!={'root','native_id','session','daily_rows','minute_rows','calendar_close','calendar_open_before_close'}:raise ValueError('Unexpected source market-value export field')
  if type(r['calendar_open_before_close']) is not bool or any(type(r[k]) is not int or r[k]<0 for k in ['daily_rows','minute_rows']):raise ValueError('Invalid source aggregate types')
 return rows

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('campaign',type=Path);a=p.parse_args();c=a.campaign.resolve();m=json.loads((c/'manifest.json').read_text())
 if m['phase']!='basket-volatility-coverage' or len(m['jobs'])!=1:raise ValueError('Wrong availability campaign')
 name=m['jobs'][0];cfg=m['variants']['vol_coverage'];code=(c/'vol_coverage.py').read_text();extra=json.loads((c/'extra_files.json').read_text())
 with shared.storage.connect(f'file:{shared.ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as conn:
  conn.row_factory=shared.storage.Row;row=dict(conn.execute('select * from backtest_queue where name=?',(name,)).fetchone())
 queued=json.loads(row['extra_files']) if isinstance(row['extra_files'],str) else row['extra_files']
 if row['code']!=code or queued!=extra or extra!={}:raise ValueError('Actual queued source differs from frozen no-dependency survey')
 if not row['backtest_id']:print(json.dumps({k:row[k] for k in ['name','status','project_id','backtest_id']}));return
 u,t=shared.credentials(shared.ROOT/'data/S001.duckdb');response=shared.read_research_backtest(u,t,c,name,row);full=response['backtest'];shared.validate_identity(full,row)
 status=shared.terminal_status(full)
 if status is None:print(json.dumps({k:full.get(k) for k in ['backtestId','status','completed','progress']}));return
 folder=shared.collect_terminal(u,t,c,name,row,response)
 result={'source_availability_only':True,'native_volatility_feature_verified':False,'strategy_calmar_proven':False,'backtest_id':row['backtest_id'],'status':status,'error':full.get('error'),'source_sha256':hashlib.sha256(code.encode()).hexdigest()}
 if status=='done':
  orders=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text());rust=rust['orders'] if isinstance(rust,dict) else rust
  rows=audit(full,orders,rust,(folder/'cloud.log').read_text());shared.write_tables(folder/'availability_report',dict(coverage=rows));result.update(actual_orders=0,actual_fills=0,actual_fees=0,ending_equity=60000,coverage_records=len(rows),root_count=15,coverage=rows)
 shared.atomic_json(c/'availability_summary.json',result);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
