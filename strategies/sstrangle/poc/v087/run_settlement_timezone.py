"""Disambiguate cached-bar clock without changing native trading behavior."""
import ast,fcntl,hashlib,json,time,traceback
from campaign import OUT,P,ROOT,run,rows,read,save
from qc_api_check import credentials
lock=(OUT/'settlement_timezone_controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
plan=json.loads((P/'settlement_timezone_plan.json').read_text())
source=(P/'strategy_settlement_diagnostic.py').read_text()
needle='                    underlying_bar_time=str(underlying_bar.time) if underlying_bar else None,'
extra='''                    underlying_exchange_timezone=str(option.underlying.exchange.time_zone),
                    underlying_security_local_time=str(option.underlying.local_time),
                    subscription_timezones=[dict(data=str(getattr(c,'data_time_zone',None)),
                        exchange=str(getattr(c,'exchange_time_zone',None)))
                        for c in self.subscription_manager.subscriptions if c.symbol == option.underlying.symbol],
'''
assert source.count(needle)==1
source=source.replace(needle,extra+needle);ast.parse(source);path=P/'strategy_settlement_timezone.py'
assert not path.exists() or path.read_text()==source
path.write_text(source);plan['source_sha256']=hashlib.sha256(source.encode()).hexdigest();save(OUT/'settlement_timezone_execution_plan.json',plan)
while 'Combined cost/funding tests terminal and archived' not in (OUT/'cost_funding_controller.log').read_text():
 if 'Traceback (most recent call last)' in (OUT/'cost_funding_controller.log').read_text():raise RuntimeError('Cost/funding controller requires diagnosis')
 time.sleep(25)
key=plan['key']
try:run(key,'put_spread',overrides={'start':[2022,9,30],'last_entry':[2022,9,30]},source_path=path)
except Exception as e:
 row=next((x for x in rows() if x['name'].endswith(key.upper())),None);details={'key':key,'error':str(e),'queue_row':row,'traceback':traceback.format_exc()}
 if row and row['backtest_id']:
  u,t=credentials(ROOT/'data/S001.duckdb');b=read(u,t,'/backtests/read',dict(projectId=row['project_id'],backtestId=row['backtest_id']));save(OUT/(key+'_failed_terminal.json'),b);details['native_error']=b.get('backtest',{}).get('error')
 save(OUT/(key+'_failure.json'),details)
 raise
print('Timezone probe terminal and archived',flush=True)
