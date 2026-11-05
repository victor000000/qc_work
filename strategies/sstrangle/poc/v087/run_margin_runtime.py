"""Preserve margin telemetry in bounded runtime statistics when QC log quota is exhausted."""
import ast,fcntl,hashlib,json,time,traceback
from campaign import OUT,P,ROOT,run,rows,read,save
from qc_api_check import credentials
lock=(OUT/'margin_runtime_controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert 'Margin telemetry terminal and archived' in (OUT/'margin_diagnostic_controller.log').read_text()
s=(P/'strategy_margin_diagnostic.py').read_text()
helper='''    def persist_margin_snapshot(self, payload):
        payload['held']=[[x['symbol'],x['quantity'],x['mark'],x['holding_value'],x['buying_power_model']] for x in payload['held']]
        payload['groups']=dict(Counter(x['model'] for x in payload['groups']))
        raw=json.dumps(payload,separators=(',',':'))
        if len(raw)>5600:
            payload['held']=payload['held'][:16]
            payload['held_truncated']=True
            raw=json.dumps(payload,separators=(',',':'))
        if len(raw)>5600:raise RuntimeError('Margin telemetry exceeds bounded capacity')
        for i in range(35):
            self.set_runtime_statistic('MD_'+str(i).zfill(2),raw[i*160:(i+1)*160] or ' ')
        self.set_runtime_statistic('MD_length',str(len(raw)))

'''
s=s.replace('    def margin_snapshot(self, reason):',helper+'    def margin_snapshot(self, reason):').replace("self.emit('MARGIN_DIAGNOSTIC',dict(","self.persist_margin_snapshot(dict(")
ast.parse(s);path=P/'strategy_margin_runtime.py';assert not path.exists() or path.read_text()==s;path.write_text(s)
key='c0_margin_runtime200k';cfg={'fill_convention':'quote_side_per_leg','start_capital':200000,'capital_fraction':1.0}
save(OUT/'margin_runtime_execution_plan.json',{'key':key,'reason':'Prior telemetry replay reproduced failure but QC returned daily/backtest log quota message, no snapshots. Bounded runtime-statistic sink replaces log sink; trading logic unchanged.','source_sha256':hashlib.sha256(s.encode()).hexdigest(),'overrides':cfg,'acceptance':'Must observe archived runtime MD fields; absence remains telemetry failure, not proof of margin cause.'})
try:run(key,'condor',overrides=cfg,source_path=path)
except Exception as e:
 row=next((x for x in rows() if x['name'].endswith(key.upper())),None);details={'key':key,'error':str(e),'queue_row':row,'traceback':traceback.format_exc()}
 if row and row['backtest_id']:
  u,t=credentials(ROOT/'data/S001.duckdb');b=read(u,t,'/backtests/read',dict(projectId=row['project_id'],backtestId=row['backtest_id']));save(OUT/(key+'_failed_terminal.json'),b);details['native_error']=b.get('backtest',{}).get('error')
 save(OUT/(key+'_failure.json'),details)
 if not details.get('native_error'):raise
 while not (OUT/(key+'_evidence/audit.json')).exists():time.sleep(10)
print('Bounded runtime margin probe terminal and archived',flush=True)
