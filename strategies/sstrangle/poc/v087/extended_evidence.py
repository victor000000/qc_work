"""Read-only evidence monitor for ongoing diagnostic jobs; never submits cloud work."""
import fcntl,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from campaign import OUT,P,ROOT,read,save
from qc_api_check import credentials
lock=(OUT/'extended_evidence.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
previous=None
while True:
 for terminal in OUT.glob('*_failed_terminal.json'):
  key=terminal.name.removesuffix('_failed_terminal.json');folder=OUT/(key+'_evidence');b=json.loads(terminal.read_text())['backtest']
  if not b.get('completed'):continue
  receipt=OUT/(key+'_failure_source_readback.json')
  if not receipt.exists():
   u,t=credentials(ROOT/'data/S001.duckdb');cloud=read(u,t,'/files/read',{'projectId':b['projectId']});expected=json.loads((OUT/(key+'_manifest.json')).read_text());remote={x['name']:hashlib.sha256(x['content'].encode()).hexdigest() for x in cloud.get('files',[])}
   matched=all(remote.get(k)==v for k,v in {'main.py':expected['source_sha256'],**expected['extra_files_sha256']}.items());save(receipt,{'project_id':b['projectId'],'backtest_id':b['backtestId'],'readback_matches_submitted':matched,'remote_hashes':remote,'limitation':None if matched else 'Project already reused; submitted queue source retained but original remote source readback unavailable'})
   if matched:save(OUT/(key+'_cloud_source_files.json'),cloud)
  if not (folder/'audit.json').exists():
   cmd=[sys.executable,str(P/'collect.py'),'--name','SSTRANGLE_OO087_20261027_'+key.upper(),'--output',str(folder),'--raw-pages','--terminal-json',str(terminal)]
   with (OUT/(key+'_export.log')).open('a') as log:subprocess.run(cmd,env=dict(os.environ,PYTHONPATH=str(ROOT/'scripts')),stdout=log,stderr=subprocess.STDOUT,check=True)
 signatures=tuple(sorted((str(f),f.stat().st_mtime_ns) for pattern in ['*_evidence/audit.json','*_failure.json'] for f in OUT.glob(pattern)))
 if signatures!=previous:
  for script in ['analyze.py','bridge.py','settlement_revalue.py','report.py']:
   subprocess.run([sys.executable,str(P/script)],check=True,stdout=subprocess.DEVNULL)
  previous=signatures;print('Extended reports refreshed',len(signatures),flush=True)
 time.sleep(25)
