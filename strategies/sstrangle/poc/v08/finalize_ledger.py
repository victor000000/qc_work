"""Retain all native trials, local search and the superseded preparation scope."""
import json,hashlib
from campaign import OUT,PREFIX,rows,ROOT
items=[]
for row in rows():
 row.pop('result_json',None);key=row['name'].removeprefix(PREFIX).lower();row['manifest']=json.loads((OUT/(key+'_manifest.json')).read_text());row['consistency']=json.loads((OUT/(key+'_consistency.json')).read_text());items.append(row)
(OUT/'trial_ledger.json').write_text(json.dumps(dict(native_trials=items,local_trials_per_strategy=901,local_trials_total=1802,scope_history=['Initial Tom sizing feasibility inspected; user required $100k condor.','User subsequently instructed full equity and deferred Tom sizing; all native runs follow the revised frozen contract.','No $200k account, 10-point-wing variant or Tom sizing limit was run.']),indent=2))
files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.suffix in ['.json','.csv','.parquet','.py','.txt'] and p.name not in ['campaign_manifest.json','TASK_CHECKPOINT.txt']}
code={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'strategies/sstrangle/poc/v08').glob('*.py')}
(OUT/'campaign_manifest.json').write_text(json.dumps(dict(files=files,code=code),indent=2));print('Archived',len(items),'native trials and1,802 local rules')
