"""Pure streaming engine. No orders, capital changes, full-array fitting or I/O."""
from datetime import datetime, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo
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
    VERSION = '0.8.9'

    def __init__(self, recipe='spx_variation', mode='strict', release='fixture', lookback=20, target=26, retention=None, calendar_hash=None):
        if recipe not in ('spx_variation', 'spy_dollar', 'spy_close_volume', 'time_control'):
            raise ValueError('unknown recipe')
        if mode not in ('strict', 'sampled') or lookback < 1 or target <= 0:
            raise ValueError('invalid configuration')
        self.config = dict(version=self.VERSION, recipe=recipe, mode=mode, release=release,
                           lookback=lookback, target=target, retention=retention, calendar_hash=calendar_hash)
        self.recipe_hash = digest(self.config)
        self.history = []
        self.session = None
        self.bars = []
        self.exclusions = []
        self.events = []
        self.source_cursor = None
        if retention is not None and retention < 8:
            raise ValueError("retention must preserve feature windows")

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
        if (session != op.astimezone(ZoneInfo('America/New_York')).date().isoformat()
                or session != cl.astimezone(ZoneInfo('America/New_York')).date().isoformat()
                or cl <= op or (cl-op).total_seconds() % 60):
            raise ValueError('invalid calendar interval')
        if self.history and session <= self.history[-1]['session']:
            raise ValueError('session must follow calibration history')
        eligible = [h for h in self.history if h['session'] < session and utc(h['available_at']) < op]
        tail = eligible[-self.config['lookback']:]
        threshold = median(h['activity'] for h in tail)/self.config['target'] if len(tail) == self.config['lookback'] else None
        if threshold is not None and threshold <= 0:
            threshold = None
        if self.config['recipe'] == 'time_control':
            threshold = 15.
        self.session = dict(session=session, opened=stamp(op), closed=stamp(cl), threshold=threshold,
                            threshold_source_end=tail[-1]['session'] if tail else None,
                            previous_end=stamp(op), previous_available=stamp(op), previous_close=None,
                            count=0, total=0., segment=0, sequence=0, complete=True, partial=None, last_bar_close=None)
        return threshold

    def _discard(self, reason, known_at):
        s = self.session
        if s['partial']:
            self._emit(False, reason)
        s['previous_close'] = None
        s['last_bar_close'] = None
        s['segment'] += 1
        s['complete'] = False
        event = dict(session=s['session'], segment_id=s['segment'], known_at=stamp(known_at), reason=reason)
        self.exclusions.append(event)
        self.events.append(event)

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
            self._discard('missing_minute', available)
        if recipe == 'spx_variation' and s['previous_close'] is not None:
            activity = math.log(close/s['previous_close'])**2
        minute_rv = math.log(close/s['previous_close'])**2 if s['previous_close'] is not None else 0.
        self.source_cursor = dict(source_row_id=row['source_row_id'], end=stamp(end), available_at=stamp(available))
        s['count'] += 1
        s['total'] += activity
        s['previous_close'], s['previous_end'], s['previous_available'] = close, stamp(end), stamp(available)
        # Keep full session activity during warmup, but never emit tradable information bars.
        if recipe != 'time_control' and s['threshold'] is None:
            return None
        if s['partial'] is None:
            s['partial'] = dict(start_event_time=stamp(start), end_event_time=stamp(end), available_at=stamp(available),
                                open=op, high=hi, low=lo, close=close, start_reference_close=s['last_bar_close'], minute_variation=0., activity=0., input_minutes=0, source_row_ids=[])
        p = s['partial']
        p.update(end_event_time=stamp(end), available_at=stamp(available), high=max(p['high'], hi),
                 low=min(p['low'], lo), close=close)
        p['activity'] += activity
        p['minute_variation'] += minute_rv
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
                   threshold_unit=('minutes' if cfg['recipe']=='time_control' else 'USD' if cfg['recipe'].startswith('spy_') else 'squared_log_return'),
                   expiry_at=s['closed'], threshold_source_end=s['threshold_source_end'], is_complete=complete, reason=reason,
                   duration_seconds=(utc(p['end_event_time'])-utc(p['start_event_time'])).total_seconds(),
                   overshoot=max(0., p['activity']-(s['threshold'] or 15)),
                   quality_flags=['assumed_minute_availability'] if cfg['mode'] == 'sampled' else [])
        row['axis_id'] = digest(row)
        self.bars.append(row)
        if complete:
            s['last_bar_close'] = row['close']
        s['partial'] = None
        if cfg['retention'] is not None:
            self.bars = self.bars[-cfg['retention']:]
            self.events = self.events[-cfg['retention']:]
            self.exclusions = self.exclusions[-cfg['retention']:]
        return row

    def finish(self):
        s = self.session
        if s is None:
            raise ValueError('no active session')
        if s['previous_end'] != s['closed']:
            self._discard('missing_final_minute', max(utc(s['closed']), utc(s['previous_available'])))
        if s['partial']:
            self._emit(False, 'session_tail')
        expected = int((utc(s['closed'])-utc(s['opened'])).total_seconds()/60)
        complete = s['complete'] and s['count'] == expected and s['previous_end'] == s['closed']
        summary = dict(session=s['session'], activity=s['total'], complete=complete,
                       available_at=s['previous_available'], expected_minutes=expected, observed_minutes=s['count'])
        if complete:
            self.history.append(summary)
            self.history = self.history[-self.config['lookback']:]
        self.session = None
        return summary

    def checkpoint(self):
        state = json.loads(json.dumps(self.__dict__, allow_nan=False))
        state['state_digest'] = digest(state)
        return state

    @classmethod
    def restore(cls, state):
        state = json.loads(json.dumps(state, allow_nan=False))
        expected = state.pop('state_digest', None)
        if expected is None or digest(state) != expected:
            raise ValueError('checkpoint state integrity mismatch')
        cfg = state['config']
        if cfg['version'] != cls.VERSION or digest(cfg) != state['recipe_hash']:
            raise ValueError('checkpoint recipe mismatch')
        obj = cls(**{k:v for k,v in cfg.items() if k!='version'})
        session = state['session']
        if session:
            op, cl = utc(session['opened']), utc(session['closed'])
            if not op <= utc(session['previous_end']) <= cl or session['count'] < 0:
                raise ValueError('invalid checkpoint cursor')
            if session['partial'] and (session['partial']['activity'] < 0 or session['partial']['input_minutes'] < 1):
                raise ValueError('invalid checkpoint partial')
        if any(not h['complete'] or h['activity'] < 0 for h in state['history']):
            raise ValueError('invalid checkpoint calibration')
        obj.__dict__.update(state)
        return obj
