"""Independent fixed-tape payoff reproduction and raw-data feature parity audit."""
import hashlib,json,re
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import pandas as pd
from optimize import ROOT,OUT,OLD,BASES
from feature_rule import feature_value,rule_pass

def reconstruct(folder):
 orders=json.loads((folder/'orders.json').read_text());spots={};events=set();positions=defaultdict(float);opening=[]
 for o in orders:
  sid=o['symbol']['id'];symbol=o['symbol']['value'].replace(' ','');match=re.fullmatch(r'SPXW(\d{6})([CP])(\d{8})',symbol);assert match
  expiry=datetime.strptime(match[1],'%y%m%d').date().isoformat();right=match[2];strike=int(match[3])/1000
  epmatch=re.search(r';e=(\d+);r=OPEN;',o.get('tag',''))
  for e in o.get('events',[]):
   assert e['id'] not in events;events.add(e['id']);qty=float(e.get('fillQuantity',0));positions[sid]+=qty
   if o['type']==6:
    sm=re.search(r'Underlying: ([0-9]+(?:\.[0-9]+)?)',e.get('message',''))
    if sm:
     spot=float(sm[1]);assert expiry not in spots or abs(spots[expiry]-spot)<1e-8;spots[expiry]=spot
   if qty and epmatch:opening.append(dict(episode=epmatch[1],expiry=expiry,right=right,strike=strike,quantity=qty,price=float(e['fillPrice']),fee=float(e.get('orderFeeAmount') or 0)))
 assert all(abs(q)<1e-8 for q in positions.values())
 legs=pd.DataFrame(opening);legs['spot']=legs.expiry.map(spots);assert legs.spot.notna().all()
 legs['intrinsic']=[max(0,r.spot-r.strike) if r.right=='C' else max(0,r.strike-r.spot) for r in legs.itertuples()]
 legs['reproduced_pnl']=legs.quantity*(legs.intrinsic-legs.price)*100-legs.fee
 calc=legs.groupby('episode').agg(pnl=('reproduced_pnl','sum'),fees=('fee','sum'),legs=('quantity','size'))
 native=pd.read_parquet(folder/'episodes.parquet').set_index('episode');assert set(calc.index)==set(native.index)
 error=(calc.pnl-native.pnl).abs();assert error.max()<1e-5
 b=json.loads((folder/'backtest.json').read_text())['backtest'];account=float(b['statistics']['End Equity'])-float(b['statistics']['Start Equity']);assert abs(calc.pnl.sum()-account)<.01
 return calc,dict(episodes=len(calc),events=len(events),net_pnl=float(calc.pnl.sum()),native_account_pnl=account,max_episode_error=float(error.max()),residual_contracts=0,scope='Independent arithmetic from native fills/contract identities and native expiry reference; not independently sourced option prices or a native margin replica')

def main():
 rules=json.loads((OUT/'frozen_rules.json').read_text());prices=pd.read_parquet(OLD/'provider/us_prices/data.parquet');results={}
 for kind,(key,folder,capital) in BASES.items():
  calc,result=reconstruct(folder);calc.to_parquet(OUT/(kind+'_local_baseline_reproduction.parquet'))
  rule=rules[kind];f=pd.read_parquet(OLD/'local'/(key+'_features.parquet'));symbol=rule['feature'].split('_')[0].upper();g=prices[prices.symbol==symbol].sort_values('date');raw=[[str(r.date),float(r.high),float(r.low),float(r.close),int(r.volume)] for r in g.itertuples()]
  day=f.decision_at.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d');values={d:feature_value(raw,d,rule['feature']) for d in day.unique()};recomputed=day.map({d:v[0] for d,v in values.items()})
  err=(recomputed-f[rule['feature']]).abs();assert err.max()<1e-10
  native_decision=recomputed.map(lambda v:rule_pass(v,rule['threshold'],rule['side']));local_decision=f[rule['feature']].gt(rule['threshold']) if rule['side']=='above' else f[rule['feature']].le(rule['threshold'])
  assert (native_decision==local_decision).all()
  selected=calc.loc[f.loc[native_decision,'episode']];assert abs(selected.pnl.sum()-rule['full_local']['pnl'])<.01
  result.update(feature=rule['feature'],feature_max_error=float(err.max()),feature_decision_mismatches=0,selected_episodes=len(selected),selected_reproduced_pnl=float(selected.pnl.sum()),smoke_expected_trades=int((native_decision&day.between('2024-01-02','2024-01-12')).sum()))
  results[kind]=result
 (OUT/'baseline_recheck.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
if __name__=='__main__':main()
