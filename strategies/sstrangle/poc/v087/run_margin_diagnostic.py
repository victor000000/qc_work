"""Telemetry-only replay of the prespecified native margin failure."""
import ast,fcntl,hashlib,json,time,traceback
from campaign import OUT,P,ROOT,run,rows,read,save
from qc_api_check import credentials
lock=(OUT/'margin_diagnostic_controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert 'Capital mechanism tests terminal and archived' in (OUT/'capital_mechanism_controller.log').read_text()
s=(P/'strategy.py').read_text()
method='''    def margin_snapshot(self, reason):
        def typename(x):
            try: return str(x.GetType().FullName)
            except Exception: return type(x).__name__
        held=[dict(symbol=str(s.symbol),quantity=float(s.holdings.quantity),
                   mark=float(s.price),holding_value=float(s.holdings.holdings_value),
                   buying_power_model=typename(s.buying_power_model))
              for s in self.securities.values() if s.invested]
        manager=getattr(self.portfolio,'positions',None)
        groups=getattr(manager,'groups',[])
        group_info=[dict(type=typename(g),model=typename(getattr(g,'buying_power_model',None)),
                         description=str(g)) for g in groups]
        self.emit('MARGIN_DIAGNOSTIC',dict(reason=reason,time=str(self.time),
            equity=float(self.portfolio.total_portfolio_value),cash=float(self.portfolio.cash),
            margin_used=float(self.portfolio.total_margin_used),remaining=float(self.portfolio.margin_remaining),
            held=held,groups=group_info,manager_type=typename(manager)))

'''
s=s.replace('    def on_order_event(self, event):',method+'    def on_order_event(self, event):')
needle="        if order.type != OrderType.OPTION_EXERCISE and not order.tag.startswith('oo05;'):"
s=s.replace(needle,"        if 'Margin Call' in str(order.tag):\n            self.margin_snapshot('native_margin_fill_after_portfolio_update')\n"+needle)
needle='        self.min_margin_remaining=min(self.min_margin_remaining,float(self.portfolio.margin_remaining))'
s=s.replace(needle,needle+"\n        if str(self.time.date())=='2025-03-10' and float(self.portfolio.margin_remaining)<.2*float(self.portfolio.total_portfolio_value):\n            self.margin_snapshot('target_day_minute_before_intervention')")
ast.parse(s);path=P/'strategy_margin_diagnostic.py';assert not path.exists() or path.read_text()==s;path.write_text(s)
plan=json.loads((P/'margin_mechanism_plan.json').read_text());plan.update(key='c0_margin_mechanism200k',source_sha256=hashlib.sha256(s.encode()).hexdigest(),config_overrides={'fill_convention':'quote_side_per_leg','start_capital':200000,'capital_fraction':1.0});save(OUT/'margin_diagnostic_execution_plan.json',plan)
key=plan['key']
try:run(key,'condor',overrides=plan['config_overrides'],source_path=path)
except Exception as e:
 row=next((x for x in rows() if x['name'].endswith(key.upper())),None);details={'key':key,'error':str(e),'queue_row':row,'traceback':traceback.format_exc()}
 if row and row['backtest_id']:
  u,t=credentials(ROOT/'data/S001.duckdb');b=read(u,t,'/backtests/read',dict(projectId=row['project_id'],backtestId=row['backtest_id']));save(OUT/(key+'_failed_terminal.json'),b);details['native_error']=b.get('backtest',{}).get('error')
 save(OUT/(key+'_failure.json'),details)
 if not details.get('native_error'):raise
 while not (OUT/(key+'_evidence/audit.json')).exists():time.sleep(10)
print('Margin telemetry terminal and archived; inspect before any next submission',flush=True)
