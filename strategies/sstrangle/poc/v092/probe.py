"""Bounded observations in the algorithm clock; no inferred native scan order."""
from copy import deepcopy
from datetime import datetime
import re
try:
    from .margin_diagnostic import record_margin_state
except ImportError:
    from margin_diagnostic_v092 import record_margin_state


def validate_plan(plan):
    if not isinstance(plan, list) or not 1 <= len(plan) <= 4:
        raise ValueError('plan requires 1–4 checkpoints')
    seen = set()
    for row in plan:
        if not isinstance(row, dict) or set(row) != {'prefix', 'phase', 'start', 'end'}:
            raise ValueError('checkpoint fields must be prefix, phase, start, end')
        prefix = row['prefix']
        if not isinstance(prefix, str) or not re.fullmatch(r'M[A-Z0-9]{1,7}', prefix) or prefix in seen:
            raise ValueError('invalid or duplicate prefix')
        seen.add(prefix)
        if row['phase'] not in ('on_data', 'on_order_event', 'on_margin_call'):
            raise ValueError('unsupported phase')
        if not all(isinstance(row[key], str) for key in ('start', 'end')):
            raise ValueError('checkpoint times must be ISO strings')
        start, end = datetime.fromisoformat(row['start']), datetime.fromisoformat(row['end'])
        if start.tzinfo or end.tzinfo or not 0 <= (end-start).total_seconds() <= 86400:
            raise ValueError('use ordered naive algorithm-clock windows up to 24 hours')
    return plan


class MarginProbe:
    def __init__(self, plan):
        self.plan = deepcopy(validate_plan(plan))

    def observe(self, algorithm, phase):
        # All diagnostic failures are isolated from native execution.
        for row in self.plan:
            try:
                if row['phase'] == phase and datetime.fromisoformat(row['start']) <= algorithm.time <= datetime.fromisoformat(row['end']):
                    record_margin_state(algorithm, row['prefix'], once=True, phase=phase)
            except Exception:
                pass  # Missing/partial receipt is not valid evidence; allow retry.
