import math,bisect
from datetime import date,timedelta
import numpy as np
import pandas as pd
REG={}
def daily_pack(prices,iv):
 frames=[]
 for symbol,g in prices.groupby('symbol'):
  g=g.sort_values('date').reset_index(drop=True);c=g.close;r=c.pct_change(fill_method=None);v=g.volume.astype(float)
  f=pd.DataFrame({'available_at':(pd.to_datetime(g.date)+pd.Timedelta(days=1)).dt.tz_localize('America/New_York').dt.tz_convert('UTC')})
  def add(name,value,formula,family='alpha',eligible=True):
   key=symbol.lower()+'_'+name;f[key]=value
   REG[key]=dict(source='us_prices' if not name.startswith(('iv','vrp')) else 'us_iv:ibkr_tws30d',symbol=symbol,formula=formula,family=family,screen_eligible=eligible,availability='completed daily observation + next New York midnight; assumed publication',basis='raw prices; no adjusted future corporate-action factors')
  for x in ['open','high','low','close','volume']:add('prev_'+x,g[x],'prior completed daily '+x,'datafield',False)
  for w in [1,2,5,10,20,60]:add('ret_'+str(w),c.pct_change(w,fill_method=None),f'C[t]/C[t-{w}]-1','momentum')
  for w in [5,10,20,60]:add('trend_'+str(w),c/c.rolling(w,min_periods=w).mean()-1,f'C/SMA({w})-1','trend')
  for w in [5,10,20,60]:add('rv_'+str(w),r.rolling(w,min_periods=w).std(ddof=1)*np.sqrt(252),f'std(simple returns,{w},ddof=1)*sqrt(252)','volatility')
  add('rv_ratio_5_20',r.rolling(5).std()/r.rolling(20).std(),'RV5/RV20','volatility')
  add('range_pct',(g.high-g.low)/c,'(H-L)/C','range')
  add('close_location',(c-g.low)/(g.high-g.low).replace(0,np.nan),'(C-L)/(H-L)','range')
  add('gap',g.open/c.shift(1)-1,'O[t]/C[t-1]-1; prior session gap, not current opening gap','gap')
  add('body',c/g.open-1,'C/O-1','range')
  add('volume_ratio_20',v/v.rolling(20).mean(),'V/SMA(V,20)','volume')
  add('dollar_volume_20',(c*v).rolling(20).mean(),'SMA(C*V,20)','liquidity')
  add('volume_z20',(v-v.rolling(20).mean())/v.rolling(20).std(),'zscore(V,20)','volume')
  add('amihud20',(r.abs()/(c*v).replace(0,np.nan)).rolling(20).mean(),'SMA(abs(return)/(C*V),20)','liquidity')
  add('drawdown60',c/c.rolling(60).max()-1,'C/rolling_max(C,60)-1','trend')
  add('return_skew20',r.rolling(20).skew(),'sample skew(simple return,20)','tail')
  add('downside_rv20',r.clip(upper=0).pow(2).rolling(20).mean().pow(.5)*np.sqrt(252),'sqrt(mean(min(r,0)^2,20)*252)','tail')
  delta=c.diff();up=delta.clip(lower=0).rolling(14).mean();down=(-delta.clip(upper=0)).rolling(14).mean()
  add('rsi14',100*up/(up+down).replace(0,np.nan),'100*mean(up,14)/(mean(up,14)+mean(down,14)); simple rolling','momentum')
  tr=pd.concat([g.high-g.low,(g.high-c.shift()).abs(),(g.low-c.shift()).abs()],axis=1).max(axis=1)
  add('atr14_pct',tr.rolling(14).mean()/c,'mean(true range,14)/C','range')
  sub=iv[(iv.underlying==symbol)&(iv.source=='ibkr_tws30d')].set_index('day').atm_iv
  assert not sub.index.duplicated().any()
  implied=g.date.map(sub)
  add('iv30',implied,'broker underlying 30-day IV, not option-derived 0DTE IV','iv_unverified',False)
  add('iv_change5',implied-implied.shift(5),'IV[t]-IV[t-5]','iv_unverified',False)
  add('iv_rank60',(implied-implied.rolling(60).min())/(implied.rolling(60).max()-implied.rolling(60).min()).replace(0,np.nan),'(IV-min60)/(max60-min60)','iv_unverified',False)
  add('vrp_proxy20',implied**2-(r.rolling(20).std()*np.sqrt(252))**2,'broker IV30 squared minus RV20 squared; NOT audio exact VRP','iv_unverified',False)
  frames.append(f.set_index('available_at'))
 panel=pd.concat(frames,axis=1).sort_index().copy().reset_index()
 for left,right in [('qqq','spy'),('iwm','spy'),('tlt','spy'),('gld','spy')]:
  key=f'{left}_minus_{right}_ret20';panel[key]=panel[left+'_ret_20']-panel[right+'_ret_20']
  REG[key]=dict(source='us_prices',formula=f'{left} 20-session return minus {right} 20-session return',family='cross_market',screen_eligible=True,availability='prior completed session, next NY midnight')
 return panel.replace([np.inf,-np.inf],np.nan)

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
