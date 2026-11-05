"""Point-in-time screen rules for the broad baseline; no LEAN dependencies.

The range formula matches dte_21_screener.compute.iv_rank.range_rank.
IV percentile is retained only as a diagnostic, never as an entry criterion.
"""
from datetime import date, timedelta
import math
from collections import deque


def iv_statistics(observations, as_of, lookback=504, min_points=504):
    """One completed daily IV per date, latest included in the trailing window.

    Do not silently fill missing IV days, pool sources or use future observations.
    Callers maintain one consistent daily ATM-IV series per underlying/root.
    """
    if not 2 <= min_points <= lookback:
        raise ValueError('Require 2 <= min_points <= lookback')
    rows = sorted(observations)
    if len({day for day, _ in rows}) != len(rows):
        raise ValueError('Duplicate IV session')
    if any(day > as_of for day, _ in rows):
        raise ValueError('Future IV observation')
    rows = rows[-lookback:]
    result = dict(ivr=None, ivp=None, samples=len(rows), iv=None,
                  first_day=str(rows[0][0]) if rows else None,
                  last_day=str(rows[-1][0]) if rows else None,
                  iv_low=None, iv_high=None)
    if not rows:
        return result
    values = [value for _, value in rows]
    if any(v is None or not math.isfinite(v) or v <= 0 for v in values):
        return result
    result['iv'] = values[-1]
    if len(rows) < min_points:
        return result
    low, high, current = min(values), max(values), values[-1]
    result.update(iv_low=low, iv_high=high,
                  ivp=100 * sum(v <= current + 1e-12 for v in values) / len(values))
    if high > low:
        result['ivr'] = 100 * (current - low) / (high - low)
    return result


def high_iv_rank(rank, threshold=70):
    return rank is not None and math.isfinite(rank) and rank > threshold


def equity_screen(rows, market_cap):
    """Last 20 completed sessions; unknown capitalization is explicitly retained."""
    if len(rows) < 20:
        return 'price_volume_history', None
    recent = rows[-20:]
    if any(not math.isfinite(p) or not math.isfinite(v) or p <= 0 or v < 0
           for _, p, v in recent):
        return 'price_volume_invalid', None
    return _validated_equity_screen(recent,market_cap)


def _validated_equity_screen(recent,market_cap):
    price = sum(p for _, p, _ in recent) / 20
    volume = sum(v for _, _, v in recent) / 20
    info = dict(avg_price=price, avg_volume=volume,
                volume=recent[-1][2], cap=market_cap,
                cap_known=market_cap is not None and math.isfinite(market_cap) and market_cap > 0)
    if price <= 30:
        return 'price', info
    if volume <= 5_000_000:
        return 'volume', info
    if info['cap_known'] and market_cap <= 1_000_000_000:
        return 'market_cap', info
    return None, info


class EquityScreenWindow:
    """Cache validity only; preserve original floating-point summation order."""
    __slots__=('rows','invalid_flags','invalid_count','above_price','above_volume')
    def __init__(self):
        self.rows=deque(maxlen=20)
        self.invalid_flags=deque(maxlen=20)
        self.invalid_count=0
        self.above_price=0;self.above_volume=0

    def append(self,point):
        _,price,volume=point
        invalid=not (math.isfinite(price) and math.isfinite(volume) and price>0 and volume>=0)
        replaced=self.rows[-1] if self.rows and self.rows[-1][0]==point[0] else (self.rows[0] if len(self.rows)==20 else None)
        if replaced is not None:
            self.above_price-=replaced[1]>30
            self.above_volume-=replaced[2]>5_000_000
        self.above_price+=price>30
        self.above_volume+=volume>5_000_000
        if self.rows and self.rows[-1][0]==point[0]:
            self.invalid_count-=self.invalid_flags[-1]
            self.rows[-1]=point;self.invalid_flags[-1]=invalid
        else:
            if len(self.rows)==20:self.invalid_count-=self.invalid_flags[0]
            self.rows.append(point);self.invalid_flags.append(invalid)
        self.invalid_count+=invalid

    def candidate_info(self,market_cap):
        # Necessary bounds only: if every sample is <= its threshold then
        # the original mean cannot pass. Mixed windows still use exact sums.
        if len(self.rows)<20 or self.invalid_count or not self.above_price or not self.above_volume:
            return None
        if market_cap is not None and math.isfinite(market_cap) and 0<market_cap<=1_000_000_000:
            return None
        reason,info=_validated_equity_screen(list(self.rows),market_cap)
        return info if reason is None else None

    def screen(self,market_cap):
        if len(self.rows)<20:return 'price_volume_history',None
        if self.invalid_count:return 'price_volume_invalid',None
        return _validated_equity_screen(list(self.rows),market_cap)


def ordered_candidates(candidates):
    """User's priority: previous completed underlying session volume, largest first."""
    return sorted(candidates, key=lambda c: (-c['volume'], c['key']))


def available_slots(positions, pending, maximum=13):
    return max(0, maximum - len(set(positions) | set(pending)))


def can_start_batch(positions, pending, exits):
    return not positions and not pending and not exits


