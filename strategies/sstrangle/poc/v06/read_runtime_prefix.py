"""Read terminal runtime metadata before the large closed-trade payload; preserve prefix."""
import argparse,base64,hashlib,json,re,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT/'scripts'))
from qc_api_check import credentials
p=argparse.ArgumentParser();p.add_argument('--project',type=int,required=True);p.add_argument('--backtest',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
u,t=credentials(ROOT/'data/S001.duckdb');stamp=str(int(time.time()));digest=hashlib.sha256(f'{t}:{stamp}'.encode()).hexdigest();auth=base64.b64encode(f'{u}:{digest}'.encode()).decode()
cfg=['url = "https://www.quantconnect.com/api/v2/backtests/read"','header = '+json.dumps('Authorization: Basic '+auth),'header = '+json.dumps('Timestamp: '+stamp),'header = "Content-Type: application/json"','request = "POST"','data = '+json.dumps(json.dumps(dict(projectId=a.project,backtestId=a.backtest)))]
proc=subprocess.Popen(['curl','--compressed','--silent','--show-error','--fail-with-body','--connect-timeout','15','--max-time','180','--config','-'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
proc.stdin.write('\n'.join(cfg).encode());proc.stdin.close();data=b'';decoder=json.JSONDecoder();runtime=None
try:
 while len(data)<5_000_000:
  chunk=proc.stdout.read(4096)
  if not chunk:break
  data+=chunk
  text=data.decode('utf-8',errors='replace');m=re.search(r'"runtimeStatistics"\s*:\s*',text)
  if m:
   try:runtime,end=decoder.raw_decode(text[m.end():])
   except json.JSONDecodeError:continue
   break
finally:
 if proc.poll() is None:proc.terminate()
 proc.wait(timeout=10)
if runtime is None:raise RuntimeError('No complete runtime metadata in response prefix: '+proc.stderr.read().decode()[:200])
prefix=data.decode('utf-8',errors='strict');assert re.search(r'"backtestId"\s*:\s*"'+re.escape(a.backtest)+'"',prefix)
assert re.search(r'"projectId"\s*:\s*'+str(a.project),prefix) and re.search(r'"completed"\s*:\s*true',prefix)
a.output.with_suffix('.response_prefix.txt').write_bytes(data)
a.output.write_text(json.dumps(dict(projectId=a.project,backtestId=a.backtest,completed=True,runtimeStatistics=runtime,
 provenance='Complete runtimeStatistics object read from authenticated terminal /backtests/read response; HTTP stream deliberately stopped before large closed-trade array. Raw response prefix retained; not represented as a full response.',prefix_sha256=hashlib.sha256(data).hexdigest()),indent=2)+'\n')
print(len(runtime),'runtime fields',json.dumps(runtime,indent=2))
