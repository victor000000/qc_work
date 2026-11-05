from datetime import datetime, timedelta, timezone
import copy
import json
import pytest
from .axis import Axis, stamp, digest
from .shadow import features, attach_shadow, ShadowAdapter, align_options, selected_leg_clock_gate
from .pipeline import run, read_bundle

OP = datetime(2024, 1, 8, 14, 30, tzinfo=timezone.utc)


def minute(i, price=100., symbol='SPX', opened=OP):
    return dict(session=opened.date().isoformat(), symbol=symbol,
                start=stamp(opened+timedelta(minutes=i)), end=stamp(opened+timedelta(minutes=i+1)),
                available_at=stamp(opened+timedelta(minutes=i+1, seconds=1)), frequency_seconds=60,
                open=price, high=price, low=price, close=price, volume=10., trade_notional=1000.,
                source_row_id=f'{opened.isoformat()}:{i}', is_fill_forward=False)


def seeded(recipe='spy_dollar', total=26000., mode='strict', length=30):
    a = Axis(recipe, mode)
    a.seed([dict(session=f'2023-12-{i:02}', activity=total, complete=True,
                 available_at=f'2023-12-{i:02}T21:00:01+00:00') for i in range(1,21)])
    a.begin('2024-01-08', OP, OP+timedelta(minutes=length))
    return a


def test_exact_and_overshoot_only_one_event_per_minute():
    a=seeded()
    assert a.update(minute(0, symbol='SPY'))['activity']==1000
    r=minute(1,symbol='SPY');r['trade_notional']=3000
    b=a.update(r)
    assert b['overshoot']==2000 and len(a.bars)==2 and a.session['partial'] is None


def test_future_calibration_is_not_used():
    a=Axis()
    history=[dict(session=f'2023-12-{i:02}',activity=26.,complete=True,
                  available_at='2024-01-09T21:00:00+00:00') for i in range(1,21)]
    a.seed(history)
    assert a.begin('2024-01-08',OP,OP+timedelta(minutes=30)) is None
    assert a.update(minute(0)) is None


def test_no_overnight_or_gap_return_and_incomplete_history():
    a=seeded('spx_variation',total=26.)
    a.update(minute(0,100));a.update(minute(2,200))
    assert a.session['total']==0 and a.session['segment']==1
    assert not a.finish()['complete']
    assert len(a.history)==20
    a.begin('2024-01-09',OP+timedelta(days=1),OP+timedelta(days=1,minutes=2))
    a.update(minute(0,400,opened=OP+timedelta(days=1)))
    assert a.session['total']==0


def test_checkpoint_prefix_and_batch_parity():
    rows=[minute(i,100+i,symbol='SPY') for i in range(30)]
    full=seeded();prefix=seeded()
    for r in rows[:7]:prefix.update(r)
    saved=copy.deepcopy(prefix.bars)
    resumed=Axis.restore(json.loads(json.dumps(prefix.checkpoint())))
    for r in rows[7:]:resumed.update(r)
    for r in rows:full.update(r)
    assert resumed.bars==full.bars and full.bars[:7]==saved
    assert resumed.finish()==full.finish()
    assert resumed.checkpoint()==full.checkpoint()


@pytest.mark.parametrize('field,value', [('frequency_seconds',300),('available_at',None),
 ('is_fill_forward',True),('close',float('nan')),('symbol','SPY'),('source_row_id','')])
def test_bad_inputs_fail_closed(field,value):
    a=seeded('spx_variation');r=minute(0);r[field]=value
    with pytest.raises((ValueError,KeyError)):a.update(r)


def test_duplicate_and_late_revisions_rejected():
    a=seeded();r=minute(0,symbol='SPY');a.update(r)
    with pytest.raises(ValueError):a.update(r)


def test_unknown_availability_only_in_labeled_sampled_mode():
    a=seeded(mode='sampled');r=minute(0,symbol='SPY');r['available_at']=None
    b=a.update(r);assert b['quality_flags']==['assumed_minute_availability']


