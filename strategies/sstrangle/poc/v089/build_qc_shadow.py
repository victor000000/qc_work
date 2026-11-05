"""Assemble an unsubmitted shadow of frozen v087; output source identity is new.

The exact original trading source is embedded, with two telemetry hooks only.
Requires a verified instrument calendar JSON; no automatic cloud submissions.
"""
import argparse,hashlib,json
from pathlib import Path


def build(base, calendar, out):
    base,calendar,out=Path(base),Path(calendar),Path(out)
    if out.exists():raise ValueError('new QC source directory required')
    source=base.read_text();cal=json.loads(calendar.read_text())
    from .qc_adapter import QCShadow
    QCShadow(cal)  # Validate calendar identities before emitting source.
    anchor='    def on_data(self, data):\n'
    init='    def initialize(self):\n'
    if source.count(anchor)!=1 or source.count(init)!=1:raise ValueError('unexpected base strategy structure')
    source=source.replace(init,init+"        self.axis_shadow = QCShadow(CALENDAR)\n",1)
    source=source.replace(anchor,anchor+"        self.axis_shadow.on_slice(self, data)\n",1)
    end='    def on_end_of_algorithm(self):\n'
    if source.count(end)>1:raise ValueError('ambiguous finalization')
    if end in source:
        source=source.replace(end,end+'        self.axis_shadow.finish(self)\n',1)
    else:
        source+='\n    def on_end_of_algorithm(self):\n        self.axis_shadow.finish(self)\n'
    source='from qc_axis_v089 import QCShadow\nfrom axis_calendar_v089 import CALENDAR\n'+source
    here=Path(__file__).parent
    files={'contracts_v089.py':(here/'contracts.py').read_text().replace('from .axis import','from axis_v089 import'), 'main.py':source,'axis_v089.py':(here/'axis.py').read_text(),
           'shadow_v089.py':(here/'shadow.py').read_text().replace('from .axis import','from axis_v089 import'),
           'qc_axis_v089.py':(here/'qc_adapter.py').read_text().replace('from .axis import','from axis_v089 import').replace('from .shadow import','from shadow_v089 import').replace('from .contracts import','from contracts_v089 import'),
           'axis_calendar_v089.py':'CALENDAR = '+repr(cal)+'\n'}
    out.mkdir(parents=True)
    for name,text in files.items():
        compile(text,name,'exec');(out/name).write_text(text)
    m=dict(version='0.8.9',status='assembled_not_submitted',base_source=str(base.resolve()),
           base_sha256=hashlib.sha256(base.read_bytes()).hexdigest(),calendar_sha256=hashlib.sha256(calendar.read_bytes()).hexdigest(),
           files={k:hashlib.sha256(v.encode()).hexdigest() for k,v in files.items()},
           scope='Native QC-minute feature shadow only; provider strict availability is not established')
    (out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');return m

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--calendar',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();print(json.dumps(build(a.base,a.calendar,a.out),indent=2))
