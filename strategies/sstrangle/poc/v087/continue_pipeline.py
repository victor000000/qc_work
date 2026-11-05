"""Resume verified smoke -> fresh baselines -> local research -> fresh QC verification."""
import json,subprocess,sys,time
from pathlib import Path
from campaign import OUT,run
if __name__=='__main__':
 while not (OUT/'p1_smoke_evidence/audit.json').exists():time.sleep(10)
 for key in ['c0','c1','p1']:
  a=json.loads((OUT/(key+'_smoke_evidence/audit.json')).read_text())
  if not a.get('native_cloud_terminal_success'):raise RuntimeError('Smoke failed: '+key)
 for stage in ['baseline','verify']:
  if stage=='verify':
   assert (OUT/'local_summary.json').exists(),'Local independent attempt must precede verification'
  for key,kind,alpha in [('c0','condor',False),('c1','condor',True),('p1','put_spread',False)]:
   run(key+'_'+stage,kind,alpha)
 print('All native baseline and verification accounts archived',flush=True)