def test_tail_is_not_a_feature_and_time_axis_session_anchored():
    a=seeded('time_control',length=16)
    for i in range(16):a.update(minute(i))
    a.finish();assert [b['is_complete'] for b in a.bars]==[True,False]
    assert features(a.bars,stamp(OP+timedelta(minutes=15)))['status']=='no_completed_axis'
    assert features(a.bars,stamp(OP+timedelta(minutes=17)))['last_axis_id']==a.bars[0]['axis_id']
    assert features(a.bars,stamp(OP+timedelta(minutes=46)))['status']=='stale_axis'


def test_time_axis_gap_fragment_is_not_complete():
    a=seeded('time_control')
    for i in list(range(5))+list(range(6,30)):a.update(minute(i))
    assert [b['is_complete'] for b in a.bars]==[False,False,True]


@pytest.mark.parametrize('opened', [datetime(2024,3,8,14,30,tzinfo=timezone.utc),
 datetime(2024,3,11,13,30,tzinfo=timezone.utc),datetime(2024,11,29,14,30,tzinfo=timezone.utc)])
def test_explicit_calendar_dst_and_early_close(opened):
    a=Axis('time_control');a.begin(opened.date().isoformat(),opened,opened+timedelta(minutes=210))
    for i in range(210):a.update(minute(i,opened=opened))
    assert a.finish()['complete'] and len(a.bars)==14


def quote(**changes):
    r=dict(contract_id='p',source_row_id='q1',root='SPXW',expiry='2024-01-08',listed_asof=True,
       observed_at='2024-01-08T14:59:00+00:00',quote_ts='2024-01-08T14:58:50+00:00',
       available_at='2024-01-08T14:59:01+00:00',greek_available_at='2024-01-08T14:59:02+00:00',
       greek_asof='2024-01-08T14:59:00+00:00',greek_input_at='2024-01-08T14:58:50+00:00',
       frequency_seconds=60,greek_frequency_seconds=60,greek_model_accepted=True,bid=1.,ask=1.2,delta=-.2,spot=100.)
    r.update(changes);return r


def test_option_clocks_future_and_5m_rejected():
    good=quote(); unknown=quote(contract_id='x',quote_ts=None);five=quote(contract_id='y',frequency_seconds=300)
    future=quote(contract_id='z',greek_input_at='2024-01-08T15:01:00+00:00')
    chain,bad=align_options([good,unknown,five,future],'2024-01-08T15:00:00+00:00')
    assert [r['contract_id'] for r in chain]==['p'] and len(bad)==3
    assert len(align_options([unknown],'2024-01-08T15:00:00+00:00','sampled')[0])==1


def test_cross_leg_skew_and_duplicate():
    assert selected_leg_clock_gate([quote(),quote(quote_ts='2024-01-08T14:58:20+00:00')])
    assert not selected_leg_clock_gate([quote(),quote(quote_ts='2024-01-08T14:58:19+00:00')])
    assert len(align_options([quote(),quote()],'2024-01-08T15:00:00+00:00')[0])==1
    with pytest.raises(ValueError):align_options([quote(),quote(bid=.9)],'2024-01-08T15:00:00+00:00')


def test_shadow_calls_existing_decision_once_no_mutation():
    a=seeded();decisions=[{'decision_at':'2024-01-08T15:00:00+00:00','order':['put',-1]}]
    before=copy.deepcopy(decisions)
    result=attach_shadow(decisions,a.bars);assert decisions==before and result[0]['decision']==before[0]
    calls=[];value=object()
    def selector():calls.append(1);return value
    assert ShadowAdapter(a).decide(decisions[0]['decision_at'],selector) is value
    assert calls==[1]


def test_frozen_selector_shadow_same_contracts_and_cash():
    from strategies.sstrangle.poc.v087.local_engine import Leg,select,account
    chain=[Leg('lp',80,'P',-.1,.5,.7,110),Leg('sp',100,'P',-.2,2.,2.2,110),
           Leg('sc',120,'C',.08,2.,2.2,110),Leg('lc',140,'C',.02,.5,.7,110)]
    a=seeded();base=select(chain,'condor')
    result=ShadowAdapter(a).decide('2024-01-08T15:00:00+00:00',select,chain,'condor')
    assert result==base and account(result[0],110,'conservative')==account(base[0],110,'conservative')


