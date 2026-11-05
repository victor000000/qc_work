import numpy as np
import pandas as pd
from research import features,select,mask_for

def fixture():
 days=pd.bdate_range('2022-05-16','2026-10-22'); rows=[]
 for i,d in enumerate(days):
  for slot in range(5):rows.append(dict(day=str(d.date()),year=d.year,pnl=float((i%17)-7)*10,gld_range_pct=(i%31)/1000,qqq_range_pct=(i%23)/1000))
 return pd.DataFrame(rows)

def test_future_outcomes_and_counts_cannot_change_selection():
 f=fixture();a,_=select(f);changed=f[f.year<=2024].copy()
 b,_=select(changed);assert a==b
 f.loc[f.year>=2025,'pnl']=1e12;f.loc[f.year>=2025,'gld_range_pct']=1e9
 c,_=select(f);assert a==c

def test_threshold_equality_missing_and_direction():
 f=pd.DataFrame({'gld_range_pct':[np.nan,.1,.2]})
 assert mask_for(f,dict(feature='gld_range_pct',threshold=.1,side='below')).tolist()==[False,True,False]
 assert mask_for(f,dict(feature='gld_range_pct',threshold=.1,side='above')).tolist()==[False,False,True]

def test_same_day_and_future_raw_bars_cannot_change_features(monkeypatch):
 import research
 f=pd.DataFrame([dict(day='2024-01-03',episode='202401030935')])
 a=features(f)
 changed=research.prices.copy();future=changed.date.astype(str)>='2024-01-03'
 changed.loc[future,'high']=1e12;changed.loc[future,'low']=0
 monkeypatch.setattr(research,'prices',changed)
 b=features(f)
 pd.testing.assert_frame_equal(a,b)
 assert (a.gld_range_pct_source_day<'2024-01-03').all()
