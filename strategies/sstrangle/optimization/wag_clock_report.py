"""Read-only exact WBA control/clock observer report; no strategy or gate changes."""
import argparse
import ast
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent;STRATEGY=HERE.parent;ROOT=STRATEGY.parents[1]
sys.path[:0]=[str(STRATEGY),str(ROOT/'scripts')]
import qc_storage as storage
from qc_api_check import credentials
from resume_basket import terminal_status,validate_identity,atomic_json
from basket_report import events
from qc_contracts import execution_rows


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded);return loaded


shared=module('_wag_clock_shared',HERE/'report.py')
wag=module('_wag_clock_native',HERE/'wag_exit_report.py')
PARENT_CAMPAIGN=STRATEGY/'results/strangle_basket-wag-regression_20261019_142652'
BASELINE=STRATEGY/'results/strangle_basket_20261018_191012'
PARENT_ID='871156fba7043ac4ea179dc019564eb4'
NAMES=('observations','cache_end_stale_gt5m','cache_end_future','slice_present',
    'slice_fresh_nonff','slice_fresh_ff','cache_slice_equal_endpoint','cache_prior_open_session_or_older',
    'cache_period_minute','slice_period_minute','security_exchange_open','security_local_equals_algorithm_ny')
CLOCK_KEYS=tuple('clock_'+side+'_'+name for side in ('put','call') for name in NAMES)