def test_end_to_end_and_hash_tamper(tmp_path):
    from .fixtures import make_bundle
    bundle=make_bundle(tmp_path/'input')
    for recipe in ('spx_variation','spy_dollar','time_control'):
        r=run(bundle,tmp_path/recipe,recipe)
        assert r['completed_bars']>0 and r['ready_features']>0 and r['original_decisions_unchanged']
    m=json.loads(bundle.read_text());f=bundle.parent/m['files']['minutes']['path'];f.write_text('[]')
    with pytest.raises(ValueError,match='hash mismatch'):read_bundle(bundle)


def test_qc_assembly_keeps_trading_body_exact(tmp_path):
    from pathlib import Path
    from .build_qc_shadow import build
    base=Path(__file__).parents[1]/'v087'/'strategy_official_funded.py'
    calendar=tmp_path/'calendar.json';calendar.write_text(json.dumps([dict(session='2024-01-08',open=stamp(OP),close=stamp(OP+timedelta(minutes=390)))]))
    build(base,calendar,tmp_path/'qc')
    assembled=(tmp_path/'qc/main.py').read_text()
    stripped=assembled.replace('from qc_axis_v089 import QCShadow\nfrom axis_calendar_v089 import CALENDAR\n','',1).replace('        self.axis_shadow = QCShadow(CALENDAR)\n','',1).replace('        self.axis_shadow.on_slice(self, data)\n','',1).replace('        self.axis_shadow.finish(self)\n','',1)
    assert stripped==base.read_text()


def test_qc_bridge_matches_local_builder():
    from .qc_adapter import QCShadow
    c=[dict(session='2024-01-08',open=stamp(OP),close=stamp(OP+timedelta(minutes=30)))]
    bridge=QCShadow(c);local=Axis(mode='sampled',release='qc-native-minute-shadow',retention=128,calendar_hash=digest(c))
    local.begin('2024-01-08',OP,OP+timedelta(minutes=30))
    for i in range(30):
        r=minute(i,100+i);r['available_at']=None
        bridge.minute(r);local.update(r)
    assert bridge.axis.checkpoint()==local.checkpoint()


def test_sampled_bundle_does_not_claim_strict(tmp_path):
    import hashlib
    from .fixtures import make_bundle
    b=make_bundle(tmp_path/'in');m=json.loads(b.read_text());f=b.parent/'minutes.json'
    rows=json.loads(f.read_text())
    for r in rows:r['available_at']=None
    f.write_text(json.dumps(rows));m['files']['minutes']['sha256']=hashlib.sha256(f.read_bytes()).hexdigest();b.write_text(json.dumps(m))
    from .fixtures import seal_fixture
    seal_fixture(b)
    with pytest.raises(ValueError,match='availability'):run(b,tmp_path/'strict')
    r=run(b,tmp_path/'sampled',mode='sampled');assert r['mode']=='sampled' and not r['economic_acceptance']


def test_unaccepted_greek_methodology_cannot_pass_strict():
    chain,bad=align_options([quote(greek_model_accepted=False)],'2024-01-08T15:00:00+00:00')
    assert not chain and bad[0]['reason']=='unaccepted_greek_model'


def test_expired_contracts_and_exact_deadline_excluded():
    rows=[quote(expiry='2024-01-05'),quote(contract_id='x',observed_at='2024-01-08T15:00:00+00:00')]
    assert not align_options(rows,'2024-01-08T15:00:00+00:00')[0]


def test_constant_no_activity_never_fakes_threshold_bar():
    a=seeded('spx_variation')
    for i in range(30):assert a.update(minute(i)) is None
    a.finish();assert all(not b['is_complete'] for b in a.bars)


def test_parquet_option_delivery_matches_json(tmp_path):
    import hashlib
    import pyarrow as pa
    import pyarrow.parquet as pq
    from .fixtures import make_bundle
    b=make_bundle(tmp_path/'in');m=json.loads(b.read_text())
    reference=run(b,tmp_path/'json')
    options=json.loads((b.parent/'options.json').read_text())
    for r in options:
        for key in ['observed_at','quote_ts','available_at','greek_available_at','greek_asof','greek_input_at']:
            r[key]=datetime.fromisoformat(r[key])
    p=b.parent/'options.parquet';pq.write_table(pa.Table.from_pylist(options),p)
    m['files']['options']=dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest());b.write_text(json.dumps(m))
    from .fixtures import seal_fixture
    seal_fixture(b)
    actual=run(b,tmp_path/'parquet')
    assert actual==reference
