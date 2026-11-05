"""Refresh reports after each archived native run; no submission or cancellation."""
import subprocess,sys,time
from pathlib import Path
from campaign import OUT
P=Path(__file__).parent
previous=None
while True:
 signatures=tuple(sorted((p.name,p.stat().st_mtime_ns) for p in OUT.glob('*_evidence/audit.json')))
 if signatures!=previous:
  for name in ['analyze.py','bridge.py','report.py']:
   subprocess.run([sys.executable,str(P/name)],check=True,stdout=subprocess.DEVNULL)
  previous=signatures
  print('Reports refreshed; archived accounts',len(signatures),flush=True)
 if len(signatures)==9:break
 if (OUT/'pipeline.log').exists() and 'Traceback (most recent call last)' in (OUT/'pipeline.log').read_text():
  print('Controller failure retained; report shows incomplete runs',flush=True);break
 time.sleep(30)
