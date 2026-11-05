"""Build readable shared feature implementation and pinned local inputs."""
from pathlib import Path
import json,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];P=Path(__file__).parent;OUT=ROOT/'strategies/sstrangle/results/qc_sizing_poc_20261024'
s=(ROOT/'strategies/sstrangle/poc/v065/local_features.py').read_text();s=s[s.index('REG={}'):s.index('\ndef attach(')]
engine='import math,bisect\nfrom datetime import date,timedelta\nimport numpy as np\nimport pandas as pd\n'+s+'''
class FeatureBook:
 def __init__(self,raw,vix):
  prices=pd.DataFrame(raw,columns=['symbol','date','open','high','low','close','volume'])
  prices['date']=pd.to_datetime(prices.date).dt.date
  empty=pd.DataFrame(columns=['underlying','source','day','atm_iv'])
  panel=daily_pack(prices,empty)
  panel['source_day']=(panel.available_at.dt.tz_convert('America/New_York').dt.tz_localize(None)-pd.Timedelta(days=1)).dt.strftime('%Y-%m-%d')
  v=pd.DataFrame(vix,columns=['source_day','vix_close']).sort_values('source_day').set_index('source_day');c=v.vix_close
  v['vix_rank252']=(c-c.rolling(252).min())/(c.rolling(252).max()-c.rolling(252).min()).replace(0,np.nan)
  v['vix_rank60']=(c-c.rolling(60).min())/(c.rolling(60).max()-c.rolling(60).min()).replace(0,np.nan)
  v['vix_change1']=c.diff();v['vix_change5']=c.diff(5);v['vix_ratio20']=c/c.rolling(20).mean()
  self.panel=panel.merge(v,on='source_day',how='left').set_index('source_day').sort_index();self.days=list(self.panel.index)
 def value(self,day,feature):
  i=bisect.bisect_left(self.days,day)-1
  if i<0:return None,None
  source=self.days[i]
  if (date.fromisoformat(day)-date.fromisoformat(source)-timedelta(days=1)).days>=7:return None,source
  value=float(self.panel.iloc[i][feature])
  return (value if math.isfinite(value) else None),source

def feature_value(book,day,feature):return book.value(day,feature)
'''
(P/'feature_engine.py').write_text(engine)
prices=pd.read_parquet(OUT/'provider/us_prices_full/data.parquet').sort_values(['symbol','date']);raw=[[r.symbol,str(r.date),float(r.open),float(r.high),float(r.low),float(r.close),int(r.volume)] for r in prices.itertuples()]
v=pd.read_csv(OUT/'VIX_History.csv');v['day']=pd.to_datetime(v.DATE).dt.strftime('%Y-%m-%d');v=v[v.day.between('2021-01-01','2026-10-22')];vix=[[r.day,float(r.CLOSE)] for r in v.itertuples()]
(OUT/'raw_inputs.json').write_text(json.dumps(dict(prices=raw,vix=vix)))
from feature_engine import FeatureBook,REG
book=FeatureBook(raw,vix);book.panel.to_parquet(OUT/'daily_features.parquet')
reg={k:v for k,v in REG.items() if v['screen_eligible']}
for k in ['vix_close','vix_rank252','vix_rank60','vix_change1','vix_change5','vix_ratio20']:reg[k]=dict(source='Cboe VIX daily close',screen_eligible=True,availability='previous completed source session, next NY midnight assumption',family='implied_volatility_regime_proxy')
assert len(reg)==150
(OUT/'feature_registry.json').write_text(json.dumps(reg,indent=2));print('Prepared',len(reg),'eligible features;',len(raw),'ETF input rows;',len(vix),'VIX rows')
