"""Bounded, readable aggregate telemetry; raw native orders remain authoritative."""
import json

def bounded_statistics(core, counts, annual):
    result={str(k):str(v) for k,v in core.items()}
    for year,value in sorted(annual.items()):result['episodes_'+str(year)]=str(value)
    direct={'filled_episodes','submitted_episodes','rejected_episodes','native_fill_events',
            'native_expiry_events','scheduled_slots','original_wing_skips','recovered_filled_episodes'}
    chunk={};chunks=[]
    for key,value in sorted(counts.items()):
        if key in direct:result[key]=str(value);continue
        candidate=dict(chunk);candidate[key]=value
        if len(json.dumps(candidate,separators=(',',':')))>180:
            if not chunk:raise ValueError('Aggregate statistic exceeds quota')
            chunks.append(chunk);chunk={key:value}
        else:chunk=candidate
    if chunk:chunks.append(chunk)
    for i,chunk in enumerate(chunks,1):result['counts_'+str(i).zfill(2)]=json.dumps(chunk,separators=(',',':'))
    result['counts_chunks']=str(len(chunks))
    if len(result)>50 or any(len(k)>200 or len(v)>200 for k,v in result.items()):
        raise ValueError('QC runtime statistic quota exceeded')
    return result
