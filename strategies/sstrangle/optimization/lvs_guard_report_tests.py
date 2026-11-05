import importlib.util,json
from copy import deepcopy
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('guard_report',HERE/'lvs_guard_report.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
ACTUAL=HERE.parent/'results/strangle_basket-lvs-regression_20261019_143611'

def actual(key='lvs_market_control'):
    folder=ACTUAL/('SSTRANGLE_20261019_143611_'+key)
    return json.loads((folder/'orders.json').read_text()),json.loads((folder/'backtest.json').read_text())['backtest']

def test_actual_original_control_cannot_claim_guarded_deferral():
    orders,full=actual();audit,_,_=r.audit_guard(orders,deepcopy(orders),full)
    assert not audit['native_execution_account_audit_passed']
    assert audit['native_single_cycle_pnl'] is None
    assert audit['guard_runtime_proof']['guard_first_deferred'] is None
    assert any('outside declared' in issue for issue in audit['issues'])

def test_runtime_claims_alone_cannot_hide_original_immediate_market_close():
    orders,full=actual();full=deepcopy(full)
    full['runtimeStatistics'].update(guard_first_deferred='1',guard_original_holdings_retained='1',guard_actual_closed='1',guard_actual_exit_reason='STOP')
    audit,_,_=r.audit_guard(orders,deepcopy(orders),full)
    assert not audit['native_execution_account_audit_passed'] and audit['native_single_cycle_pnl'] is None

def test_native_limit_fallback_trace_is_not_a_no_limit_guard_trace():
    orders,full=actual('lvs_limit_exit');audit,_,_=r.audit_guard(orders,deepcopy(orders),full)
    assert not audit['native_execution_account_audit_passed']
    assert audit['native_orders']==6 and audit['native_single_cycle_pnl'] is None
    assert any('four' in issue or 'two real' in issue for issue in audit['issues'])

def test_changed_native_export_is_rejected():
    orders,full=actual();rust=deepcopy(orders);rust[0]['tag']+=';test_difference=True'
    audit,_,_=r.audit_guard(orders,rust,full)
    assert any('Rust/Python' in issue for issue in audit['issues'])

def test_no_actual_orders_cannot_be_a_zero_pnl_success():
    _,full=actual();audit,_,_=r.audit_guard([],[],full)
    assert not audit['native_execution_account_audit_passed'] and audit['native_single_cycle_pnl'] is None

def actual_guard():
    folder=HERE.parent/'results/strangle_basket-lvs-guard_20261019_160702/SSTRANGLE_20261019_160702_lvs_guarded'
    return json.loads((folder/'orders.json').read_text()),json.loads((folder/'backtest.json').read_text())['backtest']

def test_genuine_guard_openings_match_gold_despite_zero_quantity_submission_events():
    orders,full=actual_guard()
    _,gold,_=r.native.native_records(r.native.gold_orders())
    assert gold[0]['quantity']==0 and len([e for e in gold if e['quantity']])==4
    audit,_,_=r.audit_guard(orders,deepcopy(orders),full)
    assert audit['native_execution_account_audit_passed'],audit['issues']
    assert audit['actual_fees']==4.9 and audit['native_single_cycle_pnl']==-160.9
    assert audit['residual_native_quantities']=={}

@pytest.mark.parametrize('field,value',[('fillPrice',.62),('fillQuantity',-1.),('time',1438099260.),('orderFeeAmount',1.4)])
def test_filtering_submission_events_still_rejects_changed_real_opening(field,value):
    orders,full=actual_guard();orders=deepcopy(orders)
    event=next(e for e in orders[0]['events'] if e.get('fillQuantity'))
    event[field]=value
    audit,_,_=r.audit_guard(orders,deepcopy(orders),full)
    assert not audit['native_execution_account_audit_passed']
    assert 'Original opening economics changed' in audit['issues']

def test_missing_genuine_fill_fee_is_not_inferred_from_account_total():
    orders,full=actual();orders=deepcopy(orders)
    event=next(e for e in orders[0]['events'] if e.get('fillQuantity'));event['orderFeeAmount']=None
    audit,_,_=r.audit_guard(orders,deepcopy(orders),full)
    assert audit['actual_cashflow'] is None and audit['native_single_cycle_pnl'] is None
    assert any('Missing actual fee' in issue for issue in audit['issues'])

def source_case(tmp_path):
    config=dict(engineering_smoke=True,limit_exit=False,voluntary_guard=True,stop_multiple=1.,risk_interval_minutes=15,time_exit_dte=28)
    source=(HERE/'lvs_guard_fixture.py').read_text().replace('CONFIG = {}','CONFIG = '+repr(config),1)
    (tmp_path/'guarded.py').write_text(source)
    extra=json.loads((HERE.parent/'results/strangle_basket_20261018_191012/extra_files.json').read_text())
    extra={key:extra[key] for key in ('rules.py','execution_base.py','basket_rules.py','terminal_margin.py','premium_units.py','premium_filter.py')}
    extra.update({'lvs_original_fixture.py':r.PARENT.read_text(),'unguarded_reference.py':r.REFERENCE.read_text(),'guarded_strategy.py':(HERE/'guarded_main.py').read_text(),'voluntary_quote_guard.py':(HERE/'voluntary_quote_guard.py').read_text(),'research_risk_rules.py':(HERE/'risk_rules.py').read_text()})
    (tmp_path/'extra_files.json').write_text(json.dumps(extra));row=dict(code=source,extra_files=json.dumps(extra))
    return config,row,extra

def test_actual_source_composition_preserves_parent_and_default_execution(tmp_path):
    cfg,row,_=source_case(tmp_path);proof=r.source_proof(tmp_path,'guarded',cfg,row)
    assert proof['queued_source_identical'] and proof['only_declared_research_methods_changed']

def test_queued_source_mismatch_rejected(tmp_path):
    cfg,row,_=source_case(tmp_path);row['code']+='\n#differentqueuedsource\n'
    with pytest.raises(ValueError,match='Actual queued'):r.source_proof(tmp_path,'guarded',cfg,row)

def test_original_parent_cannot_change(tmp_path):
    cfg,row,extra=source_case(tmp_path);extra['lvs_original_fixture.py']+='\n#changed\n';row['extra_files']=json.dumps(extra);(tmp_path/'extra_files.json').write_text(json.dumps(extra))
    with pytest.raises(ValueError,match='Original native'):r.source_proof(tmp_path,'guarded',cfg,row)

def test_execution_method_change_cannot_hide_inside_guard_helper(tmp_path):
    cfg,row,extra=source_case(tmp_path);old='    def execute(self, key, legs, reason, on_filled=None):'
    # Inject a distinct method body into the actual method's AST.
    source=extra['guarded_strategy.py'];lines=source.splitlines();i=next(i for i,v in enumerate(lines) if v.startswith('    def execute('));lines.insert(i+1,"        raise RuntimeError('changed execution')");extra['guarded_strategy.py']='\n'.join(lines)+'\n'
    row['extra_files']=json.dumps(extra);(tmp_path/'extra_files.json').write_text(json.dumps(extra))
    with pytest.raises(ValueError,match='outside declared scope'):r.source_proof(tmp_path,'guarded',cfg,row)
