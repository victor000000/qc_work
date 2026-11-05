"""0.9.0 acceptance cases run against implementation 0.9.0.

Failures are review evidence, not xfailed/waived checks. Original review evidence is preserved separately.
"""
import copy
import hashlib
import json
import math
from datetime import timedelta
from types import SimpleNamespace
import pytest
from strategies.sstrangle.poc.v090.axis import Axis, stamp
from strategies.sstrangle.poc.v090.shadow import features, align_options
from strategies.sstrangle.poc.v090.qc_adapter import QCShadow
from strategies.sstrangle.poc.v090.pipeline import run, read_bundle
from strategies.sstrangle.poc.v090.fixtures import make_bundle
from strategies.sstrangle.poc.v090.test_axis import seeded, minute, quote, OP


@pytest.mark.parametrize('clock',['available_at','greek_available_at','greek_input_at'])
def test_T01_sampled_never_uses_known_future_clock(clock):
    rows,_=align_options([quote(**{clock:'2024-01-08T15:01:00+00:00'})],
                          '2024-01-08T15:00:00+00:00','sampled')
    assert rows==[], 'Unknown timing may be assumed; known future data must never be admitted'


def test_T02_stale_greek_input_not_refreshed_by_computation_time():
    rows,_=align_options([quote(greek_input_at='2024-01-05T15:00:00+00:00')],
                         '2024-01-08T15:00:00+00:00','strict')
    assert rows==[], 'Fresh Greek computation time cannot legitimize days-old market inputs'


def test_T03_gap_invalidates_prior_feature_until_new_segment_complete():
    a=seeded(total=26000.)
    a.update(minute(0,symbol='SPY'))  # complete bar
    r=minute(2,symbol='SPY');r['trade_notional']=1
    a.update(r)  # missing minute; no complete bar in new segment
    assert features(a,stamp(OP+timedelta(minutes=4)))['status']!='ready'


def test_T04_axis_returns_include_interbar_price_movement():
    a=seeded()
    a.update(minute(0,100,symbol='SPY'));a.update(minute(1,110,symbol='SPY'))
    f=features(a.bars,stamp(OP+timedelta(minutes=3)))
    assert f['last_return']==pytest.approx(math.log(110/100)), 'close/open erases movement between consecutive bars'


def test_T05_checkpoint_corruption_is_detected_before_resume():
    a=seeded(total=260000.);a.update(minute(0,symbol='SPY'))
    state=a.checkpoint();state['session']['partial']['activity']+=100000
    with pytest.raises(ValueError):Axis.restore(state)


def test_T06_receipt_must_attest_delivery_not_merely_have_hash(tmp_path):
    bundle=make_bundle(tmp_path/'in');m=json.loads(bundle.read_text())
    m['input_kind']='provider'
    receipt=bundle.parent/m['verification_receipt']['path']
    receipt.write_text(json.dumps({'status':'failed','release':'different-release'}))
    m['verification_receipt']['sha256']=hashlib.sha256(receipt.read_bytes()).hexdigest()
    bundle.write_text(json.dumps(m))
    with pytest.raises(ValueError):read_bundle(bundle)


def test_T07_decisions_outside_calendar_cannot_receive_success_report(tmp_path):
    bundle=make_bundle(tmp_path/'in');m=json.loads(bundle.read_text())
    f=bundle.parent/m['files']['decisions']['path'];d=json.loads(f.read_text())
    d.append({'decision_at':'2025-01-08T15:00:00+00:00','strategy':'C0'})
    f.write_text(json.dumps(d));m['files']['decisions']['sha256']=hashlib.sha256(f.read_bytes()).hexdigest()
    bundle.write_text(json.dumps(m))
    from .fixtures import seal_fixture
    seal_fixture(bundle)
    with pytest.raises(ValueError, match='decision outside calendar'):run(bundle,tmp_path/'out')


def test_T08_time_control_threshold_is_minutes_not_activity_units():
    a=seeded('time_control',total=26000.)
    for i in range(15):a.update(minute(i))
    assert a.bars[-1]['threshold']==15


def test_T09_latest_known_invalid_market_cannot_revive_older_quote():
    old=quote(observed_at='2024-01-08T14:58:30+00:00',quote_ts='2024-01-08T14:58:30+00:00')
    new=quote(bid=3,ask=1,source_row_id='q-new')
    rows,_=align_options([old,new],'2024-01-08T15:00:00+00:00')
    assert rows==[], 'Reject latest crossed state; do not cherry-pick older valid prices'


def test_T10_malformed_telemetry_does_not_interrupt_existing_decision():
    calendar=[dict(session='2024-01-08',open=stamp(OP),close=stamp(OP+timedelta(minutes=390)))]
    bridge=QCShadow(calendar);calls=[]
    bar=SimpleNamespace(time=OP.replace(tzinfo=None)-timedelta(hours=5),
                        end_time=OP.replace(tzinfo=None)-timedelta(hours=5)+timedelta(minutes=1),
                        open=100,high=100,low=100,close=100,is_fill_forward=True)
    algo=SimpleNamespace(utc_time=(OP+timedelta(minutes=1)).replace(tzinfo=None),
                         time=bar.end_time,index='SPX',securities={'SPX':SimpleNamespace(exchange=SimpleNamespace(time_zone=SimpleNamespace(id='America/New_York')))},slots=[],set_runtime_statistic=lambda *a:None)
    bridge.on_slice(algo,SimpleNamespace(bars={'SPX':bar}))
    calls.append('original decision')
    assert calls==['original decision']


def test_T11_final_session_has_explicit_finalization():
    bridge=QCShadow([dict(session='2024-01-08',open=stamp(OP),close=stamp(OP+timedelta(minutes=2)))])
    for i in range(2):bridge.minute(minute(i))
    bridge.finish()  # Required adapter API in0.9.0; called at end-of-algorithm.
    assert bridge.axis.session is None and bridge.final_summary['complete']
    assert bridge.axis.history == []  # Zero variation is complete, but cannot calibrate.


def test_T12_session_identity_must_match_exchange_date():
    a=Axis()
    with pytest.raises(ValueError):a.begin('2024-01-09',OP,OP+timedelta(minutes=390))


def test_C01_past_prefix_remains_immutable():
    a=seeded();a.update(minute(0,symbol='SPY'));old=copy.deepcopy(a.bars)
    a.update(minute(1,symbol='SPY'));assert a.bars[:1]==old


def test_C02_raw_one_minute_gate_retained():
    a=seeded();r=minute(0,symbol='SPY');r['frequency_seconds']=300
    with pytest.raises(ValueError):a.update(r)
