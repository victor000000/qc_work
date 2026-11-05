"""Pure per-decision feature evaluation from completed pinned daily rows only."""
import math
from datetime import date,timedelta

def feature_value(rows,day,feature):
    # Each row is [ISO session day, high, low, close, volume].
    # At intraday NY decisions, prior-session rows were available at next midnight.
    past=[r for r in rows if r[0]<day]
    if not past:return None,None
    latest=past[-1];age=(date.fromisoformat(day)-date.fromisoformat(latest[0])-timedelta(days=1)).days
    if age>=7:return None,latest[0]
    if feature.endswith('_range_pct'):
        value=(float(latest[1])-float(latest[2]))/float(latest[3])
    elif feature.endswith('_volume_z20'):
        if len(past)<20:return None,latest[0]
        vals=[float(x[4]) for x in past[-20:]];mean=math.fsum(vals)/20
        variance=math.fsum((x-mean)**2 for x in vals)/19
        value=(vals[-1]-mean)/math.sqrt(variance) if variance>0 else None
    else:raise ValueError('Unsupported frozen feature: '+feature)
    if value is None or not math.isfinite(value):return None,latest[0]
    return value,latest[0]

def rule_pass(value,threshold,side):
    if value is None:return False
    if side=='above':return value>threshold
    if side=='below':return value<=threshold
    raise ValueError('Unknown rule direction')
