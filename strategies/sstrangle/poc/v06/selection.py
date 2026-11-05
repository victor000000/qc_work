"""Pure exact-width pair selection used by the QC adapter and local regression."""
def choose_exact_pairs(puts,calls,by_key,put_right,call_right,put_target,call_target,width=20):
    """Candidates and keyed wings must already pass the same as-of quote gate."""
    paired_puts=[c for c in puts if (put_right,float(c.strike)-width) in by_key]
    paired_calls=[c for c in calls if (call_right,float(c.strike)+width) in by_key]
    if not paired_puts or not paired_calls:return None
    put=min(paired_puts,key=lambda c:(abs(float(c.greeks.delta)+put_target),float(c.strike)))
    call=min(paired_calls,key=lambda c:(abs(float(c.greeks.delta)-call_target),float(c.strike)))
    return put,call,by_key[put_right,float(put.strike)-width],by_key[call_right,float(call.strike)+width]
