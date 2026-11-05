"""Isolated QC observer. Native strategy calls and exceptions remain outside this bridge."""
import json
from uuid import uuid4
from datetime import timezone
from zoneinfo import ZoneInfo
from .axis import Axis, stamp, utc, digest
from .shadow import features
from .contracts import validate_calendar


class QCShadow:
    def __init__(self, calendar, release='qc-native-minute-shadow'):
        self.calendar=validate_calendar(calendar)
        self.axis=Axis('spx_variation',mode='sampled',release=release,retention=128,calendar_hash=digest(calendar))
        self.calendar_hash=digest(calendar)
        self.export_run_id=uuid4().hex;self.shard_count=0;self.export_digest=None;self.finalized=False
        self.seen=set();self.valid=True;self.errors=[];self.records=[];self.shards=[];self.final_summary=None

    def minute(self,row):
        day=row['session'];current=self.axis.session
        if current and current['session']!=day:
            prior=current['session'];seq=current['sequence'];seg=current['segment']
            summary=self.axis.finish()
            self.records.extend(dict(kind='bar',value=b) for b in self.axis.bars if b['session']==prior and b['sequence']>seq)
            self.records.extend(dict(kind='quality',value=e) for e in self.axis.events if e['session']==prior and e['segment_id']>seg)
            self.records.append(dict(kind='session',value=summary))
        if self.axis.session is None:
            c=self.calendar[day];self.axis.begin(day,c['open'],c['close'])
        return self.axis.update(row)

    def _error(self,exc):
        self.valid=False
        self.errors.append(dict(type=type(exc).__name__,message=str(exc)[:240]))
        self.errors=self.errors[-16:]

    def _flush(self,algorithm):
        if not self.records:return
        key=f'axis_v089/{self.export_run_id}/{self.shard_count:06d}.json'
        payload=json.dumps(self.records,allow_nan=False)
        if not algorithm.object_store.save(key,payload):raise RuntimeError('shadow export failed')
        self.export_digest=digest(dict(previous=self.export_digest,key=key,records=self.records))
        self.shard_count+=1
        self.shards=[dict(key=key,sha256=digest(self.records),chain=self.export_digest)]
        self.records=[]

    def finish(self,algorithm=None):
        if self.finalized:return self.final_summary
        try:
            if self.axis.session is not None:
                day=self.axis.session['session'];seq=self.axis.session['sequence'];seg=self.axis.session['segment']
                self.final_summary=self.axis.finish()
                self.records.extend(dict(kind='bar',value=b) for b in self.axis.bars if b['session']==day and b['sequence']>seq)
                self.records.extend(dict(kind='quality',value=e) for e in self.axis.events if e['session']==day and e['segment_id']>seg)
            if algorithm is not None:
                self.records.append(dict(kind='finish',summary=self.final_summary,valid=self.valid,
                    errors=self.errors,calendar_hash=self.calendar_hash,state_digest=self.axis.checkpoint()['state_digest']))
                self._flush(algorithm)
            self.finalized=True
        except Exception as exc:self._error(exc)
        return self.final_summary

    def on_slice(self,algorithm,data):
        try:self._observe(algorithm,data)
        except Exception as exc:self._error(exc)

    def _observe(self,algorithm,data):
        now=algorithm.utc_time
        now=now.replace(tzinfo=timezone.utc) if now.tzinfo is None else utc(now)
        day=algorithm.time.date().isoformat()
        if day not in self.calendar:return
        bar=data.bars.get(algorithm.index)
        if bar is not None:
            start=bar.time;end=bar.end_time
            if start.tzinfo is None:start=start.replace(tzinfo=ZoneInfo('America/New_York'))
            if end.tzinfo is None:end=end.replace(tzinfo=ZoneInfo('America/New_York'))
            calendar=self.calendar[day]
            if utc(start)>=utc(calendar['open']) and utc(end)<=utc(calendar['close']):
                before=self.axis.session['segment'] if self.axis.session and self.axis.session['session']==day else -1
                emitted=self.minute(dict(session=day,symbol='SPX',start=stamp(start),end=stamp(end),
                    available_at=stamp(now),frequency_seconds=60,open=float(bar.open),high=float(bar.high),
                    low=float(bar.low),close=float(bar.close),source_row_id='qc:'+stamp(end),
                    is_fill_forward=bool(bar.is_fill_forward)))
                if emitted:self.records.append(dict(kind='bar',value=emitted))
                self.records.extend(dict(kind='quality',value=e) for e in self.axis.events if e['session']==day and e['segment_id']>before)
        key=(day,algorithm.time.hour,algorithm.time.minute)
        if (key[1],key[2]) in algorithm.slots and key not in self.seen:
            self.seen={k for k in self.seen if k[0]==day};self.seen.add(key)
            f=features(self.axis,stamp(now)) if self.valid else dict(status='shadow_invalid')
            self.records.append(dict(kind='decision',decision_at=stamp(now),value=f,calendar_hash=self.calendar_hash))
            algorithm.set_runtime_statistic('AX_version','0.8.9_shadow_sampled')
            algorithm.set_runtime_statistic('AX_status',f['status'])
            algorithm.set_runtime_statistic('AX_valid',str(self.valid))
        if len(self.records)>=64:self._flush(algorithm)
