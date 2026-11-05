"""Completed SCALED_RAW US-equity RV entry features; caller supplies real history."""
from datetime import datetime,time,timedelta
from zoneinfo import ZoneInfo
import math
from completed_volatility import CompletedPrice,CompletedVolatilityWindow,VolatilityFeatures
NY=ZoneInfo('America/New_York')
def expected_equity_sessions(hours,local):
    result=[]
    for offset in range(130,0,-1):
        day=datetime.combine(local.date()-timedelta(days=offset),time())
        close=hours.get_last_daily_market_close(day,False)
        if close.date()==day.date() and close<=local:result.append(day.date())
    if len(result)<61:raise ValueError('US equity calendar cannot establish61completed sessions')
    return result[-61:]
def equity_features(bars,native_id,local,expected,iv):
    if len(expected)!=61 or len(set(expected))!=61 or expected!=sorted(expected):raise ValueError('61actual equity calendar sessions required')
    asof=local.replace(tzinfo=NY);points=[]
    for b in bars:
        if str(b.symbol.id)!=native_id or b.is_fill_forward:raise ValueError('Equity RV source identity/fill-forward violation')
        end=b.end_time.replace(tzinfo=NY)
        if end>asof or end.date()>=local.date():raise ValueError('Equity RV source includes uncompleted session')
        points.append(CompletedPrice(native_id,end.date(),end,float(b.close),'SCALED_RAW_asof_'+str(local.date())))
    points=points[-61:]
    if [p.session for p in points]!=expected:return VolatilityFeatures(len(points),max(0,len(points)-1),None,None,None,False,'equity_rv_history_incomplete')
    w=CompletedVolatilityWindow();w.replace_rebased_history(points,asof,local.date(),consecutive=True)
    return w.features(iv,expected_last_session=expected[-1])
def validate_equity_rv_threshold(threshold):
    if isinstance(threshold,bool) or not math.isfinite(threshold) or threshold<=0:raise ValueError('Positive declared equity IV/RV threshold required')
    return threshold
def equity_rv_admitted(feature,threshold):
    validate_equity_rv_threshold(threshold)
    return bool(feature.ready and feature.iv_to_max_realized is not None and math.isfinite(feature.iv_to_max_realized) and feature.iv_to_max_realized>=threshold)
