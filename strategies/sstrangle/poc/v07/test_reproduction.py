import json
from optimize import OUT

def test_saved_full_baselines_reproduce_every_episode():
 records=json.loads((OUT/'baseline_recheck.json').read_text())
 assert set(records)=={'condor','strangle','put'}
 for r in records.values():
  assert r['max_episode_error']<1e-5 and r['residual_contracts']==0
  assert r['feature_decision_mismatches']==0 and r['feature_max_error']<1e-10
  assert abs(r['native_account_pnl']-r['net_pnl'])<.01

def test_frozen_rules_meet_declared_count_constraint():
 for r in json.loads((OUT/'frozen_rules.json').read_text()).values():
  assert r['trials']==864 and all(r['count_'+str(y)]>=400 for y in range(2022,2027))
  assert r['train_pnl']>0 and r['train_daily_cash_dd']>0

def test_reproduction_detects_fee_corruption_and_duplicate_events(tmp_path):
 import pandas as pd
 import pytest
 from recheck_baselines import reconstruct
 ep='202501090935';symbol={'id':'contract1','value':'SPXW  250109P03900000'}
 orders=[{'symbol':symbol,'type':0,'tag':f'oo05;e={ep};r=OPEN;', 'events':[{'id':1,'fillQuantity':-1,'fillPrice':2,'orderFeeAmount':1.18}]},{'symbol':symbol,'type':6,'tag':'expiry','events':[{'id':2,'fillQuantity':1,'fillPrice':0,'orderFeeAmount':0,'message':'Underlying: 3905'}]}]
 pd.DataFrame([{'episode':ep,'pnl':198.82}]).to_parquet(tmp_path/'episodes.parquet')
 (tmp_path/'backtest.json').write_text(json.dumps({'backtest':{'statistics':{'Start Equity':'100000','End Equity':'100198.82'}}}))
 (tmp_path/'orders.json').write_text(json.dumps(orders));_,r=reconstruct(tmp_path);assert abs(r['net_pnl']-198.82)<1e-8
 orders[0]['events'][0]['orderFeeAmount']=2.18;(tmp_path/'orders.json').write_text(json.dumps(orders))
 with pytest.raises(AssertionError):reconstruct(tmp_path)
 orders[0]['events'][0]['orderFeeAmount']=1.18;orders[1]['events'][0]['id']=1;(tmp_path/'orders.json').write_text(json.dumps(orders))
 with pytest.raises(AssertionError):reconstruct(tmp_path)
