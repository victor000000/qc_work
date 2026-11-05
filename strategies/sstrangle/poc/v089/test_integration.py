"""Independent semantic checks beyond the original review reproductions."""
import copy
import json
import math
import random
from datetime import timedelta, timezone
from types import SimpleNamespace
from pathlib import Path
import pytest
from .axis import Axis, stamp, digest
from .shadow import features, align_options, select_package, ShadowAdapter
from .test_axis import seeded, minute, quote, OP
from .qc_adapter import QCShadow
from .contracts import validate_calendar
from .fixtures import make_bundle, seal_fixture
from .pipeline import run, file_hash


@pytest.mark.parametrize('cut', range(0,31,3))
def test_restart_every_boundary_and_independent_accumulator(cut):
    rng=random.Random(89)
    rows=[minute(i,100+i/10,symbol='SPY') for i in range(30)]
    for r in rows:r['trade_notional']=rng.choice([0,500,1000,2500])
    full=seeded(total=52000);part=seeded(total=52000)
    expected=[];acc=0
    for i,r in enumerate(rows):
        acc+=r['trade_notional']
        if acc>=2000:expected.append((i+1,acc));acc=0
        full.update(r)
    for r in rows[:cut]:part.update(r)
    before=copy.deepcopy(part.bars)
    part=Axis.restore(part.checkpoint())
    for r in rows[cut:]:part.update(r)
    assert full.bars==part.bars and part.bars[:len(before)]==before
    assert [(int((__import__('datetime').datetime.fromisoformat(b['end_event_time'])-OP).total_seconds()/60),b['activity']) for b in full.bars]==expected


def test_gap_known_time_not_backdated_and_recovers():
    a=seeded(total=26000);a.update(minute(0,symbol='SPY'))
    past=features(a,stamp(OP+timedelta(minutes=2)))
    row=minute(2,symbol='SPY');row['trade_notional']=1;a.update(row)
    assert features(a,stamp(OP+timedelta(minutes=2)))==past
    assert features(a,stamp(OP+timedelta(minutes=4)))['status']=='gap_waiting_for_complete_axis'
    a.update(minute(3,symbol='SPY'))
    f=features(a,stamp(OP+timedelta(minutes=5)))
    assert f['status']=='ready' and f['last_return'] is None


def test_missing_final_minute_invalidation_at_close_watermark():
    a=seeded(length=3);a.update(minute(0,symbol='SPY'))
    past=features(a,stamp(OP+timedelta(minutes=2)))
    a.finish()
    assert features(a,stamp(OP+timedelta(minutes=2)))==past
    assert features(a,stamp(OP+timedelta(minutes=4)))['status']=='gap_waiting_for_complete_axis'


def test_close_returns_and_minute_variation_differ():
    a=seeded(total=52000)
    for i,p in enumerate([100,110,100,120]):a.update(minute(i,p,symbol='SPY'))
    f=features(a,stamp(OP+timedelta(minutes=5)))
    assert f['last_return']==pytest.approx(math.log(120/110))
    assert a.bars[1]['minute_variation']==pytest.approx(math.log(100/110)**2+math.log(120/100)**2)
    assert f['minutes_to_expiry']==25


@pytest.mark.parametrize('field',['quote_ts','available_at','greek_asof','greek_input_at','greek_available_at'])
def test_equal_deadline_clock_rejected_in_both_modes(field):
    for mode in ['strict','sampled']:
        assert not align_options([quote(**{field:'2024-01-08T15:00:00+00:00'})],'2024-01-08T15:00:00+00:00',mode)[0]


def test_future_arrival_does_not_suppress_known_past_quote():
    old=quote(observed_at='2024-01-08T14:58:30+00:00',quote_ts='2024-01-08T14:58:20+00:00')
    new=quote(source_row_id='future',available_at='2024-01-08T15:01:00+00:00')
    chain,bad=align_options([new,old],'2024-01-08T15:00:00+00:00')
    assert chain[0]['source_row_id']=='q1' and len(chain)==1


def package(skew):
    rows=[]
    for cid,k,right,delta in [('lp',80,'P',-.1),('sp',100,'P',-.2),('sc',120,'C',.08),('lc',140,'C',.02)]:
        rows.append(quote(contract_id=cid,source_row_id=cid,strike=k,right=right,delta=delta,spot=110,
            quote_ts=stamp(OP+timedelta(minutes=29,seconds=-skew if cid=='lc' else 0))))
    return rows


@pytest.mark.parametrize('skew,accepted',[(29,True),(30,True),(31,False)])
def test_actual_package_selector_enforces_skew(skew,accepted):
    legs,status,_,_=select_package(package(skew),'2024-01-08T15:00:00+00:00')
    assert bool(legs)==accepted
    if not accepted:assert status=='selected_leg_clock_skew'


def test_bad_checkpoint_semantics_rejected_even_with_recomputed_digest():
    a=seeded();s=a.checkpoint();s['session']['count']=-1
    s.pop('state_digest');s['state_digest']=digest(s)
    with pytest.raises(ValueError):Axis.restore(s)


