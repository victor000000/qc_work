"""Revalue fixed native trade tapes against pinned official expiry values.
This is ex-post attribution, never a funded replay or a changed native result.
"""
import hashlib,json
from pathlib import Path
import duckdb,pandas as pd
P=Path(__file__).parent;ROOT=P.parents[3];OUT=ROOT/'strategies/sstrangle/results/qc_poc_20261027_v087';LAKE=Path('/home/vic/data_providers/runtime/lake')
def run():
 snap=json.loads((OUT/'coverage_snapshot.json').read_text());raw=(LAKE/'snapshots'/snap['release']/'manifest.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==snap['manifest_sha256']
 m=json.loads(raw);files=[str(LAKE/x['path']) for x in m['stores']['history']['tables']['index_option_settlements']['partitions']]
 c=duckdb.connect(':memory:');c.read_parquet(files).create_view('settlements');sett=c.execute("select cast(expiry as varchar) session_day,min(settlement_value) lo,max(settlement_value) hi from settlements where underlying='SPX' group by 1").df();assert (abs(sett.hi-sett.lo)<1e-8).all();values=dict(zip(sett.session_day,sett.lo));summaries={};allrows=[]
 for folder in sorted(OUT.glob('*_evidence')):
  if not (folder/'episodes.parquet').exists():continue
  key=folder.name.removesuffix('_evidence');eps=pd.read_parquet(folder/'episodes.parquet');legs=pd.read_parquet(folder/'legs.parquet');groups={str(k):g for k,g in legs.groupby('episode')};rows=[]
  for r in eps.itertuples():
   spot=values.get(r.day)
   if spot is None:continue
   g=groups[str(r.episode)];expiry=sum(float(x.quantity)*100*max(0,float(x.strike)-spot if x.right=='P' else spot-float(x.strike)) for x in g.itertuples());pnl=float(r.entry_credit-r.opening_fees+expiry)
   rows.append(dict(run=key,episode=str(r.episode),day=r.day,native_spot=r.settlement_spot,official_spot=spot,native_pnl=r.pnl,official_fixed_tape_pnl=pnl,difference=pnl-r.pnl))
  frame=pd.DataFrame(rows);allrows.extend(rows)
  summaries[key]={'native_episodes':len(eps),'matched_episodes':len(rows),'missing_settlement_episodes':len(eps)-len(rows),'native_pnl_matched':float(frame.native_pnl.sum()) if len(rows) else None,'official_fixed_tape_pnl':float(frame.official_fixed_tape_pnl.sum()) if len(rows) else None,'settlement_difference':float(frame.difference.sum()) if len(rows) else None,'days_with_different_spot':int(frame.loc[abs(frame.native_spot-frame.official_spot)>1e-8,'day'].nunique()) if len(rows) else 0}
 pd.DataFrame(allrows).to_parquet(OUT/'official_settlement_fixed_tapes.parquet',index=False)
 result={'scope':'Ex-post fixed native trades; full settlement coverage does not imply independent quote coverage. No admission, capital, margin or path recalculation. No causal performance claim.','provider_release':snap['release'],'manifest_sha256':snap['manifest_sha256'],'runs':summaries};(OUT/'official_settlement_fixed_tapes.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':print(json.dumps(run(),indent=2))
