from datetime import date
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('optimization_report',ROOT/'optimization/report.py')
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)


def base36(value):
    chars='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';result=''
    while value:
        value,remainder=divmod(value,36);result=chars[remainder]+result
    return result


def combo(group,key,reason,batch=1,count=1,quantity=1,day='2020-01-02',volume=100,budget=3000,reserve=2000):
    annotation=(f';batch_id={batch};basket_count={count};quantity={quantity};monthly_only=True;'
        f'ivr=80;samples=504;iv=.42;iv_low=.1;iv_high=.5;allocation_equity=60000;'
        f'allocation_budget={budget};estimated_initial_margin={reserve};estimated_entry_fees=1;volume={volume};'
        'allocation_mode=research_capped_collateral_budget;total_collateral_fraction=.2;'
        'per_symbol_collateral_fraction=.05;put_delta=-.19;call_delta=.19')
    rows=[];put=int('2Z43H5BGXLVAE',36)
    for side in (0,1):
        rows.append(dict(id=group*2+side,time=day+'T17:00:00Z',quantity=(-quantity if reason=='OPEN' else quantity),status=3,
            tag=key+':'+reason+(annotation if reason=='OPEN' else ''),
            symbol={'id':'HD '+base36(put if side==0 else put-10**19)},
            groupOrderManager={'id':group},events=[dict(fillQuantity=(-quantity if reason=='OPEN' else quantity))]))
    return rows


CFG=dict(total_collateral_fraction=.2,per_symbol_collateral_fraction=.05,lookback=504)


def test_capped_budget_is_not_equity_divided_by_basket():
    rows=combo(1,'A','OPEN')+combo(2,'A','TIME',day='2020-01-03')
    entries,batches,peak=report.audit_budget_annotations(rows,CFG)
    assert len(entries)==1 and peak==1 and batches[0]['reserve']==2001
    wrong=combo(1,'A','OPEN',budget=60000)+combo(2,'A','TIME',day='2020-01-03')
    with pytest.raises(ValueError,match='collateral budget'):
        report.audit_budget_annotations(wrong,CFG)


def test_actual_margin_and_fees_must_fit_research_cap():
    rows=combo(1,'A','OPEN',reserve=3000)+combo(2,'A','TIME',day='2020-01-03')
    with pytest.raises(ValueError,match='exceed opening collateral'):
        report.audit_budget_annotations(rows,CFG)


def test_no_new_batch_on_exit_day_and_no_partial_fill_acceptance():
    rows=combo(1,'A','OPEN')+combo(2,'A','TIME',day='2020-01-03')
    with pytest.raises(ValueError,match='most recent exit'):
        report.audit_budget_annotations(rows+combo(3,'B','OPEN',batch=2,day='2020-01-03'),CFG)
    rows[-1]['quantity']=2
    with pytest.raises(ValueError,match='partial'):
        report.audit_budget_annotations(rows,CFG)


def test_cagr_uses_funded_window_and_conservative_drawdown():
    daily={date(2012,1,1):100,date(2014,1,1):120,date(2020,1,1):110,date(2026,1,1):200}
    result=report.account_metrics(daily,100,date(2012,1,1),date(2026,1,1),.30)
    assert result['cagr']==pytest.approx(2**(365.25/(date(2026,1,1)-date(2012,1,1)).days)-1)
    assert result['daily_mdd']==pytest.approx(1-110/120)
    assert result['calmar']==pytest.approx(result['cagr']/.30)
    insolvent=report.account_metrics({date(2020,1,1):-42},60000,date(2012,1,1),date(2026,1,1),1)
    assert insolvent['cagr'] is None and insolvent['calmar'] is None and not insolvent['positive_equity']


def test_qc_ohlc_chart_uses_close_instead_of_open():
    response=dict(chart=dict(series=dict(Equity=dict(values=[[1577980800,100,150,80,125]]))))
    assert list(report.daily_marks(response).values())==[125]


