"""A partial provider replay must retain whole cycles and exclude future bars."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest

LOCAL = Path(__file__).resolve().parents[1]/'local'
sys.path.insert(0, str(LOCAL))
from replay import assign_cycles, covered_rows, price_rows, validate_replay_inputs


def test_partial_fills_cannot_silently_share_the_last_order_price():
    rows = [dict(order_id=1, quantity=-1, fee=1), dict(order_id=1, quantity=-1, fee=1)]
    with pytest.raises(ValueError, match='event-level price keys'):
        validate_replay_inputs(rows, {1: 2.5}, 250000)


@pytest.mark.parametrize('price', [0, -1, float('nan'), float('inf')])
def test_replay_rejects_invalid_prices_before_engine_output(price):
    with pytest.raises(ValueError, match='price must be finite and positive'):
        validate_replay_inputs([dict(order_id=1, quantity=-1, fee=1)], {1: price}, 250000)


def test_missing_leg_excludes_entire_cycle():
    rows = [dict(cycle_id=1,age_minutes=1),dict(cycle_id=1,age_minutes=None),
            dict(cycle_id=2,age_minutes=5),dict(cycle_id=2,age_minutes=0)]
    assert [r['cycle_id'] for r in covered_rows(rows,5)] == [2,2]
    assert len(covered_rows(rows,None)) == 4


def test_no_future_bar_close_or_previous_day_fill(tmp_path):
    import hashlib
    c=tmp_path/'provider_capture';c.mkdir()
    doc=dict(pages=[dict(bars={'SPY240517P00486000':[
        dict(t='2024-04-11T19:29:00Z',c=99,v=1),
        dict(t='2024-04-12T19:29:00Z',c=3.1,v=4),
        dict(t='2024-04-12T19:30:00Z',c=200,v=9)]})])
    f=c/'minute_2024-04-12.json';f.write_text(json.dumps(doc))
    (c/'manifest.json').write_text(json.dumps(dict(failures=[],completed_jobs=1,requested_jobs=1,
        files={f.name:hashlib.sha256(f.read_bytes()).hexdigest()})))
    out=price_rows(tmp_path,[dict(symbol='SPY240517P00486000',timestamp='2024-04-12T19:30:00+00:00')])[0]
    assert out['provider_price']==3.1 and out['age_minutes']==0


def test_cycle_ids_include_both_roll_legs():
    rows=[dict(group_id=str(g),tag='SPY:'+reason) for g,reason in
        [(1,'OPEN'),(1,'OPEN'),(2,'ROLL'),(2,'ROLL'),(3,'STOP'),(3,'STOP')]]
    assign_cycles(rows)
    assert {r['cycle_id'] for r in rows}=={1}


def test_entry_features_never_use_entry_day_close():
    import pandas as pd
    from warehouse import daily_features,attach_features
    prices=pd.DataFrame(dict(symbol=['SPY']*40,date=pd.date_range('2024-01-01',periods=40),close=range(100,140)))
    trades=pd.DataFrame(dict(cycle_id=[1],ticker=['SPY'],entry=pd.to_datetime(['2024-02-01T20:30:00Z'],utc=True)))
    first=attach_features(trades,daily_features(prices)).iloc[0]
    prices.loc[prices['date']>=pd.Timestamp('2024-02-01'),'close']=1000000
    changed=attach_features(trades,daily_features(prices)).iloc[0]
    assert first['source_day']==pd.Timestamp('2024-01-31')
    assert first['available_at']<=first['entry']
    for key in ['ret_1d','ret_5d','ret_20d','rv20','close_sma20_ratio']:
        assert first[key]==changed[key]
