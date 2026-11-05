"""Causal features, latest-known option state, and isolated observational hooks."""
from copy import deepcopy
from math import log, isfinite
from zoneinfo import ZoneInfo
from .axis import utc, Axis


def features(state, decision_at, events=None):
    deadline = utc(decision_at)
    day = deadline.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    bars = state.bars if isinstance(state, Axis) else state
    events = state.events if isinstance(state, Axis) else (events or [])
    known = [e for e in events if e['session']==day and utc(e['known_at']) < deadline]
    segment_floor = max((e['segment_id'] for e in known), default=0)
    eligible = [b for b in bars if b['is_complete'] and b['session']==day
                and b['segment_id'] >= segment_floor
                and utc(b['available_at']) < deadline and utc(b['end_event_time']) < deadline]
    eligible.sort(key=lambda b:(utc(b['end_event_time']),b['sequence']))
    if not eligible:
        return {'status':'gap_waiting_for_complete_axis' if known else 'no_completed_axis'}
    last = eligible[-1]
    age = (deadline-utc(last['end_event_time'])).total_seconds()
    if age > 1800:
        return dict(status='stale_axis', axis_age_seconds=age)
    segment = [b for b in eligible if b['segment_id']==last['segment_id']]
    anchor = last['start_reference_close']
    result = dict(status='ready',last_axis_id=last['axis_id'],axis_age_seconds=age,
                  last_return=log(last['close']/anchor) if anchor is not None else None,
                  open_to_close_return=log(last['close']/last['open']),
                  duration_seconds=last['duration_seconds'],
                  activity_intensity=last['activity']/last['duration_seconds'],
                  minutes_to_expiry=max(0.,(utc(last['expiry_at'])-deadline).total_seconds()/60),
                  quality_flags=last['quality_flags'])
    for count in (3,6):
        tail=segment[-count:]
        full=len(tail)==count
        reference=tail[0]['start_reference_close'] if full else None
        result[f'return_{count}']=log(tail[-1]['close']/reference) if reference is not None else None
        result[f'minute_variation_{count}']=sum(b['minute_variation'] for b in tail) if full else None
        result[f'event_return_squared_sum_{count}']=(sum(log(b['close']/b['start_reference_close'])**2 for b in tail)
            if full and all(b['start_reference_close'] is not None for b in tail) else None)
    return result


def attach_shadow(decisions, state):
    return [dict(decision_index=i,decision=deepcopy(d),axis=features(state,d['decision_at'])) for i,d in enumerate(decisions)]


def _clock_reason(row, deadline, observed, mode):
    fields=('quote_ts','available_at','greek_available_at','greek_asof','greek_input_at')
    clocks={k:utc(row[k]) for k in fields if row.get(k) is not None}
    if any(t >= deadline for t in clocks.values()):return 'known_clock_not_predecision'
    q,av,gav,ga,gi=(clocks.get(k) for k in fields)
    pairs=((q,observed),(observed,av),(gi,ga),(ga,gav))
    if any(a is not None and b is not None and a>b for a,b in pairs):return 'invalid_clock_order'
    if any(t is not None and (deadline-t).total_seconds()>120 for t in (q,ga,gi)):
        return 'stale_quote_or_greek_input'
    if mode=='strict':
        if not row.get('greek_model_accepted',False):return 'unaccepted_greek_model'
        if len(clocks)!=len(fields):return 'unknown_clocks'
    return None


def align_options(rows, decision_at, mode='strict'):
    if mode not in ('strict','sampled'):raise ValueError('invalid timing mode')
    deadline=utc(decision_at);day=deadline.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    latest={};rejected=[];conflicts=set()
    def reject(row,reason):
        rejected.append(dict(source_row_id=row.get('source_row_id'),contract_id=row.get('contract_id'),reason=reason))
    # Resolve the newest known observation before testing market quality. A conflicting
    # newest tie blocks this contract only; a strictly newer state can recover it.
    for row in rows:
        try:
            observed=utc(row['observed_at']);key=row['contract_id']
            if observed>=deadline:
                reject(row,'snapshot_not_predecision_or_stale');continue
            if any(row.get(k) is not None and utc(row[k])>=deadline for k in ('available_at','greek_available_at')):
                reject(row,'known_clock_not_predecision');continue
            if key not in latest or observed>utc(latest[key]['observed_at']):
                if key in latest:reject(latest[key],'superseded')
                latest[key]=row;conflicts.discard(key)
            elif observed==utc(latest[key]['observed_at']):
                if row != latest[key]:
                    conflicts.add(key)
                    reject(row,'conflicting_duplicate_contract_snapshot')
                else:reject(row,'identical_duplicate')
            else:reject(row,'superseded')
        except (KeyError,TypeError,ValueError,AttributeError) as exc:
            reject(row,'invalid_field:'+str(exc))
    for key in sorted(conflicts):
        reject(latest.pop(key),'conflicting_duplicate_contract_snapshot')
    candidates=[]
    for key,row in sorted(latest.items()):
        reason=None
        try:
            observed=utc(row['observed_at'])
            if row.get('frequency_seconds')!=60 or row.get('greek_frequency_seconds')!=60:reason='not_native_one_minute'
            elif row.get('expiry')!=day or row.get('root')!='SPXW' or not row.get('listed_asof',False):reason='ineligible_contract'
            elif (deadline-observed).total_seconds()>120:reason='snapshot_not_predecision_or_stale'
            elif not row.get('source_row_id') or row.get('is_fill_forward',False):reason='unverifiable_or_fill_forward'
            elif not all(isfinite(float(row[k])) for k in ('bid','ask','delta','spot')):reason='invalid_numeric'
            elif not (0<=row['bid']<=row['ask'] and row['ask']>0 and row['spot']>0 and abs(row['delta'])<=1):reason='invalid_market'
            else:reason=_clock_reason(row,deadline,observed,mode)
            if reason is None:candidates.append(dict(row,timing_mode=mode))
        except (KeyError,TypeError,ValueError) as exc:reason='invalid_field:'+str(exc)
        if reason:reject(row,reason)
    return candidates,rejected


def selected_leg_clock_gate(selected, mode='strict'):
    if not selected:return False
    known=[utc(r['quote_ts']) for r in selected if r.get('quote_ts') is not None]
    if mode=='strict' and len(known)!=len(selected):return False
    return not known or (max(known)-min(known)).total_seconds()<=30


def select_package(rows, decision_at, strategy='condor', mode='strict'):
    """Research selector; never submits orders. Gates the actually selected package."""
    from strategies.sstrangle.poc.v087.local_engine import Leg, select
    chain,excluded=align_options(rows,decision_at,mode)
    legs,status=select([Leg(r['contract_id'],r['strike'],r['right'],r['delta'],r['bid'],r['ask'],r['spot']) for r in chain],strategy)
    identities={leg.identity for leg,q in legs} if legs else set()
    selected=[r for r in chain if r['contract_id'] in identities]
    if legs and not selected_leg_clock_gate(selected,mode):legs,status=None,'selected_leg_clock_skew'
    return legs,status,chain,excluded


class ShadowAdapter:
    def __init__(self,axis):
        self.axis=axis;self.sidecar=[];self.valid=True

    def decide(self,decision_at,existing_decision,*args,**kwargs):
        value=existing_decision(*args,**kwargs)  # Native errors deliberately propagate.
        try:result=features(self.axis,decision_at)
        except Exception as exc:
            self.valid=False;result=dict(status='shadow_error',error=type(exc).__name__)
        self.sidecar.append(dict(decision_at=decision_at,axis=result))
        self.sidecar=self.sidecar[-128:]
        return value