def test_training_selection_frozen_and_cannot_be_replaced(tmp_path):
    plan=dict(training_end='2019-12-31',history_start='2012-01-03',initial_cash=100,prior_inspection='disclosed')
    daily={date(2012,1,3):100,date(2018,1,1):90,date(2019,12,31):150,date(2020,1,1):1}
    cycles=[dict(exit='2018-01-02T17:00:00Z') for _ in range(40)]
    result=report.freeze_training(tmp_path,[('a',{},daily,cycles)],plan)
    assert result['chosen_variant']=='a' and (tmp_path/'training_selection.json').exists()
    daily[date(2019,12,31)]=160
    with pytest.raises(ValueError,match='Previously frozen'):
        report.freeze_training(tmp_path,[('a',{},daily,cycles)],plan)


def test_monitor_updates_same_campaign_and_preserves_observation_history(tmp_path, monkeypatch):
    campaign=tmp_path/'campaign';campaign.mkdir()
    state=tmp_path/'CURRENT.json';monkeypatch.setattr(report,'PROGRESS_FILE',state)
    state.write_text(json.dumps(dict(campaign=str(campaign),baseline_unchanged=True)))
    first=dict(utc='2026-10-19T04:50:00Z',jobs=[dict(name='existing',status='In Progress...',progress=.15)],collection_issues=[])
    identities=[dict(name='existing',project_id=31338456,backtest_id='retained-id',status='running')]
    report.record_monitor(campaign,first,identities)
    second=dict(first,utc='2026-10-19T04:51:00Z',collection_issues=[dict(error='TimeoutError',retry_read_only=True)])
    report.record_monitor(campaign,second,identities)
    saved=json.loads(state.read_text())
    assert saved['latest_cloud_snapshot']==second and saved['jobs']==identities
    assert saved['baseline_unchanged'] and not saved['goal_achieved']
    assert 'not proof of cloud failure' in saved['status']
    assert [json.loads(line) for line in (campaign/'cloud_progress_history.jsonl').read_text().splitlines()]==[first,second]


def test_monitor_cannot_overwrite_another_campaign_state(tmp_path, monkeypatch):
    state=tmp_path/'CURRENT.json';monkeypatch.setattr(report,'PROGRESS_FILE',state)
    original=json.dumps(dict(campaign='/another/campaign',goal_achieved=False));state.write_text(original)
    report.record_monitor(tmp_path,dict(utc='now',jobs=[],collection_issues=[]),[])
    assert state.read_text()==original
    assert (tmp_path/'cloud_progress.json').exists()


def test_logs_use_real200line_pages_and_do_not_claim_full_cloud_coverage(tmp_path):
    calls=[];pages={0:[f'line{i}' for i in range(200)],200:[f'line{i}' for i in range(200,400)],400:['tail']}
    def api(user,token,path,parameters):
        calls.append(parameters.copy())
        return dict(logs=pages[parameters['start']])
    ids=dict(projectId=31338456,backtestId='existing')
    receipt=report.collect_logs('u','t',tmp_path,ids,api=api)
    assert [row['start'] for row in calls]==[0,200,400]
    assert all(row['end']-row['start']==200 for row in calls)
    assert len((tmp_path/'cloud.log').read_text().splitlines())==401
    assert receipt['api_pagination_exhausted'] and receipt['full_cloud_log_coverage']=='unknown'
    assert len(receipt['pages'])==3
    report.collect_logs('u','t',tmp_path,ids,api=lambda *args:pytest.fail('Valid terminal pages should be reusable'))


