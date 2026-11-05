"""Genuine native fixtures: audit the two new structures and reject corruption."""
import copy,json
from pathlib import Path
import pytest
from collect_three import audit_orders
ROOT=Path(__file__).resolve().parents[2]/'results/qc_three_demo_poc_20261023'

def load(kind):
 p=ROOT/(kind+'_smoke_v1_evidence')
 return json.loads((p/'orders.json').read_text()),json.loads((p/'backtest.json').read_text())['backtest']['runtimeStatistics']

@pytest.mark.parametrize('kind,n,pnl',[('strangle',2,-6748.62),('put',1,11955.44)])
def test_native_structures_count_and_cash(kind,n,pnl):
 orders,rt=load(kind)
 episodes,legs,events,annual,audit=audit_orders(orders,'',rt,True,[2024,2025])
 assert len(episodes)==117 and len(legs)==117*n
 assert abs(audit['native_net_pnl']-pnl)<1e-8
 assert abs(audit['attribution_error'])<1e-7 and audit['residual_positions']==0
 assert annual.trades.tolist()==[117,0] and not audit['annual_pass']
 assert audit['midpoint_package_fill_audit']

@pytest.mark.parametrize('kind',['strangle','put'])
@pytest.mark.parametrize('damage',['wrong_kind','wrong_leg_count','wrong_slip','duplicate_event','future_decision','wrong_fee','missing_settlement'])
def test_corruption_rejected(kind,damage):
 orders,rt=load(kind);orders=copy.deepcopy(orders);rt=dict(rt)
 first=next(o for o in orders if ';r=OPEN;' in o.get('tag',''))
 fill=next(e for e in first['events'] if e.get('fillQuantity'))
 if damage=='wrong_kind':rt['strategy_kind']='condor'
 elif damage=='wrong_leg_count':rt['leg_count']='4'
 elif damage=='wrong_slip':fill['message']=fill['message'].replace('oo_slip=','bad_slip=')
 elif damage=='duplicate_event':first['events'].append(copy.deepcopy(fill))
 elif damage=='future_decision':fill['time']-=60
 elif damage=='wrong_fee':fill['orderFeeAmount']+=10
 elif damage=='missing_settlement':
  for o in orders:
   if o['type']==6:
    for e in o.get('events',[]):e['message']=''
 with pytest.raises(ValueError):audit_orders(orders,'',rt,False)


def test_european_adapter_rejects_premature_assignment_marker():
 orders,rt=load('strangle');orders=copy.deepcopy(orders);rt=dict(rt)
 rt['assignment_policy']='european_no_discretionary_early_assignment_native_expiry'
 exercise=next(o for o in orders if o['type']==6)
 exercise['events'][0]['message']+=' Simulated option assignment before expiration'
 with pytest.raises(ValueError,match='premature European'):
  audit_orders(orders,'',rt,False)


def test_april_stress_native_expiry_reconciles_without_early_assignment():
 p=ROOT/'strangle_expiry_smoke_v2_evidence'
 orders=json.loads((p/'orders.json').read_text());rt=json.loads((p/'backtest.json').read_text())['backtest']['runtimeStatistics']
 *_,audit=audit_orders(orders,'',rt,False)
 assert audit['episodes']==33 and audit['residual_positions']==0
 assert abs(audit['native_net_pnl']+256799.88)<1e-7
 assert not any('before expiration' in (e.get('message') or '').lower() for o in orders for e in o.get('events',[]))


def test_half_day_excludes_close_boundary_and_settles():
 p=ROOT/'put_calendar_smoke_v2_evidence'
 orders=json.loads((p/'orders.json').read_text());rt=json.loads((p/'backtest.json').read_text())['backtest']['runtimeStatistics']
 f,*_,audit=audit_orders(orders,'',rt,False)
 assert audit['episodes']==20 and int(rt['skip_session_closed'])==1
 half=f[f.day=='2022-11-25']
 assert len(half)==7 and max(half.decision_at).endswith('12:30:00')


def test_recovered_condor_keeps_exact_width_and_native_rejections():
 p=ROOT/'condor_smoke_v1_evidence'
 orders=json.loads((p/'orders.json').read_text());rt=json.loads((p/'backtest.json').read_text())['backtest']['runtimeStatistics']
 episodes,legs,events,annual,audit=audit_orders(orders,'',rt,False)
 assert len(episodes)==102 and len(legs)==408 and len(events)==574
 assert audit['rejected_episodes']==8
 assert int(rt['original_wing_skips'])==42 and int(rt['recovered_pair_candidates'])==35
 assert int(rt['recovered_filled_episodes'])==31
 assert abs(audit['native_net_pnl']+9521.44)<1e-7


def test_missing_optional_runtime_fields_are_not_imputed_as_zero():
 orders,rt=load('strangle');rt=dict(rt)
 for key in ['episodes_2024','ledger_error','max_flat_ledger_error']:rt.pop(key)
 f,legs,events,annual,audit=audit_orders(orders,'',rt,True,[2024])
 assert len(f)==117 and annual.trades.tolist()==[117]
 assert audit['runtime_max_flat_ledger_error'] is None
 assert set(audit['omitted_runtime_counters'])=={'episodes_2024','ledger_error','max_flat_ledger_error'}
 assert not audit['annual_pass'] and abs(audit['attribution_error'])<1e-7
