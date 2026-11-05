"""Fixed-native-contract provider price/settlement bridge, after independent selection."""
from pathlib import Path
import json
import pandas as pd
from local_engine import Leg,account
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'strategies/sstrangle/results/qc_poc_20261027_v087'
def bridge():
 inputs=pd.read_parquet(OUT/'independent_selection_inputs.parquet');groups={(d,h):g.set_index('contract_id') for (d,h),g in inputs.groupby(['day','hm'])}
 local=pd.read_parquet(OUT/'local_episodes.parquet');output=[];summaries={}
 for key in ['c0','c1','p1']:
  folder=OUT/(key+'_baseline_evidence')
  if not (folder/'episodes.parquet').exists():continue
  eps=pd.read_parquet(folder/'episodes.parquet');legs=pd.read_parquet(folder/'legs.parquet');by_ep={str(ep):g for ep,g in legs.groupby('episode')}
  l=local[(local.strategy==key.upper())&(local['mode']=='equal_time_sensitivity')&(local['fill']=='legacy')];localmap={r.day+r.slot:r for r in l.itertuples()}
  for r in eps.itertuples():
   slot=r.decision_at[11:16];lr=localmap.get(r.day+slot);g=groups.get((r.day,slot));base={'strategy':key,'episode':str(r.episode),'day':r.day,'slot':slot}
   if g is None or lr is None:output.append(dict(base,status='no_joint_fill_for_bridge'));continue
   selected=[];nl=by_ep[str(r.episode)]
   for x in nl.itertuples():
    identity=f'US:OPRA:SPXW:{r.day}:{x.right}:{x.strike:g}'
    if identity not in g.index:break
    v=g.loc[identity];selected.append((Leg(identity,float(x.strike),x.right,float(v.delta),float(v.bid),float(v.ask),float(v.spot)),float(x.quantity)))
   if len(selected)!=len(nl):output.append(dict(base,status='native_contract_absent_provider'));continue
   fixed=account(selected,lr.settlement,'legacy')
   if fixed is None:output.append(dict(base,status='invalid_provider_fixed_credit'));continue
   expiry=sum(q*100*(max(x.strike-lr.settlement,0) if x.right=='P' else max(lr.settlement-x.strike,0)) for x,q in selected)
   native_official=float(r.entry_credit-r.opening_fees+expiry)
   settle_delta=native_official-r.pnl
   quote_delta=fixed['pnl']-native_official
   selection_delta=lr.pnl-fixed['pnl']
   residual=lr.pnl-r.pnl-settle_delta-quote_delta-selection_delta
   assert abs(residual)<1e-7
   output.append(dict(base,status='attributed_joint_fill',native_pnl=r.pnl,local_pnl=lr.pnl,settlement_delta=settle_delta,quote_fill_delta=quote_delta,selection_delta=selection_delta,residual=residual))
  rows=[x for x in output if x['strategy']==key and x['status']=='attributed_joint_fill']
  summaries[key]={'joint_fill_bridge_episodes':len(rows),**{x:sum(r[x] for r in rows) for x in ['settlement_delta','quote_fill_delta','selection_delta','residual']},'interpretation':'fixed-order attribution on jointly filled slots only; does not explain missing/admitted trades or reproduce native funding'}
 pd.DataFrame(output).to_parquet(OUT/'fixed_contract_bridge.parquet',index=False)
 (OUT/'fixed_contract_bridge.json').write_text(json.dumps(summaries,indent=2)+'\n')
if __name__=='__main__':bridge()
