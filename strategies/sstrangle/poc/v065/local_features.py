"""Point-in-time local feature packs and chronological fixed-tape alpha screening.
Historical daily publication uses next NY midnight as an explicit assumption;
current-vintage prices are not proof of a historically available vendor release.
"""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'strategies/sstrangle/results/qc_delta_poc_20261024'
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

def attach(entries,panel):
 f=pd.merge_asof(entries.sort_values('decision_at'),panel.sort_values('available_at'),left_on='decision_at',right_on='available_at',direction='backward',allow_exact_matches=False,tolerance=pd.Timedelta(days=7))
 assert (f.available_at.dropna()<f.loc[f.available_at.notna(),'decision_at']).all()
 return f

def make_features(folder,panel):
 f=pd.read_parquet(folder/'entry_features.parquet')
 for col in ['put_delta','call_delta','anchor_pd','anchor_cd']:f[col]=pd.to_numeric(f[col],errors='raise').astype(float)
 f=attach(f,panel)
 rt=json.loads((folder/'backtest.json').read_text())['backtest']['runtimeStatistics']
 f['put_error']=(f.put_delta+float(rt['put_target'])).abs();f['call_error']=(f.call_delta-float(rt['call_target'])).abs()
 f['short_delta_sum']=f[['put_delta','call_delta']].sum(axis=1,min_count=1);f['short_abs_delta_sum']=f[['put_delta','call_delta']].abs().sum(axis=1,min_count=1)
 f['put_anchor_shift']=f.put_delta-f.anchor_pd;f['call_anchor_shift']=f.call_delta-f.anchor_cd
 local=f.decision_at.dt.tz_convert('America/New_York')
 f['minutes_since_open']=local.dt.hour*60+local.dt.minute-570;f['weekday']=local.dt.dayofweek
 for k in ['put_delta','call_delta','decision_spot','recovered','anchor_pd','anchor_cd','put_error','call_error','short_delta_sum','short_abs_delta_sum','put_anchor_shift','call_anchor_shift','minutes_since_open','weekday']:
  REG[k]=dict(source='QC pre-order metadata',family='admission' if k not in ['minutes_since_open','weekday'] else 'calendar',screen_eligible=False,availability='decision timestamp, recorded before order; not external asof join')
 REG['short_delta_sum']['formula']='sum of existing short-option contract deltas; not signed position exposure'
 REG['short_abs_delta_sum']['formula']='sum of absolute deltas of existing short-option contracts'
 legs=pd.read_parquet(folder/'legs.parquet')
 for right,side in [('P','put'),('C','call')]:
  for sign,role in [(-1,'short'),(1,'long')]:
   strikes=legs[(legs.right==right)&(legs.quantity==sign)].set_index('episode').strike
   assert not strikes.index.duplicated().any()
   key=role+'_'+side+'_strike';f[key]=f.episode.map(strikes)
   REG[key]=dict(source='chosen native contract identity; strike fixed before submission',family='contract_geometry',screen_eligible=False,availability='decision timestamp')
   distance=role+'_'+side+'_distance_pct'
   f[distance]=(f[key]-f.decision_spot)/f.decision_spot
   REG[distance]=dict(source='chosen contract strike and pre-order decision_spot',family='contract_geometry',screen_eligible=False,availability='decision timestamp')
 return f

def screen(features,labels):
 d=features.merge(labels[['episode','pnl','day','year']],on='episode',validate='one_to_one');rows=[]
 train=d.year<=2023;valid=d.year==2024;test=d.year>=2025
 for name,meta in REG.items():
  if not meta['screen_eligible'] or name not in d:continue
  if d.loc[train,name].notna().mean()<.99:continue
  threshold=float(d.loc[train,name].median())
  for side in ['above','below']:
   mask=d[name]>threshold if side=='above' else d[name]<=threshold
   rec={'feature':name,'family':meta['family'],'side':side,'threshold':threshold}
   for split,m in [('train',train),('validation',valid),('later',test)]:
    sub=d[mask&m];daily=sub.groupby('day').pnl.sum()
    rec.update({split+'_trades':len(sub),split+'_pnl':float(sub.pnl.sum()),split+'_mean':float(sub.pnl.mean()),split+'_days':len(daily)})
   annual=d[mask].groupby('year').size().reindex(range(2022,2027),fill_value=0)
   rec['annual_min']=int(annual.min());rec['annual_pass']=bool(annual.ge(360).all())
   for year,n in annual.items():rec['count_'+str(year)]=int(n)
   # Candidate selection uses training performance/counts only; later annual gate is reported, never optimized.
   trainannual=d[mask&train].groupby('year').size().reindex([2022,2023],fill_value=0)
   rec['train_eligible']=bool(trainannual.ge(360).all())
   rows.append(rec)
 return pd.DataFrame(rows)

