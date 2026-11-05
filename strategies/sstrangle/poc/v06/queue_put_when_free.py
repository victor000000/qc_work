"""Task-local continuation: one verified retry after the current native run ends."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
from campaign import rows,ROOT,OUT
old='SSTRANGLE_OO06_20261023_PUT_FULL_V2';new='SSTRANGLE_OO06_20261023_PUT_FULL_V3'
discovery=json.loads((OUT/'discovery_31338453.json').read_text())
assert not any(b['name']==old for b in discovery['matches'])
assert next(r for r in rows() if r['name']==old)['status']=='failed'
while True:
 if any(r['name']==new for r in rows()):print('Retry already present; no duplicate submitted',flush=True);break
 terminal=OUT/'strangle_full_v2_terminal.json'
 if terminal.exists():
  b=json.loads(terminal.read_text())['backtest']
  if not b['completed'] or b.get('error'):raise RuntimeError('Preceding native run did not succeed; inspect before proceeding')
  subprocess.run([sys.executable,str(Path(__file__).with_name('campaign.py')),'queue','--key','PUT_FULL_V3','--kind','put','--full'],check=True)
  assert hashlib.sha256((OUT/'put_full_v3.py').read_bytes()).hexdigest()==hashlib.sha256((OUT/'put_full_v2.py').read_bytes()).hexdigest()
  (OUT/'put_full_v3_retry_receipt.json').write_text(json.dumps(dict(reason='Prior create returned uncertain; read-only project discovery confirmed no native backtest. Retry submitted only after preceding native run completed.',prior_name=old,new_name=new,identical_source_sha256=hashlib.sha256((OUT/'put_full_v3.py').read_bytes()).hexdigest()),indent=2))
  print('PUT_FULL_V3 submitted with identical source after native completion',flush=True);break
 time.sleep(30)
