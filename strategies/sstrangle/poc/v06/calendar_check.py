"""Independent scheduled-slot inventory from the saved LEAN US equity calendar."""
import json,hashlib
from datetime import datetime,date,timedelta,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
p=ROOT/'strategies/sstrangle/research/reference/lean_market_hours_20261018.json';r=json.loads(p.read_text())['entries']['Equity-usa-[*]']
def parse(s):return datetime.strptime(s,'%m/%d/%Y').date()
holidays={parse(s) for s in r['holidays']};early={parse(s):time.fromisoformat(t) for s,t in r['earlyCloses'].items()}
slots=[time(9,35)]+[time(h,m) for h in range(10,16) for m in [0,30]]
day=date(2022,5,16);rows=[]
while day<=date(2026,7,13):
 if day.weekday()<5 and day not in holidays:
  close=early.get(day,time(16));valid=[s for s in slots if s<close]
  rows.append({'day':str(day),'close':str(close),'slots':len(valid),'boundary_slot':int(close in slots)})
 day+=timedelta(days=1)
result=dict(source=str(p),source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),calendar_key='Equity-usa-[*]',sessions=len(rows),session_dates=[r['day'] for r in rows],pre_close_slots=sum(r['slots'] for r in rows),close_boundary_slots=sum(r['boundary_slot'] for r in rows),half_days=[r for r in rows if r['boundary_slot']],
 interpretation='Independent saved US equity-calendar cross-check, not a reconstruction of QC Slice delivery or proof of the source simulator calendar')
(ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023/calendar_inventory.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