def test_log_network_failure_preserves_partial_pages_and_resumes_same_identity(tmp_path):
    ids=dict(projectId=1,backtestId='same');calls=[]
    def api(user,token,path,parameters):
        calls.append(parameters['start'])
        if parameters['start']==200:raise TimeoutError('network observation timeout')
        return dict(log=[f'line{i}' for i in range(200)])
    with pytest.raises(TimeoutError):report.collect_logs('u','t',tmp_path,ids,api=api)
    receipt=json.loads((tmp_path/'log_collection_receipt.json').read_text())
    assert not receipt['cloud_failure_inferred'] and receipt['lines']==200
    assert not (tmp_path/'cloud.log').exists() and len(list(tmp_path.glob('cloud.partial_*.log')))==1
    resumed=[]
    def finish(user,token,path,parameters):
        resumed.append(parameters['start']);return dict(log=['tail'])
    report.collect_logs('u','t',tmp_path,ids,api=finish)
    assert resumed==[200] and len((tmp_path/'log_collection_attempts.jsonl').read_text().splitlines())==2
    with pytest.raises(ValueError,match='identity'):
        report.collect_logs('u','t',tmp_path,dict(projectId=1,backtestId='different'),api=finish)


def test_repeated_pages_and_missing_logs_are_preserved_and_rejected(tmp_path):
    ids=dict(projectId=1,backtestId='same')
    with pytest.raises(ValueError,match='Repeated log page'):
        report.collect_logs('u','t',tmp_path,ids,api=lambda *args:dict(logs=[f'line{i}' for i in range(200)]))
    assert len(list((tmp_path/'log_pages').glob('page_*.json')))==2
    other=tmp_path/'missing';other.mkdir()
    with pytest.raises(ValueError,match='omitted log'):
        report.collect_logs('u','t',other,ids,api=lambda *args:dict(success=True))
    assert json.loads((other/'log_collection_receipt.json').read_text())['status']=='collection_error'


def test_failed_cloud_run_still_collects_account_charts_when_logs_fail(tmp_path,monkeypatch):
    name='failed';folder=tmp_path/name;folder.mkdir()
    (folder/'orders.json').write_text('[]');(folder/'orders.rust.json').write_text('[]')
    ids=dict(project_id=1,backtest_id='actual-failure')
    response=dict(backtest=dict(projectId=1,backtestId='actual-failure',completed=True,status='Runtime Error',error='real cloud failure'))
    def failed_request(*args):raise TimeoutError('log network timeout')
    charts=[]
    def read_chart(user,token,parameters):
        charts.append(parameters['name']);return dict(chart=dict(series={}))
    monkeypatch.setattr(report,'request',failed_request);monkeypatch.setattr(report,'read_chart',read_chart)
    monkeypatch.setattr(report,'chart_window',lambda full:{})
    report.collect_terminal('u','t',tmp_path,name,ids,response)
    assert charts==['Trading period','Strategy Equity']
    assert (folder/'trading_period.json').exists() and (folder/'strategy_equity.json').exists()
    receipt=json.loads((folder/'collection_receipt.json').read_text())
    assert receipt['cloud_status']=='failed' and receipt['issues'][0]['cloud_failure_inferred'] is False
    assert json.loads((folder/'backtest.json').read_text())['backtest']['error']=='real cloud failure'


def test_explicit_qc_log_cap_warning_does_not_become_complete_coverage(tmp_path):
    message='You currently have a maximum of 100kb of log data per backtest.'
    receipt=report.collect_logs('u','t',tmp_path,dict(projectId=1,backtestId='same'),
        api=lambda *args:dict(logs=['2014-01-01 ENTRY',message]))
    assert receipt['api_pagination_exhausted']
    assert receipt['source_log_limit_warning'] and receipt['full_cloud_log_coverage']=='limited_by_qc_log_cap_warning'


def test_proven_cloud_failure_is_separate_from_network_collection_failure(tmp_path,monkeypatch):
    campaign=tmp_path/'campaign';campaign.mkdir()
    current=tmp_path/'CURRENT.json';current.write_text(json.dumps(dict(campaign=str(campaign),feasibility_v2_verified=False)))
    monkeypatch.setattr(report,'PROGRESS_FILE',current)
    snapshot=dict(utc='2026-10-19T06:00:00Z',jobs=[dict(name='failed',status='Runtime Error')],
        cloud_failures=[dict(name='failed',error='Actual broker execution error')],
        collection_issues=[dict(name='failed',error='Temporary log timeout')])
    report.record_monitor(campaign,snapshot,[])
    state=json.loads(current.read_text())
    assert 'cloud failure confirmed' in state['status']
    assert 'not proof of cloud failure' not in state['status']
    assert 'separate read-only' in state['status'] and state['feasibility_v2_verified'] is False


