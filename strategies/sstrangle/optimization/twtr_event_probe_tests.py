import ast
from datetime import datetime,date,timedelta
import hashlib,json
from pathlib import Path
import pytest
import twtr_event_report as r

HERE=Path(__file__).resolve().parent


def test_actual_held_identity_switches_only_at_real_execution_clocks():
    t=ast.parse((HERE/'twtr_event_probe.py').read_text());f=next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name=='held_put_for')
    ns={'datetime':datetime};exec(compile(ast.Module(body=[f],type_ignores=[]),'<actual_held_clock>','exec'),ns);p=ns['held_put_for']
    assert p(datetime(2022,9,21,11,59)) is None
    assert p(datetime(2022,9,21,12))=='put31'
    assert p(datetime(2022,10,6,11,59))=='put31'
    assert p(datetime(2022,10,6,12))=='put43'
    assert p(datetime(2022,10,21,11,59))=='put43'
    assert p(datetime(2022,10,21,12))=='put46'


def envelope():
    cal=json.loads((HERE.parent/'research/reference/lean_market_hours_20261018.json').read_text())['entries']['Equity-usa-[*]']
    days={str(date(2022,9,20)+timedelta(days=i)):dict(data_slices=390,underlying_bars=1,strict_pair_minutes=1,guarded_pair_minutes=1)
          for i in range(42) if r.shared.noon_open(date(2022,9,20)+timedelta(days=i),cal)}
    rt=dict(Equity='$60,000',Fees='$0',Holdings='$0',Unrealized='$0',twtr_event_no_trades='1',twtr_event_performance_claim='0',twtr_event_observed_days=str(len(days)),twtr_event_corporate_events='0',twtr_event_underlying_warning_seen='0',twtr_event_underlying_bars=str(len(days)),twtr_event_strict_pair_after_warning='0',twtr_event_guarded_pair_after_warning='0')
    rt.update({'twtr_event_phase_'+p+'_strict':'1' for p in ['put31','put43','put46']})
    lines=['TWTR_EVENT_DAY '+json.dumps(dict(day=d,**c)) for d,c in sorted(days.items())]
    lines+=['TWTR_EVENT_CHECKSUM '+hashlib.sha256(json.dumps(dict(events=[],daily=days),sort_keys=True).encode()).hexdigest()]
    return dict(statistics={'Total Orders':'0'},runtimeStatistics=rt),'\n'.join(lines)


def test_absent_warning_is_an_explicit_source_result_not_a_verified_exit():
    f,log=envelope();v=r.audit(f,[],[],log)
    assert v['native_source_probe_verified'] and not v['underlying_warning_seen']
    assert not v['strict_quote_opportunity_after_warning_observed']
    assert not v['real_exit_execution_verified'] and not v['strategy_calmar_proven']


def test_missing_underlying_or_phase_data_cannot_masquerade_as_absent_warning():
    f,log=envelope();f['runtimeStatistics']['twtr_event_underlying_bars']='0'
    with pytest.raises(ValueError,match='source coverage'):r.audit(f,[],[],log)
    f,log=envelope();f['runtimeStatistics']['twtr_event_phase_put46_strict']='0'
    with pytest.raises(ValueError,match='phases'):r.audit(f,[],[],log)


def test_trade_or_changed_source_fingerprint_is_rejected():
    f,log=envelope()
    with pytest.raises(ValueError,match='traded'):r.audit(f,[{'id':1}],[],log)
    with pytest.raises(ValueError,match='fingerprint'):r.audit(f,[],[],log.replace('TWTR_EVENT_CHECKSUM ','TWTR_EVENT_CHECKSUM a'))
