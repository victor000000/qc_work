from pathlib import Path
import pandas as pd
import numpy as np
from local_features import daily_pack,attach,OUT,REG

def test_future_mutation_cannot_change_earlier_features():
 p=pd.read_parquet(OUT/'provider/us_prices/data.parquet');iv=pd.read_parquet(OUT/'provider/us_iv/data.parquet')
 cutoff=pd.Timestamp('2024-06-03',tz='UTC')
 entries=pd.DataFrame({'decision_at':[cutoff],'episode':['test']})
 a=attach(entries,daily_pack(p,iv))
 changed=p.copy();future=pd.to_datetime(changed.date)>=cutoff.tz_localize(None)
 changed.loc[future,['open','high','low','close','volume']]*=10
 b=attach(entries,daily_pack(changed,iv))
 pd.testing.assert_frame_equal(a,b)

def test_equal_timestamp_and_stale_data_are_not_admitted():
 t=pd.Timestamp('2024-06-03T04:00Z')
 panel=pd.DataFrame({'available_at':[t],'value':[123.]})
 entries=pd.DataFrame({'decision_at':[t,t+pd.Timedelta(seconds=1),t+pd.Timedelta(days=8)]})
 f=attach(entries,panel)
 assert pd.isna(f.value.iloc[0]) and f.value.iloc[1]==123 and pd.isna(f.value.iloc[2])

def test_daily_formulas_and_unknown_iv_clock_exclusion():
 dates=pd.date_range('2023-01-01',periods=80).date
 p=pd.DataFrame({'symbol':'SPY','date':dates,'open':100+np.arange(80),'high':102+np.arange(80),'low':99+np.arange(80),'close':101+np.arange(80),'volume':1000})
 # Provide all cross-market series for the same deliberately simple fixture.
 p=pd.concat([p.assign(symbol=s) for s in ['SPY','QQQ','IWM','TLT','GLD']],ignore_index=True)
 iv=pd.DataFrame(columns=['underlying','source','day','atm_iv'])
 f=daily_pack(p,iv)
 assert abs(f.spy_ret_5.iloc[-1]-(180/175-1))<1e-12
 assert abs(f.spy_range_pct.iloc[-1]-3/180)<1e-12
 assert not REG['spy_iv30']['screen_eligible']
 assert not any(x in REG for x in ['pnl','settlement_spot','expiry_cash_attribution','entry_credit'])

def test_later_labels_cannot_change_training_selection():
 from local_features import screen,ROOT,make_features
 prices=pd.read_parquet(OUT/'provider/us_prices/data.parquet');iv=pd.read_parquet(OUT/'provider/us_iv/data.parquet')
 folder=ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023/condor_full_v1_evidence'
 features=make_features(folder,daily_pack(prices,iv));ep=pd.read_parquet(folder/'episodes.parquet')
 a=screen(features,ep);changed=ep.copy();changed.loc[changed.year>=2024,'pnl']*= -100
 b=screen(features,changed)
 cols=['feature','side','threshold','train_mean','train_pnl','train_trades','train_eligible']
 pd.testing.assert_frame_equal(a[cols],b[cols])

def test_put_has_no_invented_call_or_long_wing_features():
 from local_features import ROOT,make_features
 p=pd.read_parquet(OUT/'provider/us_prices/data.parquet');iv=pd.read_parquet(OUT/'provider/us_iv/data.parquet')
 f=make_features(ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023/put_full_v3_evidence',daily_pack(p,iv))
 assert f.call_delta.isna().all() and f.short_call_strike.isna().all() and f.long_put_strike.isna().all()
 assert f.short_put_strike.notna().all()
 assert f.short_delta_sum.equals(f.put_delta)
 assert f.short_abs_delta_sum.equals(f.put_delta.abs())
