"""Submit one admission-only replay after primary trading runs are terminal."""
import subprocess,sys,time,json
from pathlib import Path
from campaign import rows,ROOT,OUT
name='SSTRANGLE_OO06_20261023_DIAG_FULL_V2'
while True:
 if any(r['name']==name for r in rows()):print('Diagnostic already submitted; no duplicate',flush=True);break
 terminal=OUT/'put_full_v3_terminal.json'
 if terminal.exists():
  b=json.loads(terminal.read_text())['backtest']
  if not b['completed'] or b.get('error'):raise RuntimeError('Primary put did not complete successfully')
  subprocess.run([str(ROOT/'target/release/qc-backtest-server'),'queue','--strategy','sstrangle','--name',name,'--code-file',str(OUT/'diag_full_v2.py'),'--batch','oo06_20261023','--description','Admission-only replay with bounded readable aggregate statistics; no orders'],check=True)
  print('Diagnostic submitted after primary native completion',flush=True);break
 time.sleep(30)
