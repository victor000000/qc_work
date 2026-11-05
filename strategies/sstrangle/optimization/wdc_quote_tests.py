import ast
from collections import Counter
from datetime import date,datetime,timedelta
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS
import pytest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('_wdc_report_test',HERE/'wdc_quote_report.py')
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)
TREE=ast.parse((HERE/'wdc_quote_fixture.py').read_text())


def test_native_contract_replay_literals_match_all_six_authentic_failed_trial_fills():
    env=dict(date=date)
    for node in TREE.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('CONTRACTS','GOLD','DUE','FIELDS') for t in node.targets):
            exec(compile(ast.Module(body=[node],type_ignores=[]),'<fixture-literals>','exec'),env)
    _,events,issues=report.native.native_records(report.gold_orders());assert not issues
    fills=[e for e in events if e['quantity']];assert len(fills)==6
    codes={(put,strike):'WDC '+encoded+'|WDC R735QTJ8XC9X' for put,strike,encoded in env['CONTRACTS']}
    for (day,put,strike,q,price),fill in zip(env['GOLD'],fills):
        assert (codes[put,strike],q,price)==(fill['native_sid'],fill['quantity'],fill['price'])
        assert report.shared.ny_time(fill['utc']).replace(tzinfo=None)==datetime.combine(day,datetime.min.time()).replace(hour=12)
        assert fill['fee']==1. and fill['multiplier']==100
    assert env['DUE']==date(2019,4,22) and tuple(env['FIELDS'])==report.FIELDS


def observation(*,age=0,bid=.5,ff=False,slice_ff=False):
    node=next(n for n in ast.walk(TREE) if isinstance(n,ast.FunctionDef) and n.name=='observe')
    env=dict(timedelta=timedelta,QuoteBar=object)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<native-observer>','exec'),env)
    now=datetime(2019,4,22,12)
    bar=NS(is_fill_forward=ff,end_time=now-timedelta(minutes=age),ask=NS(close=.6))
    class Cache:
        def __getitem__(self,t):return lambda:bar
    sec=NS(cache=NS(get_data=Cache()),local_time=now,bid_price=bid,ask_price=.6,
           exchange=NS(exchange_open=True),holdings=NS(quantity=-1))
    sliced=NS(is_fill_forward=slice_ff,end_time=now)
    owner=NS(positions={'WDC':{'put':'P'}},key='WDC',securities={'P':sec},time=now,
             quote_counts={'put':Counter()},good_quote=lambda s:not ff and age<=5 and bid>0)
    env['observe'](owner,'put',NS(quote_bars={'P':sliced}))
    return owner.quote_counts['put']


def test_zero_bid_fresh_positive_ask_separates_strict_and_buyback_predicates():
    c=observation(bid=0)
    assert c['zero_bid']==c['buyback_pass']==c['cache_fresh_real']==1
    assert c['strict_pass']==0


def test_prior_session_cache_and_current_fill_forward_slice_do_not_become_fresh_quotes():
    c=observation(age=24*60,slice_ff=True)
    assert c['cache_stale']==c['slice_fill_forward']==1
    assert c['cache_fresh_real']==c['slice_fresh_real']==c['buyback_pass']==c['strict_pass']==0


@pytest.mark.parametrize('age,expected',[(5,1),(6,0),(-1,0)])
def test_buyback_freshness_boundary_and_future_bar_rejection(age,expected):
    assert observation(age=age)['buyback_pass']==expected


def test_real_current_two_sided_slice_is_distinguished_from_fill_forward():
    c=observation();assert c['cache_fresh_real']==c['slice_fresh_real']==c['strict_pass']==c['buyback_pass']==1


def test_authentic_original_six_fills_without_new_diagnostic_evidence_cannot_qualify():
    rows=report.gold_orders();full=json.loads((report.SOURCE/'backtest.json').read_text())['backtest']
    result,_,_=report.audit(rows,rows,full)
    assert not result['engineering_diagnostic_verified'] and result['full_strategy_calmar'] is None
    assert any('aggregate' in x for x in result['issues'])


def test_changed_genuine_opening_is_not_tolerated_by_diagnostic():
    rows=report.gold_orders();rows[0]['events'][-1]['fillPrice']+=.01
    full=json.loads((report.SOURCE/'backtest.json').read_text())['backtest']
    result,_,_=report.audit(rows,rows,full)
    assert 'Original six native economic fills differ' in result['issues']


def history_runtime(due=0):
    rt={'wdch_unchanged':'1'}
    for side in ('put','call'):
        rt['wdch_'+side+'_prior']=json.dumps([240,240,240,0,0,240,240,240])
        rt['wdch_'+side+'_due']=json.dumps([due,due,due,0,0,due,due,due])
    return dict(runtimeStatistics=rt)


def test_history_empty_day_is_not_confused_with_stream_cache_failure():
    result=report.audit_history(dict(engineering_diagnostic_verified=True,issues=[]),history_runtime())
    assert result['engineering_diagnostic_verified']
    assert 'history empty' in result['retrospective_history_diagnosis']


def test_nonempty_retrospective_history_identifies_stream_path_instead():
    result=report.audit_history(dict(engineering_diagnostic_verified=True,issues=[]),history_runtime(240))
    assert 'stream/cache' in result['retrospective_history_diagnosis']


@pytest.mark.parametrize('field',[3,4])
def test_fill_forward_or_future_history_is_rejected(field):
    full=history_runtime(240);v=json.loads(full['runtimeStatistics']['wdch_put_due']);v[field]=1
    full['runtimeStatistics']['wdch_put_due']=json.dumps(v)
    result=report.audit_history(dict(engineering_diagnostic_verified=True,issues=[]),full)
    assert not result['engineering_diagnostic_verified']


def test_history_counts_cannot_certify_failed_original_order_audit():
    result=report.audit_history(dict(engineering_diagnostic_verified=False,issues=['native mismatch']),history_runtime())
    assert not result['engineering_diagnostic_verified'] and result['retrospective_history_diagnosis']=='inconclusive'


def actual_diagnostic():
    folder=HERE.parent/'results/strangle_basket-wdc-quote_20261019_162136/SSTRANGLE_20261019_162136_wdc_quote'
    return json.loads((folder/'orders.json').read_text()),json.loads((folder/'backtest.json').read_text())['backtest']


def test_completed_native_missing_exit_reproduction_has_complete_economic_and_counter_evidence():
    orders,full=actual_diagnostic();r,_,_=report.audit(orders,orders,full)
    assert r['engineering_diagnostic_verified'],r['issues']
    assert r['original_missing_exit_reproduced'] and len(r['residual_native_quantities'])==2
    assert r['fees']==6 and r['actual_cashflow']==284
    for side in ('put','call'):
        c=r['quote_predicate_counts'][side]
        assert c['observations']==c['cache_stale']==c['slice_fill_forward']==241
        assert c['cache_fresh_real']==c['slice_fresh_real']==0


def test_missing_actual_runtime_quote_counter_cannot_pass_reproduction_audit():
    orders,full=actual_diagnostic();del full['runtimeStatistics']['wdc_call']
    r,_,_=report.audit(orders,orders,full);assert not r['engineering_diagnostic_verified']


def test_nonfinite_account_is_not_an_economic_reconciliation():
    orders,full=actual_diagnostic();full['runtimeStatistics']['wdc_cash']='nan'
    r,_,_=report.audit(orders,orders,full);assert not r['engineering_diagnostic_verified']
