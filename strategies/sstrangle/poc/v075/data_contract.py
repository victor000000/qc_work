"""Draft 0.7.5 admission and capacity primitives; no orders or ingestion."""
from datetime import datetime, timedelta
import math


def utc_clock(value):
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Clocks must be timezone-aware datetimes')
    return value


def quote_rejections(row, decision_at, max_age_seconds=120):
    """Strict execution-input checks, stronger than native QuoteBar cache age.

    An empty list only admits this quote's data fields. It does not establish
    contract eligibility, multi-leg synchronization, liquidity or a fill.
    """
    decision_at = utc_clock(decision_at)
    if decision_at is None or max_age_seconds <= 0:
        raise ValueError('Decision and positive age bound required')
    reasons = []
    clocks = {k: utc_clock(row.get(k)) for k in ('interval_ts', 'quote_ts', 'available_at')}
    for key, value in clocks.items():
        if value is None:
            reasons.append('unknown_' + key)
        elif value >= decision_at:
            reasons.append('not_prior_' + key)
    for key in ('interval_ts', 'quote_ts'):
        value = clocks[key]
        if value is not None and (decision_at-value).total_seconds() > max_age_seconds:
            reasons.append('stale_' + key)
    if clocks['quote_ts'] is not None and clocks['interval_ts'] is not None:
        if clocks['quote_ts'] > clocks['interval_ts']:
            reasons.append('quote_after_snapshot')
    if clocks['available_at'] is not None and clocks['interval_ts'] is not None:
        if clocks['available_at'] < clocks['interval_ts']:
            reasons.append('available_before_snapshot')
    bid, ask = row.get('bid'), row.get('ask')
    valid = lambda v: isinstance(v, (int, float)) and math.isfinite(v)
    if not valid(bid) or not valid(ask) or bid <= 0 or ask < bid:
        reasons.append('invalid_market')
    if any(not valid(row.get(k)) or row[k] <= 0 for k in ('bid_size', 'ask_size')):
        reasons.append('missing_executable_size')
    if row.get('quote_type') != 'NBBO':
        reasons.append('not_nbbo')
    if row.get('is_fill_forward', False):
        reasons.append('fill_forward')
    return reasons


def package_rejections(rows, decision_at, max_skew_seconds=30, **kwargs):
    if not rows:
        return ['empty_package']
    if max_skew_seconds < 0:
        raise ValueError('Nonnegative skew bound required')
    reasons = [f'leg{i}:{r}' for i, row in enumerate(rows)
               for r in quote_rejections(row, decision_at, **kwargs)]
    clocks = [utc_clock(r.get('quote_ts')) for r in rows]
    if all(c is not None for c in clocks):
        if (max(clocks)-min(clocks)).total_seconds() > max_skew_seconds:
            reasons.append('cross_leg_skew')
    return reasons


def entry_grid(session_open, session_close):
    """Caller supplies authoritative exchange session boundaries, including DST."""
    session_open, session_close = utc_clock(session_open), utc_clock(session_close)
    if session_open is None or session_close is None or session_close <= session_open:
        raise ValueError('Valid exchange session required')
    slots = [session_open+timedelta(minutes=5)]
    t = session_open+timedelta(minutes=30)
    while t < session_close:
        slots.append(t)
        t += timedelta(minutes=30)
    return [t for t in slots if t < session_close]


def storage_plan(contract_sessions, minutes, bytes_per_row=(150, 300)):
    """Inclusive RTH snapshots; conservative full sessions, decimal GB.

    Byte range is a planning allowance for raw + indexed DB + one Parquet copy
    and quote/Greeks data, not a measured populated-Greeks footprint.
    """
    if contract_sessions < 0 or minutes not in (1, 5, 15, 30):
        raise ValueError('Nonnegative scope and supported frequency required')
    if len(bytes_per_row) != 2 or not 0 < bytes_per_row[0] <= bytes_per_row[1]:
        raise ValueError('Ordered positive byte bounds required')
    rows = contract_sessions * (390 // minutes + 1)
    return {'rows': rows, 'GB': [rows*b/1e9 for b in bytes_per_row]}
