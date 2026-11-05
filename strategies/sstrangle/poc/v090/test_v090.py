import copy
import itertools
import json
import math
from datetime import timedelta
import pytest
from .axis import Axis,stamp
from .shadow import align_options
from .test_axis import quote,minute,OP
from .fixtures import make_bundle
from .pipeline import run,file_hash
from .compare_axes import compare,read_complete,paired_interval,session_metrics


def test_conflict_resolution_independent_of_order_and_newer_recovers():
    bad=[quote(),quote(bid=.9),quote(contract_id='healthy')]
    for rows in itertools.permutations(bad):
        assert [r['contract_id'] for r in align_options(rows,'2024-01-08T15:00:00Z')[0]]==['healthy']
    new=quote(observed_at='2024-01-08T14:59:30Z',available_at='2024-01-08T14:59:31Z',source_row_id='new')
    for rows in itertools.permutations(bad+[new]):
        chain,_=align_options(rows,'2024-01-08T15:00:00Z')
        assert {r['source_row_id'] for r in chain}=={'new','q1'}


def test_zero_variation_complete_session_cannot_warmup():
    a=Axis(lookback=1)
    a.begin('2024-01-08',OP,OP+timedelta(minutes=2))
    for i in range(2):a.update(minute(i))
    assert a.finish()['complete'] and not a.history
    b=Axis.restore(a.checkpoint())
    assert b.begin('2024-01-09',OP+timedelta(days=1),OP+timedelta(days=1,minutes=2)) is None


def test_spy_control_has_26_intervals_and_restart_parity():
    a=Axis('time_control',control_symbol='SPY')
    a.begin('2024-01-08',OP,OP+timedelta(minutes=390))
    for i in range(177):a.update(minute(i,symbol='SPY'))
    b=Axis.restore(a.checkpoint())
    for i in range(177,390):
        r=minute(i,symbol='SPY');a.update(r);b.update(r)
    assert a.bars==b.bars and a.finish()==b.finish()
    assert len(a.bars)==26 and all(b['threshold_unit']=='minutes' for b in a.bars)
    with pytest.raises(ValueError):Axis('spx_variation',control_symbol='SPY')


def test_independent_dependence_oracle_and_no_gap_or_overnight_pair():
    bars=[]
    for segment,returns in [(0,[.1,.2,.3]),(1,[-.1,-.2,-.3])]:
        for r in returns:
            bars.append(dict(is_complete=True,sequence=len(bars)+1,segment_id=segment,
                start_reference_close=100,close=100*math.exp(r),duration_seconds=60,minute_variation=r*r))
    result=session_metrics(bars)
    # Centered [0.1,0.2,0.3] has zero lag-one numerator within each group.
    assert result['return_acf1']==pytest.approx(0,abs=1e-12)
    assert result['return_count']==6
    assert paired_interval([3.,3.,3.],100)==[3.,3.]
    assert paired_interval([1.],100) is None


@pytest.fixture
def runs(tmp_path):
    bundle=make_bundle(tmp_path/'input')
    run(bundle,tmp_path/'left','spy_close_volume','sampled')
    run(bundle,tmp_path/'right','time_control','sampled',control_symbol='SPY')
    return tmp_path/'left',tmp_path/'right'


def test_common_warmup_and_reproducible_comparison(runs):
    left,right=runs
    result=compare(left,right,100)
    assert len(result['common_sessions'])==3
    assert len(result['excluded_sessions'])==20
    assert result==compare(left,right,100)
    assert result['recipe_selected'] is None and not result['economic_acceptance']
    for row in result['paired_summary'].values():assert row['paired_sessions']<=3


def test_comparison_rejects_tampered_completion(runs):
    left,right=runs
    p=left/'axis_bars.jsonl';p.write_text(p.read_text()+'\n')
    with pytest.raises(ValueError,match='hash mismatch'):compare(left,right,100)


def test_comparison_rejects_different_underlying_even_if_resealed(runs):
    left,right=runs
    p=right/'axis_quality.json';r=json.loads(p.read_text());r['underlying']='SPX';p.write_text(json.dumps(r))
    p=right/'COMPLETE.json';r=json.loads(p.read_text());r['files']['axis_quality.json']=file_hash(right/'axis_quality.json');p.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='underlying'):compare(left,right,100)


def test_unknown_extra_files_are_not_completed_outputs(runs):
    left,_=runs;(left/'unhashed.txt').write_text('partial')
    with pytest.raises(ValueError,match='inventory'):read_complete(left)
