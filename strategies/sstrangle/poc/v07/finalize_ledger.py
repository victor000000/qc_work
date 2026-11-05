"""Retain successful native trials and failed preparation/submission attempts."""
import hashlib,json
from campaign import OUT,rows
items=[]
for row in rows():
 row.pop('result_json',None);key=row['name'].removeprefix('SSTRANGLE_OO07_20261024_').lower()
 for suffix in ['manifest','consistency']:
  p=OUT/(key+'_'+suffix+'.json')
  if p.exists():row[suffix]=json.loads(p.read_text())
 terminal=OUT/(key+'_terminal.json')
 if terminal.exists():
  b=json.loads(terminal.read_text())['backtest'];row['native_terminal']={k:b.get(k) for k in ['completed','status','error','progress']}
 row['stage']='native trial' if row['backtest_id'] else 'upload rejected before native backtest'
 items.append(row)
items.append(dict(name='condor_alpha_smoke_plain',stage='local CLI argument error before queue submission',native_backtest_created=False,reason='--extra-files requires a JSON file path, not inline JSON',evidence='controller_plain.log'))
items.append(dict(name='strangle_source_verification_read',stage='post-backtest read-only source audit interrupted by SSL error; resumed successfully',native_backtest_created=False,reason='Added bounded read-only file-read retries and reused saved native terminal/order evidence',evidence='controller_readable.log'))
items.append(dict(name='put_prelaunch_transport_recovery',stage='Rust upload retries exhausted before native launch; same frozen candidate submitted once through authenticated Python transport',native_backtests_cancelled=False,evidence='put_recovery_receipt.json'))
(OUT/'trial_ledger.json').write_text(json.dumps(items,indent=2))
files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.suffix in ['.json','.csv','.parquet','.py','.txt'] and p.name not in ['campaign_manifest.json','TASK_CHECKPOINT.txt'] and not p.name.endswith('_progress.json')}
(OUT/'campaign_manifest.json').write_text(json.dumps({'files':files},indent=2))
print('Preserved',len(items),'attempts')
