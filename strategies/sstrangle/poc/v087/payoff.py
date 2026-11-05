"""Independent expiry payoff arithmetic; native observations remain inputs."""
import json,re
from datetime import datetime
from collections import defaultdict
import pandas as pd

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