def standard_equity_monthly(expiry, third_friday_closed=False):
    first = date(expiry.year,expiry.month,1)
    friday = first+timedelta(days=(4-first.weekday())%7+14)
    return (expiry == friday
            or (expiry == friday+timedelta(days=1) and expiry < date(2015,2,1))
            or (expiry == friday-timedelta(days=1) and third_friday_closed))


def equal_budget_candidates(candidates, existing_count, equity, maximum=13):
    """Largest affordable basket; volume priority within that feasible count.

    Each candidate supplies a conservative one-strangle margin plus fee estimate.
    Existing positions retain their contract counts. Their count still belongs
    in the denominator used for new entries.
    """
    if not math.isfinite(equity) or equity <= 0 or not 0 <= existing_count <= maximum:
        raise ValueError('Invalid equity or existing basket count')
    candidates = ordered_candidates(candidates)
    for count in range(min(maximum, existing_count+len(candidates)), existing_count, -1):
        budget = equity/count
        affordable = [c for c in candidates if math.isfinite(c['unit_cost'])
                      and 0 < c['unit_cost'] <= budget]
        if len(affordable) >= count-existing_count:
            return affordable[:count-existing_count], count
    return [], existing_count


def equal_budget_quantity(equity, count, unit_cost, available_margin):
    """Integer lots from the 1/x equity budget, constrained by remaining margin."""
    if (not 1 <= count <= 13 or any(not math.isfinite(v) for v in
            (equity,unit_cost,available_margin)) or equity <= 0 or unit_cost <= 0):
        raise ValueError('Invalid equal-budget sizing inputs')
    return max(0, math.floor(min(equity/count,max(0,available_margin))/unit_cost))


def monthly_expiry(expiries, today, future=False):
    """First listed standard monthly expiry >=35 calendar DTE.

    US equity monthlies historically expire Saturday (now Friday), with Thursday
    when Friday is a holiday. Futures use their product's listed standard dates.
    """
    eligible = []
    for expiry in set(expiries):
        if (expiry - today).days < 35 or (expiry - today).days > 95:
            continue
        if not future:
            first = date(expiry.year, expiry.month, 1)
            friday = first + timedelta(days=(4-first.weekday()) % 7 + 14)
            if expiry not in (friday - timedelta(days=1), friday, friday + timedelta(days=1)):
                continue
        eligible.append(expiry)
    return min(eligible) if eligible else None


def earnings_veto(events, today, expiry):
    """Events are (known_as_of, report_date); future announcements cannot veto."""
    return any(known <= today <= report <= expiry for known, report in events)


def strangle_reserve(spot, put_strike, call_strike, credit, multiplier):
    """Screener's equity Reg-T estimate, also used as a conservative FOP size cap.

    Actual LEAN security buying power is checked separately for every leg.
    """
    call = max(.2 * spot - max(call_strike - spot, 0), .1 * spot)
    put = max(.2 * spot - max(spot - put_strike, 0), .1 * put_strike)
    return (max(call, put) + credit) * multiplier


def black76_price_delta(forward, strike, years, volatility, rate, put=False):
    """European futures-option approximation; inputs must share quotation units."""
    if min(forward, strike, years, volatility) <= 0:
        raise ValueError('Black-76 requires positive forward, strike, time and IV')
    root = volatility * math.sqrt(years)
    d1 = math.log(forward / strike) / root + root / 2
    d2 = d1 - root
    cdf = lambda x: .5 * (1 + math.erf(x / math.sqrt(2)))
    discount = math.exp(-rate * years)
    if put:
        return discount * (strike*cdf(-d2) - forward*cdf(-d1)), -discount*cdf(-d1)
    return discount * (forward*cdf(d1) - strike*cdf(d2)), discount*cdf(d1)


def black76_iv_delta(price, forward, strike, years, rate, put=False):
    """Reject invalid/arbitrage-inconsistent prices, never turn zero IV into a signal."""
    values = [price, forward, strike, years, rate]
    if any(v is None or not math.isfinite(v) for v in values) or min(values[:4]) <= 0:
        return None, None
    discount = math.exp(-rate*years)
    intrinsic = discount * max(strike-forward if put else forward-strike, 0)
    upper = discount * (strike if put else forward)
    if not intrinsic + 1e-10 < price < upper:
        return None, None
    # Preserve the same 50 bisections and arithmetic order. During the
    # search only price is needed; delta and invariant terms were needlessly
    # recalculated for every trial volatility.
    sqrt_years, log_moneyness, sqrt_two = math.sqrt(years), math.log(forward/strike), math.sqrt(2)
    def trial_price(volatility):
        root = volatility * sqrt_years
        d1 = log_moneyness / root + root / 2
        d2 = d1 - root
        if put:
            return discount * (strike*(.5*(1+math.erf(-d2/sqrt_two)))
                - forward*(.5*(1+math.erf(-d1/sqrt_two))))
        return discount * (forward*(.5*(1+math.erf(d1/sqrt_two)))
            - strike*(.5*(1+math.erf(d2/sqrt_two))))
    low, high = .00001, 5.0
    if trial_price(high) < price:
        return None, None
    for _ in range(50):
        mid = (low+high)/2
        if trial_price(mid) < price:
            low = mid
        else:
            high = mid
    iv = (low+high)/2
    return iv, black76_price_delta(forward, strike, years, iv, rate, put)[1]
