"""Point-in-time monthly top-N consumer ranking from verified provider rollups.

Requires caller-supplied prior exchange sessions and historical optionable IDs.
It cannot establish coverage or create missing observations itself.
"""
from datetime import date,datetime
import math

def stamp(value):
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('Timezone-aware availability/cutoff required')
    return t

def select_universes(rows,sessions,optionable_ids,cutoff):
    cut=stamp(cutoff)
    days=[date.fromisoformat(d) for d in sessions]
    if len(days)!=20 or days!=sorted(set(days)) or days[-1]>=cut.date():
        raise ValueError('Exactly20distinct completed prior sessions required')
    ids=sorted(set(optionable_ids));latest={};ignored=0
    for r in rows:
        key=(r['underlying_id'],r['session_date'])
        if key[0] not in ids or key[1] not in sessions:continue
        available=stamp(r['available_at_utc'])
        if available>=cut:ignored+=1;continue
        if available.date()<date.fromisoformat(key[1]):raise ValueError('Availability precedes session')
        previous=latest.get(key)
        if previous and available==stamp(previous['available_at_utc']) and r!=previous:
            raise ValueError('Conflicting same-version provider observation')
        if previous is None or available>stamp(previous['available_at_utc']):latest[key]=r
    scores=[];rejected=[]
    for identity in ids:
        records=[latest.get((identity,d)) for d in sessions]
        if any(r is None for r in records):
            rejected.append({'underlying_id':identity,'reason':'missing_session'});continue
        if any(any(r.get(k) is not True for k in ['chain_complete','volume_complete','classification_complete']) for r in records):
            rejected.append({'underlying_id':identity,'reason':'unverified_daily_coverage'});continue
        values=[float(r['monthly_35_95_volume']) for r in records]
        if any(not math.isfinite(v) or v<0 or not v.is_integer() for v in values):
            raise ValueError('Nonnegative integer contract volume required')
        score=sum(values)/20
        if score<=0:rejected.append({'underlying_id':identity,'reason':'zero_activity'});continue
        scores.append({'underlying_id':identity,'mean_option_volume':score})
    scores.sort(key=lambda r:(-r['mean_option_volume'],r['underlying_id']))
    for rank,r in enumerate(scores,1):r['rank']=rank
    return {'cutoff':cutoff,'sessions':sessions,'ranking':scores,'top50':scores[:50],
      'top100':scores[:100],'rejected':rejected,'future_observations_ignored':ignored,
      'coverage_note':'Input population/listing coverage must be verified separately; eligible names are never padded toN'}
