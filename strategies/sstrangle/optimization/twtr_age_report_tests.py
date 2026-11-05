"""Test strict source-control evidence; never fabricate a profitable candidate."""
from copy import deepcopy
import hashlib,json
from pathlib import Path
import pytest
import twtr_age_report as r

DRY=Path(__file__).resolve().parents[1]/'results/strangle_basket-twtr-age-regression_20261019_202703'


def reference():
    orders=[o for o in json.loads(r.GOLD.read_text()) if o['id'] in r.IDS]
    full=deepcopy(json.loads((r.GOLD.parent/'backtest.json').read_text())['backtest'])
    fees=sum(f['fee'] for f in r.shared.execution_rows(orders))
    full['statistics']['Total Orders']='6';full['runtimeStatistics']['Fees']=str(-fees)
    return orders,full


def test_actual_unclosed_source_can_validate_control_but_not_a_completed_strategy():
    orders,full=reference();v,filled=r.audit(orders,orders,full,False,orders)
    assert v['expected_cloud_failure_reproduced'] and v['all_six_control_fills_equal']
    assert v['realized_cycle_pnl'] is None and len(v['residual_quantities'])==2
    assert v['exact_account_equity']==pytest.approx(47796.095)
    assert not v['strategy_calmar_proven']


def test_failed_open_reference_cannot_be_presented_as_successful_age_candidate():
    orders,full=reference()
    with pytest.raises(ValueError,match='genuinely complete and flat'):r.audit(orders,orders,full,True,orders)


def test_control_completion_or_incomplete_native_export_is_rejected():
    orders,full=reference();full['error']=None;full['status']='Completed.'
    with pytest.raises(ValueError,match='mandatory-quote failure'):r.audit(orders,orders,full,False,orders)
    orders,full=reference()
    with pytest.raises(ValueError,match='Missing/rejected/extra'):r.audit(orders[:-1],orders[:-1],full,False,orders)


def test_actual_dry_render_binds_unchanged_original_risk_and_native_helpers():
    m=json.loads((DRY/'manifest.json').read_text());assert m['expected_control_cloud_failure'] is True
    assert m['source_orders_sha256']==hashlib.sha256(r.GOLD.read_bytes()).hexdigest()
    for key,cfg in m['variants'].items():
        row=dict(code=(DRY/(key+'.py')).read_text(),extra_files=(DRY/'extra_files.json').read_text())
        assert r.source_proof(DRY,key,cfg,row)['original_native_models_preserved']
        row['code']+='\n# differs from actual queue'
        with pytest.raises(ValueError,match='queued'):r.source_proof(DRY,key,cfg,row)