def test_training_excludes_incomplete_or_cloud_failed_attempts(tmp_path):
    plan=dict(training_end='2019-12-31',history_start='2012-01-03',initial_cash=100,prior_inspection='disclosed')
    daily={date(2012,1,3):100,date(2018,1,1):90,date(2019,12,31):150}
    cycles=[dict(exit='2018-01-02T17:00:00Z') for _ in range(40)]
    failure=dict(variant='cloud-failed',error='actual failure',qualified=False)
    frozen=report.freeze_training(tmp_path,[('incomplete',dict(period_complete=False),daily,cycles)],plan,excluded=[failure])
    assert frozen['chosen_variant'] is None
    assert not frozen['training'][0]['eligible'] and frozen['excluded_attempts']==[failure]


def test_failed_attempt_preserves_open_native_positions_without_fake_fullperiod_stats(tmp_path,monkeypatch):
    (tmp_path/'orders.json').write_text('[]');(tmp_path/'orders.rust.json').write_text('[]')
    (tmp_path/'collection_receipt.json').write_text(json.dumps(dict(issues=[])))
    fills=[dict(symbol_id='real-native-short',quantity=-2,qc_price=3,multiplier=100,fee=2)]
    monkeypatch.setattr(report,'execution_rows',lambda orders:fills)
    row=dict(name='failed',project_id=1,backtest_id='failed-id')
    full=dict(statistics={'Total Orders':'0'},runtimeStatistics={'Equity':'$59,000'},error='unfilled exit')
    actual=report.failed_attempt_evidence(tmp_path,row,full,dict(queued_code_and_helpers_identical=True))
    assert actual['residual_native_quantities']=={'real-native-short':-2}
    assert actual['executed_cashflow_less_fees']==598
    assert actual['cashflow_is_not_realized_profit_when_positions_remain']
    assert not actual['target_flag'] and not actual['qualified_for_selection'] and not actual['full_period_performance_published']


def test_clean_insolvency_before_evaluation_finalizes_without_post_bankruptcy_marks(tmp_path):
    plan=dict(history_start='2012-01-03',training_end='2019-12-31',evaluation_start='2020-01-01',end='2026-09-30',
        initial_cash=60000,minimum_closed_cycles=100,minimum_evaluation_cycles=20,prior_inspection='disclosed')
    daily={date(2014,1,2):60000,date(2017,6,1):50000,date(2018,3,1):-42.29};original=dict(daily)
    cycles=[dict(exit='2017-01-02T17:00:00Z') for _ in range(120)]
    account=report.account_metrics(daily,60000,date(2012,1,3),date(2026,9,30),1.01)
    summary=dict(period_complete=False,outcome='insolvent',cycles=120,account=account)
    frozen=report.freeze_training(tmp_path,[('insolvent',summary,daily,cycles)],plan)
    result=report.evaluation_result('insolvent',summary,daily,cycles,frozen,plan)
    assert frozen['chosen_variant'] is None and not frozen['training'][0]['eligible']
    assert result['summary']['outcome']=='insolvent' and not result['target_flag']
    assert not result['evaluation']['available'] and result['evaluation']['observations']==0
    assert result['evaluation']['ending_equity'] is None and result['evaluation']['calmar'] is None
    assert 'No account-equity observations' in result['evaluation']['unavailable_reason']
    assert account['ending_equity']==-42.29 and account['cagr'] is None and daily==original
    json.dumps(result,allow_nan=False)


