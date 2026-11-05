"""Actual minute-trade session closes for prospective futures RV features only."""
from dataclasses import dataclass
from datetime import date,datetime,timedelta
import math
from completed_volatility import CompletedPrice
@dataclass(frozen=True)
class SessionBounds:
    session:date
    opened:datetime
    closed:datetime
@dataclass(frozen=True)
class MinuteTrade:
    native_id:str
    start:datetime
    end:datetime
    close:float
    fill_forward:bool=False
@dataclass(frozen=True)
class SessionCloses:
    points:tuple
    missing:tuple
    stale:tuple
    source_bars:int
    ready:bool

def session_closes(bars,sessions,native_id,epoch,asof,decision_session,max_age=timedelta(minutes=5)):
    if asof.tzinfo is None or max_age<timedelta(0):raise ValueError('Aware decision clock and valid close-age policy required')
    sessions=list(sessions)
    if len(sessions)!=61 or len({s.session for s in sessions})!=61 or any(a.session>=b.session for a,b in zip(sessions,sessions[1:])):raise ValueError('Exactly61 ordered native calendar sessions required')
    for s in sessions:
        if s.opened.tzinfo is None or s.closed.tzinfo is None or not s.opened<s.closed<=asof or s.session>=decision_session:raise ValueError('Uncompleted/invalid native session')
        if s.opened.date()!=s.session or s.closed.date()!=s.session:raise ValueError('Adapter requires same-date regular sessions')
    lookup={s.session:s for s in sessions};last={};observed={};count=0
    for b in bars:
        count+=1
        if b.native_id!=native_id or b.fill_forward:raise ValueError('Native identity/fill-forward violation')
        if b.start.tzinfo is None or b.end.tzinfo is None or b.end>asof or not b.start<b.end:raise ValueError('Invalid or future source timestamps')
        if not math.isfinite(b.close) or b.close<=0:raise ValueError('Invalid actual minute close')
        s=lookup.get(b.end.date())
        if s is None:raise ValueError('Source minute outside requested completed sessions')
        if not s.opened<=b.start<b.end<=s.closed:raise ValueError('Source minute outside native regular hours')
        if b.end in observed and observed[b.end]!=b.close:raise ValueError('Conflicting source minute duplicate')
        observed[b.end]=b.close
        if s.session not in last or b.end>last[s.session].end:last[s.session]=b
    points=[];missing=[];stale=[]
    for s in sessions:
        b=last.get(s.session)
        if b is None:missing.append(str(s.session));continue
        if s.closed-b.end>max_age:stale.append(str(s.session));continue
        points.append(CompletedPrice(native_id,s.session,b.end,b.close,epoch))
    return SessionCloses(tuple(points),tuple(missing),tuple(stale),count,not missing and not stale)
