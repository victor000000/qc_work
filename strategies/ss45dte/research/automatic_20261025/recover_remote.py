"""Read-only remote list recovery with bounded curl streaming; secrets only on stdin."""
import sys,json,hashlib,base64,time,subprocess,concurrent.futures
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'scripts'))
from qc_api_check import credentials
u,t=credentials(ROOT/'data/S001.duckdb');out=Path(__file__).parent

def get(pid):
 ts=str(int(time.time()));auth=base64.b64encode(f'{u}:{hashlib.sha256(f"{t}:{ts}".encode()).hexdigest()}'.encode()).decode()
 cfg='url = "https://www.quantconnect.com/api/v2/backtests/list"\nheader = "Authorization: Basic '+auth+'"\nheader = "Timestamp: '+ts+'"\nheader = "Content-Type: application/json"\ndata = '+json.dumps(json.dumps({'projectId':pid,'includeStatistics':False}))+'\n'
 path=out/f'remote_list_{pid}.json'
 with path.open('w') as f:
  r=subprocess.run(['curl','-sS','--compressed','--max-time','180','--config','-'],input=cfg,text=True,stdout=f,stderr=subprocess.PIPE)
 try:
  d=json.loads(path.read_text());print(pid,'complete',d.get('success'),'count',d.get('count'),[(x.get('name'),x.get('backtestId'),x.get('status')) for x in d.get('backtests',[]) if 'AUTO' in x.get('name','')],flush=True)
 except Exception as e:print(pid,'incomplete',r.returncode,path.stat().st_size,r.stderr,flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:list(ex.map(get,[int(x) for x in sys.argv[1:]] or [31338453,31338461]))
