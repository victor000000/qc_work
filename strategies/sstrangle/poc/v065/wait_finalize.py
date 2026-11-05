"""Task-local terminal artifact continuation; no cloud submissions or cancellation."""
import json,subprocess,sys,time
from pathlib import Path
P=Path(__file__).parent;OUT=P.parents[1]/'results/qc_delta_poc_20261024'
while True:
 paths=[OUT/(k+'_evidence/audit.json') for k in ['condor_full_t02','condor_full_t05']]
 if all(p.exists() for p in paths):
  assert all(json.loads(p.read_text())['annual_pass'] for p in paths)
  # Enrichment/actual-delta verification must have completed too.
  if 'CAMPAIGN COMPLETE' in (OUT/'controller.log').read_text():break
 if 'Traceback' in (OUT/'controller.log').read_text():raise RuntimeError('Controller failed; preserve all runs and inspect')
 time.sleep(30)
subprocess.run([sys.executable,str(P/'fetch_charts.py')],check=True)
subprocess.run([sys.executable,str(P/'finalize_artifacts.py')],check=True)
print('ARTIFACTS VERIFIED; visual review and documentation promotion remain',flush=True)