def test_positive_incomplete_path_before_evaluation_is_explicitly_unavailable():
    daily={date(2014,1,2):60000,date(2018,1,1):65000}
    result=report.account_metrics(daily,60000,date(2020,1,1),date(2026,9,30),.2)
    assert result['observations']==0 and not result['available'] and not result['window_end_observed']
    assert result['opening_equity']==65000 and result['ending_equity'] is None
    assert result['cagr'] is None and result['calmar'] is None


def test_missing_requested_last_session_cannot_qualify_via_positive_summary():
    daily={date(2012,1,3):60000,date(2019,12,31):70000,date(2020,1,2):65000,date(2026,9,29):180000}
    account=report.account_metrics(daily,60000,date(2012,1,3),date(2026,9,30),.2)
    assert account['observed_end']=='2026-09-29' and account['expected_end_session']=='2026-09-30'
    assert not account['window_end_observed'] and not account['available']
    assert account['cagr'] is None and account['calmar'] is None
    assert 'before the requested final account session' in account['unavailable_reason']
    # Even an optimistic stale summary cannot override independently missing marks.
    stale=dict(period_complete=True,cycles=120,account=dict(account,calmar=9.))
    plan=dict(initial_cash=60000,evaluation_start='2020-01-01',end='2026-09-30',minimum_closed_cycles=100,minimum_evaluation_cycles=20)
    cycles=[dict(exit='2024-01-02T17:00:00Z') for _ in range(120)]
    result=report.evaluation_result('stale',stale,daily,cycles,dict(chosen_variant='stale'),plan)
    assert not result['target_flag'] and result['evaluation']['calmar'] is None


def test_uncertain_ohlc_order_cannot_pass_evaluation_calmar_gate():
    daily={date(2019,12,31):100,date(2020,1,2):100,date(2026,9,30):150}
    account=dict(reported_mdd=.02,observed_account_chart_mdd_lower_bound=.02,
        observed_account_chart_mdd_upper_bound=.25,window_end_observed=True,
        positive_equity=True,calmar=3.)
    summary=dict(period_complete=True,cycles=120,account=account)
    plan=dict(initial_cash=60,evaluation_start='2020-01-01',end='2026-09-30',
        minimum_closed_cycles=100,minimum_evaluation_cycles=20)
    cycles=[dict(exit='2024-01-02T17:00:00Z') for _ in range(120)]
    result=report.evaluation_result('candidate',summary,daily,cycles,
        dict(chosen_variant='candidate'),plan)
    assert result['evaluation']['available']
    assert result['evaluation']['denominator_mdd']==.25
    assert result['evaluation']['cagr']/.02>2
    assert result['evaluation']['calmar']<2 and not result['target_flag']


def test_requested_weekend_uses_actual_saved_calendar_final_session():
    expected=report.expected_account_end_session(date(2026,10,3))
    assert expected==date(2026,10,2)
    metrics=report.account_metrics({date(2026,1,2):100,date(2026,10,2):110},100,date(2026,1,1),date(2026,10,3),.1)
    assert metrics['window_end_observed'] and metrics['available'] and metrics['cagr'] is not None


def terminal_cache_fixture(tmp_path,completed=True,failed=True,hash_receipt=True):
    import hashlib
    campaign=tmp_path/'campaign';campaign.mkdir()
    name='existing';folder=campaign/name;folder.mkdir()
    row=dict(project_id=31338456,backtest_id='same-execution')
    response=dict(success=True,backtest=dict(projectId=31338456,backtestId='same-execution',completed=completed,
        status='Runtime Error' if failed else 'Completed' if completed else 'In Progress...',error='confirmed cloud error' if failed else None))
    report.atomic_json(folder/'backtest.json',response)
    receipt=dict(identity=dict(projectId=31338456,backtestId='same-execution'),cloud_status=report.terminal_status(response['backtest']))
    if hash_receipt:receipt['backtest_sha256']=hashlib.sha256((folder/'backtest.json').read_bytes()).hexdigest()
    report.atomic_json(folder/'collection_receipt.json',receipt)
    return campaign,name,row,response


