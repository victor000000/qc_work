import copy,json
from pathlib import Path
import pytest
from collect import audit_orders
FOLDER=Path(__file__).resolve().parents[2]/'results/qc_poc_20261026_v085/put_spread_smoke_evidence'
def load():return json.loads((FOLDER/'orders.json').read_text()),json.loads((FOLDER/'backtest.json').read_text())['backtest']['runtimeStatistics']
def test_real_put_spread_cash_and_geometry():
 orders,rt=load();f,legs,events,annual,audit=audit_orders(orders,'',rt,False)
 assert len(legs)==2*len(f) and set(legs.right)=={'P'}
 assert abs(audit['attribution_error'])<1e-5 and audit['residual_positions']==0
 assert (f.pnl>-2002.37).all() and (f.entry_credit<2000).all()
@pytest.mark.parametrize('damage',['missing_leg','duplicate_event','wrong_fill','missing_settlement','future_decision'])
def test_corrupt_spread_evidence_is_rejected(damage):
 orders,rt=load();first=next(o for o in orders if ';r=OPEN;' in o.get('tag',''));fill=next(e for e in first['events'] if e.get('fillQuantity'))
 if damage=='missing_leg':orders.remove(first)
 elif damage=='duplicate_event':first['events'].append(copy.deepcopy(fill))
 elif damage=='wrong_fill':fill['fillPrice']+=.1
 elif damage=='future_decision':fill['time']-=60
 else:
  for o in orders:
   if o['type']==6:
    for e in o.get('events',[]):e['message']=''
 with pytest.raises(ValueError):audit_orders(orders,'',rt,False)