def main():
 dest=OUT/'local';dest.mkdir(exist_ok=True)
 prices=pd.read_parquet(OUT/'provider/us_prices/data.parquet');iv=pd.read_parquet(OUT/'provider/us_iv/data.parquet')
 panel=daily_pack(prices,iv);panel.to_parquet(dest/'daily_feature_pack.parquet',index=False)
 datasets={'v06_control':ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023/condor_full_v1_evidence'}
 datasets.update({k:ROOT/('strategies/sstrangle/results/qc_three_demo_poc_20261023/'+v+'_evidence') for k,v in [('strangle_v06','strangle_full_v2'),('put_v06','put_full_v3')]})
 for key in ['condor_full_t02','condor_full_t05']:
  folder=OUT/(key+'_evidence')
  if (folder/'audit.json').exists():datasets[key]=folder
 summary={}
 for key,folder in datasets.items():
  f=make_features(folder,panel);labels=pd.read_parquet(folder/'labels.parquet')
  ep=pd.read_parquet(folder/'episodes.parquet')
  f.to_parquet(dest/(key+'_features.parquet'),index=False);labels.to_parquet(dest/(key+'_labels.parquet'),index=False)
  results=screen(f,ep);results.to_csv(dest/(key+'_all_trials.csv'),index=False)
  eligible=results[results.train_eligible].sort_values(['train_mean','feature','side'],ascending=[False,True,True])
  selected=eligible.iloc[0].to_dict() if len(eligible) else None
  coverage=f[[x for x in REG if x in f]].notna().mean().rename('coverage').to_frame();coverage.to_csv(dest/(key+'_coverage.csv'))
  summary[key]=dict(episodes=len(f),feature_fields=len(coverage),eligible_features=sum(v['screen_eligible'] for v in REG.values()),screen_trials=len(results),rules_passing_all_year_count=int(results.annual_pass.sum()),selected_by_training_only=selected,minimum_field_coverage=float(coverage.coverage.min()))
 for name,meta in REG.items():
  unit='dimensionless'
  if name.endswith(('prev_open','prev_high','prev_low','prev_close')):unit='USD per ETF share'
  elif name.endswith('prev_volume'):unit='shares'
  elif name.endswith('dollar_volume_20'):unit='USD'
  elif name.endswith('amihud20'):unit='inverse USD'
  elif name.endswith('rsi14'):unit='0-100'
  elif name.endswith('_strike') or name=='decision_spot':unit='index points'
  elif name=='minutes_since_open':unit='minutes'
  elif name=='weekday':unit='Monday=0 through Friday=4'
  elif ('_rv_' in name and 'ratio' not in name) or name.endswith(('downside_rv20','iv30','iv_change5')):unit='annualized return volatility'
  elif name.endswith('vrp_proxy20'):unit='annualized return variance'
  meta['unit']=unit
  meta.update(dtype=str(f[name].dtype),scope='SPX episode with explicitly named cross-market inputs',max_provider_age_days=7,provider_release=json.loads((OUT/'provider/release.json').read_text())['release'],applicability='Call and long-wing fields are null when absent from strategy; never imputed as zero')
 (dest/'feature_registry.json').write_text(json.dumps(REG,indent=2))
 pd.DataFrame.from_dict(REG,orient='index').rename_axis('feature').to_csv(dest/'feature_inventory.csv')
 (dest/'summary.json').write_text(json.dumps(dict(datasets=summary,policy='Conditional fixed native tape; no refills or margin recomputation. 2022-2023 train / 2024 validation / 2025-2026 later evaluation; all periods previously inspected, not untouched OOS. No profitability claim. Broker IV fields excluded from alpha screening due unknown historical publication clock.',gaps=['SPX/VIX daily absent','SPY/QQQ minutes absent','option surface/skew/OI absent','current-session opening gap/VWAP/Hurst not implemented']),indent=2))
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
