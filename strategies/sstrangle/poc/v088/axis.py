"""Pure streaming engine. No orders, capital changes, full-array fitting or I/O."""
from datetime import datetime, timedelta, timezone
from statistics import median
import hashlib
import json
import math


def utc(value):
    t = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    if t.tzinfo is None:
        raise ValueError('timezone required')
    return t.astimezone(timezone.utc)


def stamp(t):
    return utc(t).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class Axis:
    VERSION = '0.8.8'

    def __init__(self, recipe='spx_variation', mode='strict', release='fixture', lookback=20, target=26):
        if recipe not in ('spx_variation', 'spy_dollar', 'spy_close_volume', 'time_control'):
            raise ValueError('unknown recipe')
        if mode not in ('strict', 'sampled') or lookback < 1 or target <= 0:
            raise ValueError('invalid configuration')
        self.config = dict(version=self.VERSION, recipe=recipe, mode=mode, release=release,
                           lookback=lookback, target=target)
        self.recipe_hash = digest(self.config)
        self.history = []
        self.session = None
        self.bars = []
        self.exclusions = []

    def seed(self, history):
        if self.session is not None or self.history:
            raise ValueError('seed only once before replay')
        previous = None
        for row in history:
            if not row['complete'] or not math.isfinite(row['activity']) or row['activity'] < 0:
                raise ValueError('invalid calibration session')
            if previous is not None and row['session'] <= previous:
                raise ValueError('unordered or duplicate calibration')
            utc(row['available_at'])
            self.history.append(dict(row))
            previous = row['session']

    def begin(self, session, opened, closed):
        if self.session is not None:
            raise ValueError('finish previous session')
        op, cl = utc(opened), utc(closed)
        if cl <= op or (cl-op).total_seconds() % 60:
            raise ValueError('invalid calendar interval')
        if self.history and session <= self.history[-1]['session']:
            raise ValueError('session must follow calibration history')
        eligible = [h for h in self.history if h['session'] < session and utc(h['available_at']) < op]
        tail = eligible[-self.config['lookback']:]
        threshold = median(h['activity'] for h in tail)/self.config['target'] if len(tail) == self.config['lookback'] else None
        if threshold is not None and threshold <= 0:
            threshold = None
        self.session = dict(session=session, opened=stamp(op), closed=stamp(cl), threshold=threshold,
                            threshold_source_end=tail[-1]['session'] if tail else None,
                            previous_end=stamp(op), previous_available=stamp(op), previous_close=None,
                            count=0, total=0., segment=0, sequence=0, complete=True, partial=None)
        return threshold

    def _discard(self, reason):
        s = self.session
        if s['partial']:
            self._emit(False, reason)
        s['previous_close'] = None
        s['segment'] += 1
        s['complete'] = False
        self.exclusions.append(dict(session=s['session'], reason=reason))

    def update(self, row):
        s = self.session
        if s is None:
            raise ValueError('begin session first')
        end, start = utc(row['end']), utc(row['start'])
        if row.get('frequency_seconds') != 60 or end-start != timedelta(minutes=1):
            raise ValueError('native one-minute bars required')
        if row['session'] != s['session'] or start < utc(s['opened']) or end > utc(s['closed']):
            raise ValueError('outside declared session')
        if end <= utc(s['previous_end']):
            raise ValueError('duplicate, revision or late event')
        raw_available = row.get('available_at')
        if raw_available is None and self.config['mode'] == 'strict':
            raise ValueError('historical availability missing')
        available = utc(raw_available) if raw_available else end
        if available < end or available < utc(s['previous_available']):
            raise ValueError('invalid or reordered availability')
        expected_symbol = 'SPY' if self.config['recipe'].startswith('spy_') else 'SPX'
        if row['symbol'] != expected_symbol:
            raise ValueError('wrong underlying for recipe')
        prices = [float(row[k]) for k in ('open', 'high', 'low', 'close')]
        if not all(math.isfinite(v) and v > 0 for v in prices):
            raise ValueError('invalid price')
        op, hi, lo, close = prices
        if lo > min(op, close) or hi < max(op, close) or lo > hi:
            raise ValueError('invalid OHLC')
        if not row.get('source_row_id') or row.get('is_fill_forward', False):
            raise ValueError('provenance required; fill-forward prohibited')
        recipe = self.config['recipe']
        if recipe == 'spy_dollar':
            activity = float(row['trade_notional'])
        elif recipe == 'spy_close_volume':
            activity = close*float(row['volume'])
        elif recipe == 'time_control':
            activity = 1.
        else:
            activity = 0.  # Computed after gap reset.
        if not math.isfinite(activity) or activity < 0:
            raise ValueError('invalid activity')
        if start != utc(s['previous_end']):
            self._discard('missing_minute')
        if recipe == 'spx_variation' and s['previous_close'] is not None:
            activity = math.log(close/s['previous_close'])**2
        s['count'] += 1
        s['total'] += activity
        s['previous_close'], s['previous_end'], s['previous_available'] = close, stamp(end), stamp(available)
        # Keep full session activity during warmup, but never emit tradable information bars.
        if recipe != 'time_control' and s['threshold'] is None:
            return None
        if s['partial'] is None:
            s['partial'] = dict(start_event_time=stamp(start), end_event_time=stamp(end), available_at=stamp(available),
                                open=op, high=hi, low=lo, close=close, activity=0., input_minutes=0, source_row_ids=[])
        p = s['partial']
        p.update(end_event_time=stamp(end), available_at=stamp(available), high=max(p['high'], hi),
                 low=min(p['low'], lo), close=close)
        p['activity'] += activity
        p['input_minutes'] += 1
        p['source_row_ids'].append(row['source_row_id'])
        if recipe == 'time_control':
            offset = int((end-utc(s['opened'])).total_seconds()/60)
            # A gap fragment cannot masquerade as a complete anchored time bar.
            if offset % 15 == 0:
                return self._emit(p['input_minutes'] == 15, 'time_boundary')
        elif p['activity'] >= s['threshold']:
            return self._emit(True, 'threshold')
        return None

    def _emit(self, complete, reason):
        s, cfg = self.session, self.config
        p = s['partial']
        s['sequence'] += 1
        row = dict(p, session=s['session'], segment_id=s['segment'], sequence=s['sequence'],
                   recipe_hash=self.recipe_hash, data_release=cfg['release'], threshold=s['threshold'],
                   threshold_source_end=s['threshold_source_end'], is_complete=complete, reason=reason,
                   duration_seconds=(utc(p['end_event_time'])-utc(p['start_event_time'])).total_seconds(),
                   overshoot=max(0., p['activity']-(s['threshold'] or 15)),
                   quality_flags=['assumed_minute_availability'] if cfg['mode'] == 'sampled' else [])
        row['axis_id'] = digest(row)
        self.bars.append(row)
        s['partial'] = None
        return row

    def finish(self):
        s = self.session
        if s is None:
            raise ValueError('no active session')
        if s['partial']:
            self._emit(False, 'session_tail')
        expected = int((utc(s['closed'])-utc(s['opened'])).total_seconds()/60)
        complete = s['complete'] and s['count'] == expected and s['previous_end'] == s['closed']
        summary = dict(session=s['session'], activity=s['total'], complete=complete,
                       available_at=s['previous_available'], expected_minutes=expected, observed_minutes=s['count'])
        if complete:
            self.history.append(summary)
        self.session = None
        return summary

    def checkpoint(self):
        return json.loads(json.dumps(self.__dict__, allow_nan=False))

    @classmethod
    def restore(cls, state):
        obj = cls()
        obj.__dict__.update(json.loads(json.dumps(state)))
        if obj.config['version'] != cls.VERSION or digest(obj.config) != obj.recipe_hash:
            raise ValueError('checkpoint recipe mismatch')
        return obj
