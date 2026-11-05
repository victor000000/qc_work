"""Pure calculations shared by the cloud algorithm and local regression tests."""
import math


def iv_entry_rejection(rank, minimum):
    """None disables the IV gate, including its history prerequisite."""
    if minimum is None:
        return None
    if rank is None or not math.isfinite(rank):
        return 'ivr_unavailable'
    return 'ivr_below_threshold' if rank < minimum else None


def iv_rank(current, previous, required=252):
    if len(previous) < required:
        return None
    low, high = min(previous), max(previous)
    if not math.isfinite(current) or current <= 0 or high <= low:
        return None
    return max(0.0, min(100.0, 100.0 * (current - low) / (high - low)))


def correlation(a, b):
    dates = sorted(set(a) & set(b))[-60:]
    if len(dates) < 40:
        return None
    x, y = [a[d] for d in dates], [b[d] for d in dates]
    xm, ym = sum(x) / len(x), sum(y) / len(y)
    numerator = sum((u - xm) * (v - ym) for u, v in zip(x, y))
    denominator = math.sqrt(sum((u - xm)**2 for u in x) * sum((v - ym)**2 for v in y))
    return numerator / denominator if denominator > 0 else None


def close_reason(cashflow, fees, close_cost, initial_credit, dte, final_day=False, stop_multiple=2.0):
    if final_day:
        return 'END'
    if dte <= 21:
        return 'TIME'
    pnl = cashflow - fees - close_cost
    if pnl >= 0.5 * initial_credit:
        return 'PROFIT'
    if pnl <= -stop_multiple * initial_credit:
        return 'STOP'
    return None


def return_features(returns, lookback=20):
    """Trailing snapshot-return RV and scaled log-price displacement, using past data only."""
    if len(returns) < lookback:
        return None, None
    values = list(returns)[-lookback:]
    if any(not math.isfinite(r) or r <= -1 for r in values):
        return None, None
    mean = sum(values) / len(values)
    variance = sum((r - mean)**2 for r in values) / (len(values) - 1)
    if variance <= 0:
        return None, None
    rv = math.sqrt(variance * 252)
    trend_z = sum(math.log1p(r) for r in values) / (rv * math.sqrt(lookback / 252))
    return rv, trend_z


def entry_filter_reason(iv, rv, trend_z, min_iv_rv=None, max_trend_z=None):
    if min_iv_rv is not None:
        if iv is None or rv is None or rv <= 0 or iv / rv < min_iv_rv:
            return 'premium_rejected'
    if max_trend_z is not None:
        if trend_z is None or abs(trend_z) > max_trend_z:
            return 'trend_rejected'
    return None


def roll_side(put_delta, call_delta, threshold=0.20):
    net_delta = -put_delta - call_delta
    if net_delta <= -threshold:
        return 'put'
    if net_delta >= threshold:
        return 'call'
    return None
