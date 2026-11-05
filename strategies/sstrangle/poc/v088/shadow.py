"""As-of features and optional candidate alignment; frozen decisions remain unchanged."""
from copy import deepcopy
from math import log, isfinite
from zoneinfo import ZoneInfo
from .axis import utc


def features(bars, decision_at):
    deadline = utc(decision_at)
    day = deadline.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    eligible = [b for b in bars if b['is_complete'] and b['session'] == day
                and utc(b['available_at']) < deadline and utc(b['end_event_time']) < deadline]
    eligible.sort(key=lambda b: (utc(b['end_event_time']), b['sequence']))
    if not eligible:
        return {'status': 'no_completed_axis'}
    last = eligible[-1]
    age = (deadline-utc(last['end_event_time'])).total_seconds()
    if age > 1800:
        return {'status': 'stale_axis', 'axis_age_seconds': age}
    segment = [b for b in eligible if b['segment_id'] == last['segment_id']]
    result = dict(status='ready', last_axis_id=last['axis_id'], axis_age_seconds=age,
                  last_return=log(last['close']/last['open']), duration_seconds=last['duration_seconds'],
                  activity_intensity=last['activity']/last['duration_seconds'],
                  minutes_to_expiry=None, quality_flags=last['quality_flags'])
    for count in (3, 6):
        tail = segment[-count:]
        result[f'return_{count}'] = log(tail[-1]['close']/tail[0]['open']) if len(tail) == count else None
        result[f'variation_{count}'] = sum(log(b['close']/b['open'])**2 for b in tail) if len(tail) == count else None
    return result


def attach_shadow(decisions, bars):
    """Sidecar keyed by immutable decision position; never mutate or gate decisions."""
    return [dict(decision_index=i, decision=deepcopy(d), axis=features(bars, d['decision_at']))
            for i, d in enumerate(decisions)]


def align_options(rows, decision_at, mode='strict'):
    """Return eligible chain and all exclusion reasons. Input is a normalized 1m quote/Greek join."""
    if mode not in ('strict', 'sampled'):
        raise ValueError('invalid timing mode')
    deadline = utc(decision_at)
    day = deadline.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    candidates, rejected = {}, []
    for row in rows:
        reason = None
        try:
            observed = utc(row['observed_at'])
            if row['frequency_seconds'] != 60 or row.get('greek_frequency_seconds') != 60:
                reason = 'not_native_one_minute'
            elif row['expiry'] != day or row.get('root') != 'SPXW' or not row.get('listed_asof', False):
                reason = 'ineligible_contract'
            elif observed >= deadline or (deadline-observed).total_seconds() > 120:
                reason = 'snapshot_not_predecision_or_stale'
            elif not row.get('source_row_id') or row.get('is_fill_forward', False):
                reason = 'unverifiable_or_fill_forward'
            elif not all(isfinite(float(row[k])) for k in ('bid', 'ask', 'delta', 'spot')):
                reason = 'invalid_numeric'
            elif not (0 <= row['bid'] <= row['ask'] and row['ask'] > 0 and row['spot'] > 0):
                reason = 'invalid_market'
            elif mode == 'strict' and not row.get('greek_model_accepted', False):
                reason = 'unaccepted_greek_model'
            elif mode == 'strict':
                fields = ('quote_ts', 'available_at', 'greek_available_at', 'greek_asof', 'greek_input_at')
                if any(row.get(k) is None for k in fields):
                    reason = 'unknown_clocks'
                else:
                    q, av, gav, ga, gi = (utc(row[k]) for k in fields)
                    if not (q <= observed <= av <= deadline and q <= av and gi <= ga <= gav <= deadline):
                        reason = 'invalid_clock_order'
                    elif (deadline-q).total_seconds() > 120 or (deadline-ga).total_seconds() > 120:
                        reason = 'stale_quote_or_greek'
            if reason is None:
                key = row['contract_id']
                if key not in candidates or observed > utc(candidates[key]['observed_at']):
                    candidates[key] = dict(row, timing_mode=mode)
                elif observed == utc(candidates[key]['observed_at']):
                    raise ValueError('duplicate contract snapshot requires explicit source resolution')
        except (KeyError, TypeError) as exc:
            reason = 'missing_field:' + str(exc)
        if reason:
            rejected.append(dict(source_row_id=row.get('source_row_id'), contract_id=row.get('contract_id'), reason=reason))
    return [candidates[k] for k in sorted(candidates)], rejected


def selected_leg_clock_gate(selected, mode='strict'):
    if not selected:
        return False
    if mode == 'sampled':
        return True  # Diagnostic only; no claim about actual quote-event skew.
    if any(r.get('quote_ts') is None for r in selected):
        return False
    clocks = [utc(r['quote_ts']) for r in selected]
    return (max(clocks)-min(clocks)).total_seconds() <= 30


class ShadowAdapter:
    """QC/local seam: caller feeds completed underlying bars, then invokes the existing selector.

    Does not submit orders or override portfolio models. QC bars with simulated availability
    must use sampled mode; real historical latency is not inferred from engine time.
    """
    def __init__(self, axis):
        self.axis = axis
        self.sidecar = []

    def decide(self, decision_at, existing_decision, *args, **kwargs):
        value = existing_decision(*args, **kwargs)
        self.sidecar.append(dict(decision_at=decision_at, axis=features(self.axis.bars, decision_at)))
        return value
