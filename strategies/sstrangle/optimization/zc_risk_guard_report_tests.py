"""Reporter unit checks use real preserved fills and a synthetic fixture envelope.

These tests never create a native research success artifact or simulate a new
profitable exit. Only a separately collected cloud execution can validate it.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pytest
import zc_risk_guard_report as zc

DRY = Path(__file__).resolve().parents[1] / 'results/strangle_basket-zc-risk-guard_20261019_184618'


def gold():
    return [o for o in json.loads(zc.GOLD.read_text()) if o['id'] in zc.GOLD_IDS]


def envelope():
    return dict(statistics={'Total Orders':'10'}, runtimeStatistics={
        'Equity':'$53,528.59', 'Fees':'-$24.70', 'Holdings':'$0', 'Unrealized':'$0',
        'fixture_cycle_net':'-3212.2', 'fixture_replayed_entry':'1',
        'fixture_synthetic_fills':'0', 'fixture_calmar_claim':'0',
        'fixture_open_completed':'1', 'fixture_guard_and_retry':'0'})


def test_genuine_reference_economics_reconcile_inside_unit_envelope():
    orders = gold(); r, fills = zc.audit(orders,orders,envelope(),False,orders)
    assert r['all_ten_control_fills_equal'] and r['native_orders']==10
    assert r['actual_fees']==pytest.approx(24.7)
    assert r['native_single_cycle_pnl']==pytest.approx(-3212.2)
    assert not r['strategy_calmar_proven']


def test_changed_control_closing_price_cannot_be_accepted_as_reference():
    orders = deepcopy(gold())
    for event in orders[-1]['events']:
        if event.get('fillQuantity'): event['fillPrice'] += .00125
    with pytest.raises(ValueError,match='ten genuine source fills'):
        zc.audit(orders,orders,envelope(),False,gold())


def test_missing_native_order_or_wrong_account_never_passes():
    orders = gold()
    with pytest.raises(ValueError,match='Incomplete'):
        zc.audit(orders[:-1],orders[:-1],envelope(),False,gold())
    full = envelope(); full['runtimeStatistics']['Equity']='$60,000'
    with pytest.raises(ValueError,match='terminal account mismatch'):
        zc.audit(orders,orders,full,False,gold())


def test_candidate_needs_actual_native_policy_exercise_not_just_a_flag():
    full = envelope(); full['runtimeStatistics']['fixture_guard_and_retry']='1'
    with pytest.raises(ValueError,match='not exercised'):
        zc.audit(gold(),gold(),full,True,gold())


def test_late_real_fill_cannot_hide_behind_simultaneous_submission_timestamps():
    orders=deepcopy(gold())
    for event in orders[-1]['events']:
        if event.get('fillQuantity'):event['time']+=301
    with pytest.raises(ValueError,match='closing fills exceeded five minutes'):
        zc.audit(orders,orders,envelope(),True,gold())


def test_dry_render_preserves_execution_dependencies_and_actual_method_chain():
    m = json.loads((DRY/'manifest.json').read_text())
    assert m['phase']=='basket-zc-risk-guard' and m['evidence_only']
    assert set(m['variants'])=={'zc_control','zc_guard_retry'}
    assert m['source_orders_sha256']==hashlib.sha256(zc.GOLD.read_bytes()).hexdigest()
    for key,cfg in m['variants'].items():
        code=(DRY/(key+'.py')).read_text();extras=(DRY/'extra_files.json').read_text()
        r=zc.source_proof(DRY,key,cfg,dict(code=code,extra_files=extras))
        assert r['preserved_control_identical']
        with pytest.raises(ValueError,match='differ'):
            zc.source_proof(DRY,key,cfg,dict(code=code+'\n# mismatched queue',extra_files=extras))
