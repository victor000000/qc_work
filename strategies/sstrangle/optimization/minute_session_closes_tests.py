from datetime import datetime,date,timedelta,timezone
import pytest
from minute_session_closes import SessionBounds,MinuteTrade,session_closes
D=date(2020,1,1);ASOF=datetime(2020,5,1,12,tzinfo=timezone.utc)
def samples():
 ss=[SessionBounds(D+timedelta(days=i),datetime(2020,1,1,9,tzinfo=timezone.utc)+timedelta(days=i),datetime(2020,1,1,16,tzinfo=timezone.utc)+timedelta(days=i)) for i in range(61)]
 bb=[MinuteTrade('native',s.closed-timedelta(minutes=1),s.closed,100+i) for i,s in enumerate(ss)];return ss,bb
def run(ss,bb):return session_closes(bb,ss,'native','RAW',ASOF,ASOF.date())
def test_exact_actual_closes_and_early_close():
 ss,bb=samples();ss[-1]=SessionBounds(ss[-1].session,ss[-1].opened,ss[-1].closed-timedelta(hours=3));bb[-1]=MinuteTrade('native',ss[-1].closed-timedelta(minutes=1),ss[-1].closed,222)
 r=run(ss,bb);assert r.ready and len(r.points)==61 and r.points[-1].price==222 and r.points[-1].end_time==bb[-1].end
@pytest.mark.parametrize('kind',['missing','stale'])
def test_absent_close_unavailable_not_fabricated(kind):
 ss,bb=samples()
 if kind=='missing':bb.pop()
 else:bb[-1]=MinuteTrade('native',ss[-1].closed-timedelta(minutes=7),ss[-1].closed-timedelta(minutes=6),160)
 r=run(ss,bb);assert not r.ready and len(r.points)==60 and len(r.missing)+len(r.stale)==1
def test_five_minute_boundary_inclusive():
 ss,bb=samples();bb[-1]=MinuteTrade('native',ss[-1].closed-timedelta(minutes=6),ss[-1].closed-timedelta(minutes=5),160);assert run(ss,bb).ready
@pytest.mark.parametrize('kind',['identity','fillforward','outside','future','nonpositive'])
def test_invalid_source_rejected(kind):
 from dataclasses import replace
 ss,bb=samples();kw={'identity':dict(native_id='other'),'fillforward':dict(fill_forward=True),'outside':dict(start=ss[-1].opened-timedelta(hours=1),end=ss[-1].opened-timedelta(minutes=59)),'future':dict(end=ASOF+timedelta(minutes=1)),'nonpositive':dict(close=0)}[kind];bb[-1]=replace(bb[-1],**kw)
 with pytest.raises(ValueError):run(ss,bb)
def test_unordered_minutes_choose_actual_last_and_no_duplicate_samples():
 ss,bb=samples();assert run(ss,list(reversed(bb))+[bb[-1]]).ready
 from dataclasses import replace
 with pytest.raises(ValueError):run(ss,bb+[replace(bb[-1],close=999)])
def test_calendar_cannot_be_omitted_or_current():
 ss,bb=samples()
 with pytest.raises(ValueError):run(ss[:-1],bb)
 from dataclasses import replace
 ss[-1]=replace(ss[-1],session=ASOF.date())
 with pytest.raises(ValueError):run(ss,bb)