def test_bounded_axis_state():
    a=Axis('time_control',retention=8)
    a.begin('2024-01-08',OP,OP+timedelta(minutes=390))
    for i in range(390):a.update(minute(i))
    assert len(a.bars)==8 and a.session['sequence']==26
    b=Axis.restore(a.checkpoint());assert b.finish()==a.finish()


def test_invalid_calendar_and_decision_coverage():
    with pytest.raises(ValueError):validate_calendar([dict(session='2024-01-09',open=stamp(OP),close=stamp(OP+timedelta(minutes=390)))])
    c=dict(session='2024-01-08',open=stamp(OP),close=stamp(OP+timedelta(minutes=390)))
    with pytest.raises(ValueError):validate_calendar([c,c])


class Store:
    def __init__(self):self.values={}
    def save(self,key,value):
        assert key not in self.values
        self.values[key]=value;return True


def test_qc_end_hook_and_telemetry_failure_isolation():
    c=[dict(session='2024-01-08',open=stamp(OP),close=stamp(OP+timedelta(minutes=2)))]
    bridge=QCShadow(c)
    for i in range(2):bridge.minute(minute(i))
    algo=SimpleNamespace(object_store=Store())
    assert bridge.finish(algo)['complete']
    assert bridge.finish(algo)['complete'] and len(algo.object_store.values)==1
    bad=QCShadow(c);algo.object_store=SimpleNamespace(save=lambda *args:False)
    bad.finish(algo)
    assert not bad.valid and bad.errors


def test_native_error_not_swallowed_by_shadow():
    adapter=ShadowAdapter(seeded())
    def native():raise RuntimeError('native risk error')
    with pytest.raises(RuntimeError,match='native risk error'):adapter.decide(stamp(OP),native)


def test_corrupt_shadow_does_not_interrupt_native_callback():
    a=seeded();adapter=ShadowAdapter(a);calls=[]
    a.bars=[{}]
    assert adapter.decide(stamp(OP),lambda:calls.append(1) or 'native')=='native'
    assert calls==[1] and not adapter.valid


def test_qc_actual_delivery_time_is_retained():
    bridge=QCShadow([dict(session='2024-01-08',open=stamp(OP),close=stamp(OP+timedelta(minutes=30)))])
    bar=SimpleNamespace(time=OP.astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).replace(tzinfo=None),
        end_time=(OP+timedelta(minutes=1)).astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).replace(tzinfo=None),
        open=100,high=100,low=100,close=100,is_fill_forward=False)
    algo=SimpleNamespace(utc_time=(OP+timedelta(minutes=2)).replace(tzinfo=None),time=bar.end_time,index='SPX',slots=[])
    bridge.on_slice(algo,SimpleNamespace(bars={'SPX':bar}))
    assert bridge.valid and bridge.axis.source_cursor['available_at']==stamp(OP+timedelta(minutes=2))


def test_incomplete_output_has_no_completion_marker(tmp_path):
    b=make_bundle(tmp_path/'in');m=json.loads(b.read_text());f=b.parent/'minutes.json'
    rows=json.loads(f.read_text());rows[-2]['close']=-1;f.write_text(json.dumps(rows))
    m['files']['minutes']['sha256']=file_hash(f);b.write_text(json.dumps(m));seal_fixture(b)
    with pytest.raises(ValueError):run(b,tmp_path/'out')
    assert not (tmp_path/'out/COMPLETE.json').exists()


def test_streamed_output_counts_and_hashes(tmp_path):
    b=make_bundle(tmp_path/'in');r=run(b,tmp_path/'out',recipe='time_control')
    completion=json.loads((tmp_path/'out/COMPLETE.json').read_text())
    for path,sha in completion['files'].items():assert file_hash(tmp_path/'out'/path)==sha
    bars=[json.loads(x) for x in (tmp_path/'out/axis_bars.jsonl').read_text().splitlines()]
    assert sum(x['is_complete'] for x in bars)==r['completed_bars']==92
    assert len((tmp_path/'out/decision_shadow.jsonl').read_text().splitlines())==23


def test_provider_identity_cannot_relabel_fixture(tmp_path):
    b=make_bundle(tmp_path/'in');m=json.loads(b.read_text());m['input_kind']='provider';b.write_text(json.dumps(m))
    with pytest.raises(ValueError,match='identity mismatch'):run(b,tmp_path/'out')


def test_qc_day_transition_retains_tail_and_missing_minute_receipt():
    nextday=OP+timedelta(days=1)
    c=[dict(session='2024-01-08',open=stamp(OP),close=stamp(OP+timedelta(minutes=3))),
       dict(session='2024-01-09',open=stamp(nextday),close=stamp(nextday+timedelta(minutes=3)))]
    bridge=QCShadow(c);bridge.minute(minute(0))
    bridge.minute(minute(0,opened=nextday))
    assert any(r['kind']=='quality' and r['value']['reason']=='missing_final_minute' for r in bridge.records)
    assert any(r['kind']=='session' and not r['value']['complete'] for r in bridge.records)
