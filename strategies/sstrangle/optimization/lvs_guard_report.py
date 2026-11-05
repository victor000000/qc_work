"""Read-only native voluntary-guard comparison. No orders, server or queue changes."""
import argparse,ast,fcntl,hashlib,importlib.util,json
from collections import Counter
from datetime import datetime,timedelta,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('_guard_lvs_native',HERE/'lvs_exit_report.py');native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
shared=native.shared
PARENT=native.STRATEGY/'results/strangle_basket-lvs-regression_20261019_143611/lvs_market_control.py'
REFERENCE=native.STRATEGY/'results/strangle_basket-calmar_20261019_150331/cap20_stop1_exit28.py'
DUE=datetime(2015,8,21,16,tzinfo=timezone.utc)

def methods(source):
    tree=ast.parse(source);c=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ResearchShortStrangle')
    return {n.name:ast.dump(n,include_attributes=False) for n in c.body if isinstance(n,ast.FunctionDef)}

def source_proof(campaign,key,config,row):
    source=(campaign/(key+'.py')).read_text();extra=json.loads((campaign/'extra_files.json').read_text())
    queued=json.loads(row['extra_files']) if isinstance(row['extra_files'],str) else row['extra_files']
    if source!=row['code'] or extra!=queued:raise ValueError('Actual queued source/helpers differ')
    configs=[ast.literal_eval(n.value) for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CONFIG' for t in n.targets)]
    if configs!=[config] or not isinstance(config.get('voluntary_guard'),bool) or config.get('limit_exit') is not False:raise ValueError('Wrong literal policy configuration')
    if extra.get('lvs_original_fixture.py')!=PARENT.read_text() or extra.get('unguarded_reference.py')!=REFERENCE.read_text():raise ValueError('Original native control/reference differs')
    original=methods(extra['unguarded_reference.py']);guarded=methods(extra['guarded_strategy.py'])
    if {k for k in original if original[k]!=guarded.get(k)}!={'on_data','intraday_risk_exits','process_exit_requests'} or set(guarded)-set(original)!={'voluntary_quote_ready'}:raise ValueError('Guard changed methods outside declared scope')
    frozen=json.loads((native.STRATEGY/'results/strangle_basket_20261018_191012/extra_files.json').read_text())
    for k in ('rules.py','execution_base.py','basket_rules.py','terminal_margin.py','premium_units.py','premium_filter.py'):
        if extra.get(k)!=frozen[k]:raise ValueError('Default execution dependency changed: '+k)
    # The unchanged reference contains its previously verified terminal-only
    # insolvency margin model. Audit NEW/CHANGED methods for model replacement;
    # exact AST equality above retains that original terminal-only method.
    changed_names={'on_data','intraday_risk_exits','process_exit_requests','voluntary_quote_ready'}
    changed_bodies=[ast.unparse(n) for n in ast.walk(ast.parse(extra['guarded_strategy.py'])) if isinstance(n,ast.FunctionDef) and n.name in changed_names]
    for body in [source,extra['voluntary_quote_guard.py'],*changed_bodies]:
        if any(x in body for x in ('set_fill_model(', 'set_buying_power_model(', 'set_margin_call_model(')):raise ValueError('Default model replaced')
    return dict(queued_source_identical=True,only_declared_research_methods_changed=True,original_native_parent_identical=True,
        main_sha256=hashlib.sha256(source.encode()).hexdigest(),extras_sha256=hashlib.sha256((campaign/'extra_files.json').read_bytes()).hexdigest())

def audit_guard(orders,rust,full):
    attempts,events,issues=native.native_records(orders);ra,re,ri=native.native_records(rust);issues+=ri
    if attempts!=ra or events!=re:issues.append('Rust/Python complete native events differ')
    fills=[e for e in events if e['quantity']]
    _,gold,gi=native.native_records(native.gold_orders());issues+=gi
    gold_fills=[e for e in gold if e['quantity']]
    if native.economics(fills[:2])!=native.economics(gold_fills[:2]):issues.append('Original opening economics changed')
    if len(orders)!=4 or len(fills)!=4:issues.append('Expected two real opening and two real closing fills')
    declared=full.get('statistics',{}).get('Total Orders')
    if declared is None or int(str(declared).replace(',',''))!=len(orders):issues.append('Incomplete declared actual orders')
    holdings=Counter()
    for e in sorted(events,key=lambda e:(e['utc'],e['order_id'],e['event_id'])):
        if e['native_sid'] not in native.SID_SET:issues.append('Unexpected native contract')
        holdings[e['native_sid']]+=e['quantity']
        if holdings[e['native_sid']]>1e-9:issues.append('Actual event path overclosed')
    residual={k:v for k,v in holdings.items() if abs(v)>1e-9}
    if residual:issues.append('Actual residual exposure')
    reasons=set();closing=[]
    for o in orders:
        if o['status']!=3 or abs(sum(e['quantity'] for e in events if e['order_id']==o['id'])-float(o['quantity']))>1e-9:issues.append('Incomplete or mismatched actual native order')
        if ':OPEN' in o.get('tag','').split(';')[0]:continue
        closing.append(o);head=o.get('tag','').split(';')[0];reason=head.split(':')[-1];reasons.add(reason)
        if reason not in ('PROFIT','STOP','TIME') or native.tag_fields(o).get('attempt')!='guard_market':issues.append('Undeclared or forced native close')
        if o['type']!=8 or float(o['quantity'])!=2:issues.append('Closing order is not original-sized native combo market')
        stamp=native.utc(o['time'])
        if stamp<native.TRIGGER+timedelta(minutes=14) or stamp>DUE+timedelta(minutes=5):issues.append('Guarded order outside declared observation/deadline window')
        if reason=='TIME' and not DUE<=stamp<=DUE+timedelta(minutes=5):issues.append('TIME order missed first eligible28DTE noon')
    if len(closing)!=2 or len(reasons)!=1:issues.append('Native closing pair/reason missing')
    for e in fills[2:]:
        if e['quantity']!=2 or not native.TRIGGER+timedelta(minutes=14)<=native.utc(e['utc'])<=DUE+timedelta(minutes=5):issues.append('Actual closing fill outside permitted path')
    runtime=full.get('runtimeStatistics',{})
    for key in ('guard_first_deferred','guard_original_holdings_retained','guard_actual_closed'):
        if str(runtime.get(key))!='1':issues.append('Missing actual aggregate proof: '+key)
    if len(reasons)!=1 or runtime.get('guard_actual_exit_reason') not in reasons:issues.append('Actual runtime reason differs from native close')
    supported=all(e['price'] is not None and e['fee'] is not None for e in fills)
    cash=sum(-e['quantity']*e['price']*100 for e in fills) if supported else None
    fees=sum(e['fee'] for e in events if e['fee'] is not None)
    ending=None
    try:
        ending=shared.money(runtime['Equity'])
        if cash is None or abs(ending-native.INITIAL-cash+fees)>.0051:issues.append('Actual account/cashflow mismatch')
        if abs(abs(shared.money(runtime['Fees']))-fees)>.0051:issues.append('Actual fees differ')
        if shared.money(runtime['Holdings'])!=0 or shared.money(runtime['Unrealized'])!=0:issues.append('Terminal account not flat')
    except (KeyError,ValueError):issues.append('Missing actual terminal account fields')
    if native.terminal_status(full)!='done':issues.append('Cloud not cleanly completed')
    valid=not issues
    return dict(engineering_only=True,strategy_performance_claim=False,native_execution_account_audit_passed=valid,issues=list(dict.fromkeys(issues)),
        native_orders=len(orders),actual_fill_events=len(fills),actual_fees=fees,actual_cashflow=cash,
        native_single_cycle_pnl=cash-fees if valid else None,ending_account_equity=ending,residual_native_quantities=residual,
        guard_runtime_proof={k:runtime.get(k) for k in ('guard_first_deferred','guard_original_holdings_retained','guard_actual_closed','guard_actual_exit_reason')},
        limits_or_synthetic_fills_allowed=False,full_strategy_path_verified=False),attempts,events

def main():
    parser=argparse.ArgumentParser();parser.add_argument('campaign',type=Path);a=parser.parse_args();c=a.campaign.resolve();m=json.loads((c/'manifest.json').read_text())
    if m['phase']!='basket-lvs-guard' or len(m['jobs'])!=2 or {v.get('voluntary_guard') for v in m['variants'].values()}!={True,False}:raise ValueError('Require one native guard pair')
    lock=(c/'guard_report.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:print('Existing guard collector owns lock');return
    u,t=native.credentials(native.ROOT/'data/S001.duckdb');progress=[];audits=[];errors=[]
    for name in m['jobs']:
        key,cfg=shared.config_for(name,m)
        with native.storage.connect(f'file:{native.ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as db:
            db.row_factory=native.storage.Row;saved=db.execute('SELECT * FROM backtest_queue WHERE name=?',(name,)).fetchone()
        if saved is None:progress.append(dict(name=name,status='dry_run_not_queued'));continue
        row=dict(saved);proof=source_proof(c,key,cfg,row)
        if not row.get('backtest_id'):progress.append(dict(name=name,status=row['status']));continue
        try:
            response=shared.read_research_backtest(u,t,c,name,row);full=response['backtest'];native.validate_identity(full,row)
            progress.append(dict(name=name,status=full.get('status'),completed=full.get('completed'),backtest_id=row['backtest_id']))
            if native.terminal_status(full) is None:continue
            folder=shared.collect_terminal(u,t,c,name,row,response);orders=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text());rust=rust['orders'] if isinstance(rust,dict) else rust
            if cfg['voluntary_guard']:result,attempts,events=audit_guard(orders,rust,full)
            else:
                receipts=native.events((folder/'cloud.log').read_text(),'LVS_EXIT_RECEIPT');result=native.audit_attempt(orders,rust,full,False,native.gold_orders(),receipts);attempts,events,_=native.native_records(orders)
            result.update(variant=key,project_id=row['project_id'],backtest_id=row['backtest_id'],source_proof=proof)
            out=folder/'guard_report';shared.write_tables(out,dict(native_attempts=attempts,native_events=events));native.atomic_json(out/'summary.json',result);audits.append(result)
        except Exception as e:errors.append(dict(name=name,error=type(e).__name__+': '+str(e),read_only_retry=True))
    valid=len(audits)==2 and not errors and all(r['native_execution_account_audit_passed'] for r in audits)
    result=dict(engineering_pair_verified=valid,strategy_performance_claim=False,progress=progress,collection_issues=errors,variants=audits)
    native.atomic_json(c/'guard_pair_summary.json',result);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
