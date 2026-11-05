from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import pytest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('wag_clock_report',HERE/'wag_clock_report.py')
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)


def runtime_counts(observations=61):
    values={key:'0' for key in report.CLOCK_KEYS}
    for side in ('put','call'):
        base='clock_'+side+'_'
        for key in ('observations','cache_end_stale_gt5m','slice_present','slice_fresh_ff','cache_period_minute',
                    'slice_period_minute','security_local_equals_algorithm_ny','cache_prior_open_session_or_older'):
            values[base+key]=str(observations)
        values[base+'security_exchange_open']=str(max(0,observations-1))
    return values


def original_control():
    folder=report.PARENT_CAMPAIGN/'SSTRANGLE_20261019_142652_wag_control'
    orders=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text())
    rust=rust['orders'] if isinstance(rust,dict) else rust
    full=json.loads((folder/'backtest.json').read_text())['backtest']
    log=(folder/'cloud.log').read_text() if (folder/'cloud.log').exists() else ''
    return orders,rust,full,report.events(log,'WAG_EXIT_FIXTURE')


def test_exact24_actual_runtime_counters_classify_stale_cache_fresh_ff_without_gate_relaxation():
    evidence=report.counter_evidence(runtime_counts())
    assert evidence['complete_valid'] and len(evidence['counts'])==24
    result=report.classify_clocks(evidence,True)
    assert result['classification_available'] and not result['root_cause_proven']
    for side in ('put','call'):
        row=result['sides'][side]
        assert row['joint_observation_lower_bounds']['stale_cache_and_fresh_ff_slice_minimum']==61
        assert row['joint_observation_lower_bounds']['stale_cache_and_fresh_real_slice_minimum']==0
        assert not row['exact_joint_counts_available']
    assert result['no_quote_gate_relaxation']


def test_missing_clock_runtime_counter_is_unknown_not_inferred_from_other_fields():
    values=runtime_counts();values.pop('clock_put_cache_end_future')
    # A similarly named old predicate or log-equivalent field does not fill it.
    values['put_stale_or_future']='61'
    evidence=report.counter_evidence(values)
    assert evidence['missing_runtime_counters']==['clock_put_cache_end_future']
    missing=next(row for row in evidence['rows'] if row['field']=='clock_put_cache_end_future')
    assert missing['count'] is None and not missing['reported']
    assert not report.classify_clocks(evidence,True)['classification_available']
    assert not evidence['missing_values_inferred']


def test_marginal_nonzero_counters_cannot_establish_simultaneous_discrepancy():
    values=runtime_counts(10)
    for side in ('put','call'):
        values['clock_'+side+'_cache_end_stale_gt5m']='3'
        values['clock_'+side+'_slice_fresh_ff']='0'
        values['clock_'+side+'_slice_fresh_nonff']='3'
    result=report.classify_clocks(report.counter_evidence(values),True)
    assert result['classification_available']
    assert result['sides']['put']['joint_observation_lower_bounds']['stale_cache_and_fresh_real_slice_minimum']==0
    assert any('not established' in label for label in result['sides']['put']['observed_predicates'])


@pytest.mark.parametrize('key,value',[('clock_put_observations','0'),('clock_put_slice_fresh_nonff','62'),
    ('clock_put_cache_end_future','1'),('clock_put_slice_present','1'),('clock_put_slice_fresh_ff','-1'),
    ('clock_put_cache_period_minute','0.5'),('clock_put_cache_period_minute','NaN')])
def test_counter_invariants_fail_without_fabricating_observations(key,value):
    values=runtime_counts();values[key]=value
    evidence=report.counter_evidence(values)
    assert not evidence['complete_valid']
    assert not report.classify_clocks(evidence,True)['classification_available']


def test_actual_parent_native_failure_remains_verified_but_missing_clock_fields_do_not_prove_cause():
    orders,rust,full,logs=original_control()
    result=report.audit_clock(orders,rust,full,logs)
    assert result['original_native_control_verified']
    assert result['native_audit']['native_cashflow_account_reconciles']
    assert result['native_audit']['aggregate_holding_valuation']['derived_signed_holdings']==-139
    assert len(result['actual_runtime_counters']['missing_runtime_counters'])==24
    assert not result['diagnostic_case_verified'] and not result['root_cause_proven']


def test_complete_clock_fields_still_require_same_genuine_native_control_ledger():
    orders,rust,full,logs=original_control();full=deepcopy(full)
    full['runtimeStatistics'].update(runtime_counts())
    observed=report.audit_clock(orders,rust,full,logs)
    assert observed['diagnostic_case_verified'] and not observed['root_cause_proven']
    corrupted=deepcopy(orders);corrupted[0]['events'][-1]['fillPrice']=.91
    result=report.audit_clock(corrupted,deepcopy(corrupted),full,fixture_logs=[])
    assert not result['original_native_control_verified'] and not result['diagnostic_case_verified']


def test_joint_future_cache_and_real_slice_requires_complete_reported_evidence():
    values=runtime_counts(10)
    for side in ('put','call'):
        values['clock_'+side+'_cache_end_stale_gt5m']='0'
        values['clock_'+side+'_cache_end_future']='10'
        values['clock_'+side+'_slice_fresh_ff']='0'
        values['clock_'+side+'_slice_fresh_nonff']='10'
    result=report.classify_clocks(report.counter_evidence(values),True)
    assert result['sides']['put']['joint_observation_lower_bounds']['future_cache_and_fresh_real_slice_minimum']==10
    assert not result['root_cause_proven']


def test_real_thin_clock_source_validates_inherited_brokerage_without_requiring_setup_in_main():
    campaign=report.STRATEGY/'results/strangle_basket-wag-clock_20261019_144650'
    manifest=json.loads((campaign/'manifest.json').read_text())
    source=(campaign/'wag_clock.py').read_text();extras=json.loads((campaign/'extra_files.json').read_text())
    assert 'set_brokerage_model' not in source
    row=dict(code=source,extra_files=json.dumps(extras),code_hash='mock-queue-content-hash')
    receipt=report.frozen_source(campaign,manifest,row)
    assert receipt['exact_original_native_control_parent']
    assert receipt['brokerage_and_default_models_inherited_from_exact_parent']


def test_parent_or_baseline_helper_mutation_is_rejected_even_if_queue_and_main_match(tmp_path):
    campaign=report.STRATEGY/'results/strangle_basket-wag-clock_20261019_144650'
    manifest=json.loads((campaign/'manifest.json').read_text());source=(campaign/'wag_clock.py').read_text()
    original=json.loads((campaign/'extra_files.json').read_text());(tmp_path/'wag_clock.py').write_text(source)
    for filename in ('wag_original_fixture.py','execution_base.py'):
        extras=dict(original);extras[filename]+='\n# altered dependency\n'
        (tmp_path/'extra_files.json').write_text(json.dumps(extras))
        row=dict(code=source,extra_files=json.dumps(extras),code_hash='mock-queue-content-hash')
        with pytest.raises(ValueError,match='(exact prior native control|immutable baseline helper)'):
            report.frozen_source(tmp_path,manifest,row)
