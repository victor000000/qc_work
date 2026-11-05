"""Read-only native AGE24 audit; failed control exposure is retained as evidence."""
import argparse,ast,fcntl,hashlib,json
from collections import Counter
from datetime import date,datetime,time,timedelta
from pathlib import Path
import report as shared
from zc_risk_guard_report import economic
from account_drawdown import chart_drawdown

HERE=Path(__file__).resolve().parent
FROZEN=HERE.parent/'results/strangle_basket-calmar_20261019_182746'
GOLD=FROZEN/'SSTRANGLE_20261019_182746_cap20_stop1_guard_rv12_exit21/orders.json'
IDS={733,734,735,736,737,738}
INITIAL=47823.595


def source_proof(c,key,cfg,row):
    code=(c/(key+'.py')).read_text();extras=json.loads((c/'extra_files.json').read_text());m=json.loads((c/'manifest.json').read_text())
    queued=json.loads(row['extra_files']) if isinstance(row['extra_files'],str) else row['extra_files']
    if code!=row['code'] or queued!=extras:raise ValueError('Actual queued TWTR AGE source differs')
    configs=[ast.literal_eval(n.value) for n in ast.walk(ast.parse(code)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CONFIG' for t in n.targets)]
    if configs!=[cfg] or type(cfg.get('holding_cap')) is not bool or cfg['holding_cap'] is not (key=='twtr_age24'):
        raise ValueError('Wrong isolated control/candidate policy')
    if cfg['max_holding_days']!=24 or cfg['stop_multiple']!=1 or cfg['risk_interval_minutes']!=15:
        raise ValueError('Undeclared AGE/risk parameter change')
    frozen=json.loads((FROZEN/'extra_files.json').read_text())
    if any(extras.get(k)!=v for k,v in frozen.items()):raise ValueError('Original execution dependency differs')
    if extras['twtr_original_strategy.py']!=(FROZEN/'cap20_stop1_guard_rv12_exit21.py').read_text():
        raise ValueError('Original risk/execution strategy differs')
    helper=extras['holding_age.py']
    if hashlib.sha256(helper.encode()).hexdigest()!=m['holding_age_helper_sha256'] or 'TWTR' in helper or '2022' in helper:
        raise ValueError('Holding deadline helper changed or contains case-specific filters')
    if any(s in code for s in ('set_fill_model(', 'set_buying_power_model(', 'set_margin_call_model(', 'set_holdings(')):
        raise ValueError('Fixture replaced native accounting/execution')
    return dict(queued_source_identical=True,original_native_models_preserved=True,
        source_sha256=hashlib.sha256(code.encode()).hexdigest(),extras_sha256=hashlib.sha256((c/'extra_files.json').read_bytes()).hexdigest())


def audit(orders,rust,full,cap,gold_orders):
    fills=shared.execution_rows(orders);gold=shared.execution_rows(gold_orders)
    if shared.execution_signature(fills)!=shared.execution_signature(shared.execution_rows(rust)):
        raise ValueError('Actual Rust/Python AGE executions differ')
    if len(gold_orders)!=6 or {o['id'] for o in gold_orders}!=IDS:raise ValueError('Wrong actual TWTR source orders')
    if len(orders)!=len(fills) or len(orders)!=int(str(full['statistics']['Total Orders']).replace(',','')) or len(orders)!=6:
        raise ValueError('Missing/rejected/extra native TWTR orders')
    by_id={f['order_id']:f for f in fills};inventory=Counter()
    for o in sorted(orders,key=lambda o:o['id']):
        f=by_id[o['id']]
        if o['status']!=3 or abs(f['quantity'])!=2 or float(o['quantity'])!=f['quantity'] or f['multiplier']!=100 or f['underlying_id']!='TWTR VLE97YS7S57P':
            raise ValueError('Actual native TWTR size/identity/fill mismatch')
        inventory[f['symbol_id']]+=f['quantity']
        if not -2<=inventory[f['symbol_id']]<=0:raise ValueError('Native TWTR overclose or unexpected quantity')
    residual={s:q for s,q in inventory.items() if q}
    cash=INITIAL+sum(-f['quantity']*f['qc_price']*f['multiplier']-f['fee'] for f in fills)
    fees=sum(f['fee'] for f in fills);rt=full['runtimeStatistics']
    end=float(full['totalPerformance']['portfolioStatistics']['endEquity'])
    if abs(abs(shared.money(rt['Fees']))-fees)>.0051 or abs(shared.money(rt['Equity'])-end)>.0051:
        raise ValueError('Actual AGE fees/equity do not reconcile')
    result=dict(actual_native_orders=len(orders),actual_fills=len(fills),actual_fees=fees,
                actual_cash=cash,exact_account_equity=end,residual_quantities=residual,
                strategy_calmar_proven=False,scope='Isolated held-position execution only')
    if not cap:
        error=full.get('error','')
        if shared.terminal_status(full)!='failed' or '2022-10-29' not in error or 'Mandatory exit lacked fresh quotes on its eligible session: TWTR VLE97YS7S57P' not in error:
            raise ValueError('Control did not reproduce actual mandatory-quote failure')
        if economic(fills)!=economic(gold):raise ValueError('Control did not reproduce all six genuine source fills')
        original=Counter()
        for f in gold:original[f['symbol_id']]+=f['quantity']
        if residual!={s:q for s,q in original.items() if q} or abs(cash-end-abs(shared.money(rt['Holdings'])))>.0051:
            raise ValueError('Actual failed control residual/cash/account mismatch')
        result.update(expected_cloud_failure_reproduced=True,all_six_control_fills_equal=True,
                      realized_cycle_pnl=None,residuals_preserved=True)
        return result,fills
    if shared.terminal_status(full)!='done' or residual or shared.money(rt['Holdings'])!=0 or shared.money(rt['Unrealized'])!=0 or abs(cash-end)>.0051:
        raise ValueError('Candidate is not genuinely complete and flat')
    prefix=[f for f in fills if f['reason'] in ('OPEN','ROLL')]
    if len(prefix)!=4 or economic(prefix)!=economic([f for f in gold if f['order_id']<=736]):
        raise ValueError('Candidate changed genuine pre-AGE opening/roll economics')
    cycles=shared.audit_dte(orders)
    if len(cycles)!=1 or cycles[0]['reason']!='AGE' or cycles[0]['rolls']!=1:
        raise ValueError('Candidate did not complete one real AGE cycle')
    cycle=cycles[0];due=shared.ny_time(cycle['entry']).date()+timedelta(days=24)
    calendar=json.loads((HERE.parent/'research/reference/lean_market_hours_20261018.json').read_text())['entries']['Equity-usa-[*]']
    for _ in range(15):
        if shared.noon_open(due,calendar):break
        due+=timedelta(days=1)
    else:raise ValueError('Cannot establish first product-open AGE session')
    closing=[f for f in fills if f['reason']=='AGE'];closing_orders=[o for o in orders if ':AGE' in o['tag'].split(';')[0]]
    if len(closing)!=2 or any(o['type']!=8 for o in closing_orders):raise ValueError('AGE requires genuine native equity combo market fills')
    for f in closing:
        when=shared.ny_time(f['timestamp'])
        if when.date()!=due or not time(12)<=when.time()<=time(12,5):raise ValueError('AGE fill missed first eligible product noon')
    if due!=date(2022,10,17) or cycle['exit_dte']!=32:raise ValueError('Wrong isolated AGE deadline/expiry')
    net=cash-INITIAL
    if abs(net-cycle['pnl'])>.0051 or abs(float(rt['fixture_cycle_net'])-net)>.0051:
        raise ValueError('Actual candidate cycle/account differs')
    for k,v in dict(AGE='1',fixture_age_days='24',fixture_synthetic_fills='0',fixture_settlement_cash='0',fixture_calmar_claim='0').items():
        if rt.get(k)!=v:raise ValueError('Missing genuine AGE policy proof: '+k)
    result.update(native_age_exit_verified=True,all_four_pre_exit_fills_equal=True,
                  realized_cycle_pnl=net,cycle=cycle,first_eligible_age_date=str(due))
    return result,fills


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('campaign',type=Path);c=p.parse_args().campaign.resolve();m=json.loads((c/'manifest.json').read_text())
    if m['phase']!='basket-twtr-age-regression' or set(m['variants'])!={'twtr_age_control','twtr_age24'} or m['source_orders_sha256']!=hashlib.sha256(GOLD.read_bytes()).hexdigest():
        raise ValueError('Wrong frozen AGE comparison/reference')
    lock=(c/'age_report.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:print('Another AGE collector owns this campaign');return
    gold=[o for o in json.loads(GOLD.read_text()) if o['id'] in IDS]
    u,t=shared.credentials(shared.ROOT/'data/S001.duckdb');results={};identities=[]
    for name in m['jobs']:
        key,cfg=shared.config_for(name,m)
        with shared.storage.connect(f'file:{shared.ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as conn:
            conn.row_factory=shared.storage.Row;row=dict(conn.execute('select * from backtest_queue where name=?',(name,)).fetchone())
        proof=source_proof(c,key,cfg,row);identities.append({k:row[k] for k in ['name','status','project_id','backtest_id']})
        if not row['backtest_id']:results[key]=dict(status=row['status']);continue
        response=shared.read_research_backtest(u,t,c,name,row);full=response['backtest'];shared.validate_identity(full,row);status=shared.terminal_status(full)
        if status is None:results[key]=dict(status=full.get('status'),progress=full.get('progress'));continue
        folder=shared.collect_terminal(u,t,c,name,row,response)
        orders=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text());rust=rust['orders'] if isinstance(rust,dict) else rust
        result,fills=audit(orders,rust,full,cfg['holding_cap'],gold)
        result.update(status=status,error=full.get('error'),backtest_id=row['backtest_id'],source_proof=proof)
        charts=[dict(source=n,**chart_drawdown(json.loads((folder/n).read_text()),INITIAL,date(2022,9,20),date(2022,10,31))) for n in ['trading_period.json','strategy_equity.json'] if (folder/n).exists()]
        if not charts:raise ValueError('Actual AGE account chart unavailable')
        result['account_chart_drawdown_audits']=charts
        shared.write_tables(folder/'age_report',dict(executions=fills,residual_positions=[dict(symbol_id=s,quantity=q) for s,q in result['residual_quantities'].items()],cycles=[result['cycle']] if 'cycle' in result else []))
        shared.atomic_json(folder/'age_audit.json',result);results[key]=result
    verified=results.get('twtr_age_control',{}).get('expected_cloud_failure_reproduced') and results.get('twtr_age24',{}).get('native_age_exit_verified')
    result=dict(results=results,jobs=identities,paired_age_audit_passed=bool(verified),strategy_calmar_proven=False,
                scope='Known TWTR holding, isolated deadline change; original risk timing shared by both. Combined full-strategy performance is unproven.')
    shared.atomic_json(c/'twtr_age_summary.json',result);print(json.dumps(result,indent=2))


if __name__=='__main__':main()
