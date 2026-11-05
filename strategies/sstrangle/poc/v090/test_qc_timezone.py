from datetime import datetime,timedelta,timezone
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo
import pytest
from .qc_adapter import QCShadow
from .axis import stamp

@pytest.mark.parametrize('day,length',[('2022-07-08',390),('2022-11-25',210),('2024-03-08',390),('2024-03-11',390)])
def test_exchange_clock_full_session_and_postclose_fillforward(day,length):
    opened=datetime.fromisoformat(day+'T09:30:00').replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)
    bridge=QCShadow([dict(session=day,open=stamp(opened),close=stamp(opened+timedelta(minutes=length)))])
    for i in range(length+60):
        start=opened+timedelta(minutes=i);end=start+timedelta(minutes=1)
        bar=NS(time=start.astimezone(ZoneInfo('America/Chicago')).replace(tzinfo=None),end_time=end.astimezone(ZoneInfo('America/Chicago')).replace(tzinfo=None),open=100,high=100,low=100,close=100,is_fill_forward=i>=length)
        algo=NS(utc_time=end.replace(tzinfo=None),time=end.astimezone(ZoneInfo('America/New_York')).replace(tzinfo=None),index='SPX',slots=[],securities={'SPX':NS(exchange=NS(time_zone=NS(id='America/Chicago')))})
        bridge.on_slice(algo,NS(bars={'SPX':bar}))
    summary=bridge.finish()
    assert bridge.valid and summary['complete']
    assert summary['observed_minutes']==summary['expected_minutes']==length


def test_decision_counts_distinguish_ready_from_warmup_without_exporting_features():
    from .test_axis import seeded,OP
    bridge=QCShadow([dict(session='2024-01-08',open=stamp(OP),close=stamp(OP+timedelta(minutes=30)))])
    bridge.axis=seeded('spx_variation',total=26e-8)
    for i in range(3):
        start=OP+timedelta(minutes=i);end=start+timedelta(minutes=1);price=100+i
        bar=NS(time=start,end_time=end,open=price,high=price,low=price,close=price,is_fill_forward=False)
        algo=NS(utc_time=end,time=end.astimezone(ZoneInfo('America/New_York')),index='SPX',slots=[(9,31),(9,32),(9,33)],set_runtime_statistic=lambda *args:None)
        bridge.on_slice(algo,NS(bars={'SPX':bar}))
    assert bridge.valid
    assert bridge.decision_status_counts=={'no_completed_axis':2,'ready':1}