def test_verified_terminal_failed_cache_reuses_full_response_without_any_api(tmp_path,monkeypatch):
    campaign,name,row,response=terminal_cache_fixture(tmp_path)
    monkeypatch.setattr(report,'read_existing_backtest',lambda *args:pytest.fail('Known pinned terminal failure must not hit API'))
    actual=report.read_research_backtest('u','t',campaign,name,row)
    assert actual==response and actual['backtest']['error']=='confirmed cloud error'


def test_nonterminal_and_legacy_unhashed_response_require_real_observation(tmp_path,monkeypatch):
    first=tmp_path/'nonterminal';first.mkdir()
    campaign,name,row,response=terminal_cache_fixture(first,completed=False,failed=True)
    calls=[]
    def api(*args):calls.append(args);return response
    monkeypatch.setattr(report,'read_existing_backtest',api)
    assert report.read_research_backtest('u','t',campaign,name,row)==response and len(calls)==1
    second=tmp_path/'legacy';second.mkdir()
    campaign,name,row,response=terminal_cache_fixture(second,hash_receipt=False)
    assert report.read_research_backtest('u','t',campaign,name,row)==response and len(calls)==2
    (campaign/name/'backtest.json').unlink()
    assert report.read_research_backtest('u','t',campaign,name,row)==response and len(calls)==3


def test_legacy_cache_is_pinned_after_one_real_full_response_and_collection(tmp_path,monkeypatch):
    import hashlib
    campaign,name,row,response=terminal_cache_fixture(tmp_path,hash_receipt=False)
    calls=[]
    def api(*args):calls.append(args);return response
    monkeypatch.setattr(report,'read_existing_backtest',api)
    monkeypatch.setattr(report,'request',lambda *args:dict(logs=[]))
    monkeypatch.setattr(report,'chart_window',lambda full:{})
    monkeypatch.setattr(report,'read_chart',lambda *args:dict(chart=dict(series={})))
    folder=campaign/name;(folder/'orders.json').write_text('[]');(folder/'orders.rust.json').write_text('[]')
    actual=report.read_research_backtest('u','t',campaign,name,row)
    report.collect_terminal('u','t',campaign,name,row,actual)
    receipt=json.loads((folder/'collection_receipt.json').read_text())
    assert receipt['backtest_sha256']==hashlib.sha256((folder/'backtest.json').read_bytes()).hexdigest()
    assert receipt['cloud_status']=='failed'
    assert report.read_research_backtest('u','t',campaign,name,row)==response and len(calls)==1


@pytest.mark.parametrize('corruption',['cached_identity','receipt_identity','hash','status','api_error'])
def test_terminal_cache_integrity_conflict_fails_without_api_or_overwriting(tmp_path,monkeypatch,corruption):
    campaign,name,row,response=terminal_cache_fixture(tmp_path)
    folder=campaign/name;receipt=json.loads((folder/'collection_receipt.json').read_text())
    if corruption=='cached_identity':
        response['backtest']['backtestId']='different-execution';report.atomic_json(folder/'backtest.json',response)
    elif corruption=='receipt_identity':receipt['identity']['projectId']=999
    elif corruption=='hash':receipt['backtest_sha256']='0'*64
    elif corruption=='status':receipt['cloud_status']='done'
    elif corruption=='api_error':
        response['success']=False;response['errors']=['unusable API response'];report.atomic_json(folder/'backtest.json',response)
    report.atomic_json(folder/'collection_receipt.json',receipt)
    before={path.name:path.read_bytes() for path in folder.iterdir()}
    monkeypatch.setattr(report,'read_existing_backtest',lambda *args:pytest.fail('Integrity conflict must fail before API'))
    with pytest.raises(ValueError):report.read_research_backtest('u','t',campaign,name,row)
    assert {path.name:path.read_bytes() for path in folder.iterdir()}==before
