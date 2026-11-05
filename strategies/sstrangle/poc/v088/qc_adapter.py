"""QC-facing minute bridge. Explicit calendar; only sidecar telemetry, never decisions."""
from datetime import timezone
from zoneinfo import ZoneInfo
from .axis import Axis, stamp, utc
from .shadow import features


class QCShadow:
    def __init__(self, calendar, release='qc-native-minute-shadow'):
        self.calendar = {r['session']: r for r in calendar}
        if len(self.calendar) != len(calendar):
            raise ValueError('duplicate calendar session')
        # QC delivery time is simulated, not verified historical availability.
        self.axis = Axis('spx_variation', mode='sampled', release=release)
        self.seen = set()

    def minute(self, row):
        day = row['session']
        current = self.axis.session
        if current and current['session'] != day:
            self.axis.finish()
        if self.axis.session is None:
            c = self.calendar[day]
            self.axis.begin(day, c['open'], c['close'])
        return self.axis.update(row)

    def on_slice(self, algorithm, data):
        """Called before frozen strategy on_data, and cannot submit or modify orders."""
        now = algorithm.utc_time.replace(tzinfo=timezone.utc)
        day = algorithm.time.date().isoformat()
        if day not in self.calendar:
            return
        bar = data.bars.get(algorithm.index)
        if bar is not None:
            # Index bar time is exchange-local. It is not an option quote clock.
            start = bar.time.replace(tzinfo=ZoneInfo('America/New_York'))
            end = bar.end_time.replace(tzinfo=ZoneInfo('America/New_York'))
            calendar = self.calendar[day]
            if utc(start) >= utc(calendar['open']) and utc(end) <= utc(calendar['close']):
                self.minute(dict(session=day, symbol='SPX', start=stamp(start), end=stamp(end),
                                 available_at=None, frequency_seconds=60,
                                 open=float(bar.open), high=float(bar.high), low=float(bar.low), close=float(bar.close),
                                 source_row_id='qc:'+stamp(end), is_fill_forward=bool(bar.is_fill_forward)))
        key = (day, algorithm.time.hour, algorithm.time.minute)
        if (key[1], key[2]) in algorithm.slots and key not in self.seen:
            self.seen.add(key)
            f = features(self.axis.bars, stamp(now))
            algorithm.set_runtime_statistic('AX_version','0.8.8_shadow_sampled')
            algorithm.set_runtime_statistic('AX_bars',str(sum(b['is_complete'] for b in self.axis.bars)))
            algorithm.set_runtime_statistic('AX_status',f['status'])
            algorithm.set_runtime_statistic('AX_last',str(f.get('last_axis_id','')))
