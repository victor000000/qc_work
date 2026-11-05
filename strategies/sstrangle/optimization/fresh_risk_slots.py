"""Consume a per-position risk interval only after a genuine risk evaluation.

Callers pass the algorithm UTC clock. A stale or closed-market attempt does not
consume the interval, so a later fresh paired quote can be evaluated promptly.
This scheduler never changes quotes, thresholds, order types or fill prices.
"""
from datetime import datetime


class FreshRiskSlots:
    def __init__(self, interval):
        if type(interval) is not int or interval not in (1, 5, 15, 30):
            raise ValueError('Explicit supported risk interval required')
        self.interval = interval
        self.consumed = {}

    def token(self, utc):
        if not isinstance(utc, datetime):
            raise ValueError('Algorithm UTC datetime required')
        if utc.tzinfo is not None and utc.utcoffset().total_seconds() != 0:
            raise ValueError('Risk scheduler requires UTC, not an exchange-local clock')
        return (utc.toordinal() * 1440 + utc.hour * 60 + utc.minute) // self.interval

    def due(self, key, utc):
        slot = self.token(utc)
        previous = self.consumed.get(key)
        if previous is not None and slot < previous:
            raise ValueError('Risk clock moved backwards')
        return previous != slot

    def complete(self, key, utc):
        if not self.due(key, utc):
            raise ValueError('Risk interval already evaluated for this position')
        self.consumed[key] = self.token(utc)

    def retain(self, active_keys):
        active = set(active_keys)
        self.consumed = {key: slot for key, slot in self.consumed.items() if key in active}