def frozen_source(campaign,manifest,row):
    path=campaign/'wag_clock.py';source=path.read_text()
    if row['code']!=source:raise ValueError('Queued thin clock fixture differs from frozen main')
    config=manifest['variants']['wag_clock']
    if config!={'engineering_smoke':True,'buyback':False}:raise ValueError('Clock observer must preserve strict-control CONFIG')
    tree=ast.parse(source)
    configs=[ast.literal_eval(node.value) for node in ast.walk(tree) if isinstance(node,ast.Assign) and
        any(isinstance(target,ast.Name) and target.id=='CONFIG' for target in node.targets)]
    if configs!=[config]:raise ValueError('Thin observer literal CONFIG differs from frozen manifest')
    classes=[node for node in tree.body if isinstance(node,ast.ClassDef)]
    if len(classes)!=1 or [ast.unparse(base) for base in classes[0].bases]!=['WAGExitRegression']:
        raise ValueError('Thin observer does not inherit the unchanged original fixture')
    methods={node.name for node in classes[0].body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
    if methods!={'initialize','on_data','diagnose'}:raise ValueError('Thin observer overrides methods beyond its read-only clock hooks')
    extras=json.loads((campaign/'extra_files.json').read_text())
    queued=json.loads(row['extra_files']) if isinstance(row.get('extra_files'),str) else row.get('extra_files') or {}
    if extras!=queued:raise ValueError('Queued clock helpers differ from frozen helper bundle')
    baseline=json.loads((BASELINE/'extra_files.json').read_text())
    for name in ('rules.py','execution_base.py','basket_rules.py','terminal_margin.py','premium_units.py','premium_filter.py'):
        if extras.get(name)!=baseline[name]:raise ValueError('Clock observer changed immutable baseline helper '+name)
    if extras.get('basket_strategy.py')!=(BASELINE/'basket.py').read_text():raise ValueError('Clock observer changed immutable baseline strategy dependency')
    if extras.get('wag_original_fixture.py')!=(PARENT_CAMPAIGN/'wag_control.py').read_text():raise ValueError('Clock observer parent is not the exact prior native control')
    if 'wag_quote_clock_diagnostics.py' not in extras:raise ValueError('Frozen clock observation helper missing')
    return dict(main_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        extras_sha256=hashlib.sha256((campaign/'extra_files.json').read_bytes()).hexdigest(),
        parent_fixture_sha256=hashlib.sha256(extras['wag_original_fixture.py'].encode()).hexdigest(),
        diagnostic_helper_sha256=hashlib.sha256(extras['wag_quote_clock_diagnostics.py'].encode()).hexdigest(),
        rust_content_hash=row['code_hash'],queued_source_identical=True,exact_original_native_control_parent=True,
        immutable_baseline_execution_helpers=True,brokerage_and_default_models_inherited_from_exact_parent=True)


def counter_evidence(runtime):
    """Absent exported counters stay unknown; never recover them from logs."""
    rows=[];missing=[];issues=[];counts={}
    extra=sorted(key for key in runtime if key.startswith('clock_') and key not in CLOCK_KEYS)
    if extra:issues.append('Unexpected clock runtime fields outside the frozen24-counter contract: '+str(extra))
    for key in CLOCK_KEYS:
        raw=runtime.get(key)
        if key not in runtime:
            missing.append(key);rows.append(dict(field=key,reported=False,raw_value=None,count=None));continue
        try:
            parsed=Decimal(str(raw))
            if not parsed.is_finite() or parsed<0 or parsed!=parsed.to_integral_value():raise ValueError('Not a nonnegative integer')
            value=int(parsed)
        except (InvalidOperation,ValueError,TypeError):
            issues.append('Invalid actual runtime counter '+key);rows.append(dict(field=key,reported=True,raw_value=str(raw),count=None));continue
        counts[key]=value;rows.append(dict(field=key,reported=True,raw_value=str(raw),count=value))
    for side in ('put','call'):
        prefix='clock_'+side+'_'
        if any(prefix+name not in counts for name in NAMES):continue
        c={name:counts[prefix+name] for name in NAMES};n=c['observations']
        if n<=0:issues.append(side+': no actual bounded clock observations')
        if any(value>n for name,value in c.items() if name!='observations'):issues.append(side+': boolean count exceeds actual observations')
        if c['cache_end_stale_gt5m']+c['cache_end_future']>n:issues.append(side+': stale/future cache predicates cannot overlap')
        if c['slice_fresh_nonff']+c['slice_fresh_ff']>c['slice_present']:issues.append(side+': fresh Slice predicates exceed actual Slice presence')
        if c['slice_period_minute']>c['slice_present'] or c['cache_slice_equal_endpoint']>c['slice_present']:
            issues.append(side+': Slice-based count exceeds actual Slice presence')
    return dict(rows=rows,counts=counts,missing_runtime_counters=missing,issues=issues,
        exact24_actual_runtime_fields=len(counts)==24 and not extra,complete_valid=not missing and not issues,
        missing_values_inferred=False)


def classify_clocks(evidence,native_ledger_verified):
    if not native_ledger_verified:
        return dict(classification_available=False,reason='Original native economic/control/account ledger did not verify',sides={},root_cause_proven=False)
    if not evidence['complete_valid']:
        return dict(classification_available=False,reason='Required actual runtime counters missing or invalid; no inferred clock diagnosis',sides={},root_cause_proven=False)
    sides={}
    for side in ('put','call'):
        c={name:evidence['counts']['clock_'+side+'_'+name] for name in NAMES};n=c['observations']
        lower={}
        labels=[]
        for cache in ('stale','future'):
            issue=c['cache_end_stale_gt5m' if cache=='stale' else 'cache_end_future']
            for source,name in [('fresh_real','slice_fresh_nonff'),('fresh_ff','slice_fresh_ff')]:
                minimum=max(0,issue+c[name]-n)
                lower[cache+'_cache_and_'+source+'_slice_minimum']=minimum
                if minimum:labels.append('Observed '+cache+' cached endpoint with '+source+' Slice in at least '+str(minimum)+' common observations')
        if not labels:
            labels.append('Marginal counters reported; simultaneous stale/future cache and fresh Slice not established by available aggregate intersections')
        if c['slice_present']==0:labels.append('No current Slice QuoteBar observed')
        if c['slice_fresh_nonff']==0:labels.append('No fresh non-fill-forward current Slice QuoteBar observed')
        if c['security_local_equals_algorithm_ny']<n:labels.append('Actual security local clock differed from algorithm NY in some observations; direction is not exported')
        sides[side]=dict(actual_counts=c,observed_predicates=labels,joint_observation_lower_bounds=lower,
            exact_joint_counts_available=False,counts_are_not_price_or_timestamp_rows=True)
    return dict(classification_available=True,reason=None,sides=sides,root_cause_proven=False,
        interpretation='Observed clock/cache/Slice predicates only; aggregate intersections are conservative lower bounds, not invented exact joint counts.',
        no_quote_gate_relaxation=True)


def audit_clock(orders,rust,full,fixture_logs):
    native=wag.audit_fixture(orders,rust,full,'wag_control',wag.original_first_four(),fixture_logs)
    verified=full.get('completed') is True and native['actual_control_failure_reproduced'] and not native['issues'] and native['native_cashflow_account_reconciles']
    evidence=counter_evidence(full.get('runtimeStatistics',{}))
    classification=classify_clocks(evidence,verified)
    return dict(engineering_only=True,strategy_performance_claim=False,original_native_control_verified=verified,
        diagnostic_case_verified=bool(verified and classification['classification_available']),
        expected_cloud_failure_is_not_strategy_success=True,native_audit=native,
        actual_runtime_counters=evidence,observed_clock_classification=classification,
        root_cause_proven=False,quote_gate_changed=False,
        limitations=['One unchanged native WBA control plus aggregate read-only observer; no Calmar or broad strategy result.',
            'Missing runtime counters are unknown and never filled from logs or earlier jobs.',
            'A fresh fill-forward Slice does not satisfy the unchanged strict non-fill-forward quote gate.',
            'Observational cache/clock classifications do not independently establish vendor, mapping or engine root cause.'])


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('campaign',type=Path)
    args=parser.parse_args();campaign=args.campaign.resolve();manifest=json.loads((campaign/'manifest.json').read_text())
    if manifest.get('phase')!='basket-wag-clock' or list(manifest.get('variants',{}))!=['wag_clock'] or len(manifest.get('jobs',[]))!=1:
        raise ValueError('Require exactly one frozen native WBA clock control')
    if manifest.get('parent_control')!={'project_id':31338456,'backtest_id':PARENT_ID}:raise ValueError('Wrong original parent control identity')
    if manifest.get('source_failure')!={'project_id':31338456,'backtest_id':wag.SOURCE_BACKTEST}:raise ValueError('Wrong original source-failure identity')
    lock=(campaign/'wag_clock_report.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:print('Another native clock collector owns this campaign');return
    name=manifest['jobs'][0]
    if not name.endswith('_wag_clock'):raise ValueError('Manifest job name differs from single clock variant')
    with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as connection:
        connection.row_factory=storage.Row;saved=connection.execute('SELECT * FROM backtest_queue WHERE name=?',(name,)).fetchone()
    if saved is None:
        print(json.dumps(dict(name=name,status='not_queued_dry_run',submitted=False)));return
    row=dict(saved);source=frozen_source(campaign,manifest,row)
    if not row.get('backtest_id'):
        print(json.dumps(dict(name=name,status=row['status'],completed=False)));return
    user,token=credentials(ROOT/'data/S001.duckdb')
    response=shared.read_research_backtest(user,token,campaign,name,row);full=response['backtest'];validate_identity(full,row)
    snapshot=dict(utc=datetime.now(timezone.utc).isoformat(),name=name,project_id=row['project_id'],backtest_id=row['backtest_id'],
        status=full.get('status'),completed=full.get('completed'),progress=full.get('progress'),error=full.get('error'))
    atomic_json(campaign/'wag_clock_cloud_progress.json',snapshot)
    print(json.dumps(snapshot),flush=True)
    if terminal_status(full) is None:return
    folder=shared.collect_terminal(user,token,campaign,name,row,response)
    orders=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text());rust=rust['orders'] if isinstance(rust,dict) else rust
    log=(folder/'cloud.log').read_text() if (folder/'cloud.log').exists() else ''
    diagnostics=events(log,'WAG_EXIT_FIXTURE')
    # Preserve available actual order/counter evidence even if native audit rejects.
    counters=counter_evidence(full.get('runtimeStatistics',{}));out=campaign/'wag_clock_report'
    shared.write_tables(out,dict(executions=execution_rows(orders),clock_runtime_fields=counters['rows'],
        raw_native_orders=[dict(order_id=order['id'],payload=json.dumps(order)) for order in orders]))
    try:summary=audit_clock(orders,rust,full,diagnostics)
    except Exception as exc:
        atomic_json(out/'audit_error.json',dict(error=type(exc).__name__+': '+str(exc),original_evidence_preserved=True,
            quote_gate_changed=False,root_cause_proven=False));raise
    summary.update(project_id=row['project_id'],backtest_id=row['backtest_id'],frozen_source=source,
        log_collection=json.loads((folder/'log_collection_receipt.json').read_text()))
    atomic_json(out/'summary.json',summary)
    checksums={str(path.relative_to(campaign)):hashlib.sha256(path.read_bytes()).hexdigest() for path in campaign.rglob('*')
        if path.is_file() and path.name not in ('evidence_checksums.json','wag_clock_report.lock')}
    atomic_json(out/'evidence_checksums.json',checksums)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
