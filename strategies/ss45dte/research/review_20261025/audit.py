"""Read-only SS45DTE source/queue audit; never queues a run or changes an algorithm."""
import hashlib
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
import qc_storage

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
source = ROOT/'strategy.py'
shim = types.ModuleType('AlgorithmImports')
shim.QCAlgorithm = type('QCAlgorithm', (), {})
shim.timedelta = timedelta
sys.modules['AlgorithmImports'] = shim
namespace = {}
exec(compile(source.read_text(), str(source), 'exec'), namespace)
algorithm = namespace['Ss45Dte']()
algorithm.Portfolio = types.SimpleNamespace(TotalPortfolioValue=150000)
algorithm._vega = lambda contract, dte: 1000.0
actual = algorithm._contracts('TLT', None, None, 45)
corrected_same_proxy = int(1500 // (2 * (1000/100) * 2.5))
algorithm.option = {t:types.SimpleNamespace(Symbol=t) for t in namespace['UNIVERSE']}
algorithm.legs = {'TLT':['call','put']}
managed=[]
algorithm._manage=managed.append
algorithm.OnData(types.SimpleNamespace(OptionChains={}))
with qc_storage.connect('/home/vic/qc_work/data/SS45DTE.duckdb') as con:
    queue=[dict(zip(['name','status','error_message'],r)) for r in con.execute(
        'SELECT name,status,error_message FROM backtest_queue ORDER BY id').fetchall()]
    runs=[dict(zip(['name','status','total_orders','net_profit_pct','dd'],r)) for r in con.execute(
        'SELECT name,status,total_orders,net_profit_pct,dd FROM experiments ORDER BY id').fetchall()]
result=dict(strategy='ss45dte',observed_at=datetime.now(timezone.utc).isoformat(),
            source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            database='/home/vic/qc_work/data/SS45DTE.duckdb',queue=queue,runs=runs,
            unit_demo=dict(equity=150000,name_budget=1500,vega_per_decimal=1000,p5_points=2.5,
                           current_contracts=actual,unit_corrected_proxy_contracts=corrected_same_proxy),
            no_chain_demo=dict(open_ticker='TLT',manage_calls=managed),
            note='Synthetic unit/control-flow fixtures, not a backtest or sizing recommendation')
(OUT/'audit.json').write_text(json.dumps(result,indent=2,default=str)+'\n')
print(json.dumps(result,indent=2,default=str))
