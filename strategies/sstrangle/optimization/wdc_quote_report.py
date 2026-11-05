"""Read-only native WDC quote-gate diagnostic collector; no Calmar claim."""
import argparse
import ast
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('_wdc_native',HERE/'lvs_exit_report.py')
native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
shared=native.shared
SOURCE=native.STRATEGY/'results/strangle_basket-calmar_20261019_150331/SSTRANGLE_20261019_150331_cap20_stop1_exit28'
IDS=(861,862,865,866,869,870)
INITIAL=39557.74
FIELDS=('observations','cache_present','cache_fresh_real','slice_present','slice_fresh_real',
    'zero_bid','positive_ask','positive_bid','strict_pass','buyback_pass','cache_stale',
    'cache_fill_forward','slice_fill_forward','clock_matches','product_open','held_short_one')


def gold_orders():
    full=json.loads((SOURCE/'backtest.json').read_text())['backtest']
    if full['backtestId']!='3d5fefa21dd61cc75b1a5c579c390c3c' or str(full['projectId'])!='31338456':
        raise ValueError('Wrong native WDC source identity')
    rows=[o for o in json.loads((SOURCE/'orders.json').read_text()) if o['id'] in IDS]
    if [o['id'] for o in rows]!=list(IDS):raise ValueError('Missing genuine WDC gold orders')
    return rows


def source_proof(campaign,row,config,key='wdc_quote'):
    path=campaign/(key+'.py');source=path.read_text();extras=json.loads((campaign/'extra_files.json').read_text())
    queued=json.loads(row['extra_files']) if isinstance(row['extra_files'],str) else row['extra_files']
    if source!=row['code'] or extras!=queued:raise ValueError('Queued source mismatch')
    frozen=native.STRATEGY/'results/strangle_basket_20261018_191012'
    original=json.loads((frozen/'extra_files.json').read_text())
    for k in ('rules.py','execution_base.py','basket_rules.py','terminal_margin.py','premium_units.py','premium_filter.py'):
        if extras.get(k)!=original[k]:raise ValueError('Original execution dependency changed: '+k)
    if extras.get('basket_strategy.py')!=(frozen/'basket.py').read_text():raise ValueError('Original native basket changed')
    configs=[ast.literal_eval(n.value) for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='CONFIG' for t in n.targets)]
    if configs!=[config]:raise ValueError('Wrong native fixture configuration')
    if key=='wdc_history':
        parent=native.STRATEGY/'results/strangle_basket-wdc-quote_20261019_162136/wdc_quote.py'
        if extras.get('wdc_original_fixture.py')!=parent.read_text():raise ValueError('Verified WDC execution parent changed')
        methods={n.name for n in ast.walk(ast.parse(source)) if isinstance(n,ast.FunctionDef)}
        if methods!={'history_summary','on_end_of_algorithm'}:raise ValueError('History probe changed trading methods')
        if source.count('self.history[QuoteBar]')!=1 or 'fill_forward=False' not in source:
            raise ValueError('Unexpected retrospective history call')
    elif 'self.history' in source:raise ValueError('Quote-only fixture unexpectedly requests history')
    for call in ('set_fill_model(', 'set_buying_power_model(', 'set_margin_call_model('):
        if call in source:raise ValueError('Forbidden diagnostic mutation/export: '+call)
    return dict(queued_source_identical=True,original_default_execution_unchanged=True,
        main_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),extras_sha256=hashlib.sha256((campaign/'extra_files.json').read_bytes()).hexdigest())


def audit(orders,rust,full):
    attempts,events,issues=native.native_records(orders);ra,re,ri=native.native_records(rust);issues+=ri
    if attempts!=ra or events!=re:issues.append('Rust/Python complete native events differ')
    _,gold,gi=native.native_records(gold_orders());issues+=gi
    fills=[e for e in events if e['quantity']];gold_fills=[e for e in gold if e['quantity']]
    if native.economics(fills[:6])!=native.economics(gold_fills):issues.append('Original six native economic fills differ')
    if len(orders) not in (6,8) or len(fills)!=len(orders):issues.append('Unexpected actual order/fill count')
    for o in orders:
        if o['status']!=3 or float(o['quantity'])!=sum(e['quantity'] for e in events if e['order_id']==o['id']):
            issues.append('Incomplete native order')
    if int(str(full.get('statistics',{}).get('Total Orders',-1)).replace(',',''))!=len(orders):issues.append('Declared order count mismatch')
    quantities=Counter();allowed={e['native_sid'] for e in gold_fills}
    for e in sorted(events,key=lambda x:(x['utc'],x['order_id'],x['event_id'])):
        if e['native_sid'] not in allowed:issues.append('Unexpected native contract')
        quantities[e['native_sid']]+=e['quantity']
        if quantities[e['native_sid']]>1e-9:issues.append('Native event path overclosed')
    residual={k:v for k,v in quantities.items() if v}
    rt=full.get('runtimeStatistics',{});counts={}
    for side in ('put','call'):
        try:
            vector=json.loads(rt['wdc_'+side])
            if len(vector)!=len(FIELDS) or any(type(x)is not int or x<0 for x in vector):raise ValueError()
            counts[side]=dict(zip(FIELDS,vector));n=counts[side]['observations']
            if n<=0 or any(x>n for x in vector):raise ValueError()
            if counts[side]['clock_matches']!=n or counts[side]['held_short_one']!=n:issues.append('Diagnostic clocks/holdings differ')
        except (KeyError,ValueError,TypeError):issues.append('Missing or invalid aggregate '+side+' quote predicates')
    supported=all(e['price'] is not None and e['fee'] is not None for e in fills)
    cashflow=sum(-e['quantity']*e['price']*100 for e in fills) if supported else None
    fees=sum(e['fee'] for e in events if e['fee'] is not None)
    try:
        cash=float(rt['wdc_cash']);equity=float(rt['wdc_equity'])
        if not all(math.isfinite(v) for v in (cash,equity,fees)):raise ValueError('Nonfinite account')
        if cashflow is None or abs(cash-INITIAL-cashflow+fees)>.0051:issues.append('Actual cash/fees do not reconcile')
        exact=shared.money(full['totalPerformance']['portfolioStatistics']['endEquity'])
        if abs(exact-equity)>.0051:issues.append('Native exact account equity mismatch')
        if int(rt['wdc_native_matched'])!=6 or int(rt['wdc_residual_count'])!=len(residual):issues.append('Native runtime residual/path mismatch')
    except (KeyError,ValueError,TypeError):cash=equity=None;issues.append('Missing account/path evidence')
    if len(fills)==6:
        expected=Counter()
        for e in gold_fills:expected[e['native_sid']]+=e['quantity']
        if residual!={k:v for k,v in expected.items() if v}:issues.append('Original residual pair differs')
        if rt.get('wdc_closed_at')!='None':issues.append('Residual pair falsely claimed closed')
    else:
        if residual:issues.append('Eight-fill path left real residuals')
        for e in fills[6:]:
            local=shared.ny_time(e['utc'])
            if e['quantity']!=1 or local.date().isoformat()!='2019-04-22' or local.hour<12:issues.append('Unexpected native TIME close')
        for o in orders[6:]:
            if o['type']!=8 or o.get('tag','').split(';')[0].split(':')[-1]!='TIME':issues.append('Unexpected closing order type/reason')
    if native.terminal_status(full)!='done':issues.append('Diagnostic cloud failure')
    valid=not issues
    return dict(engineering_diagnostic_verified=valid,issues=list(dict.fromkeys(issues)),strategy_performance_claim=False,
        full_strategy_calmar=None,native_orders=len(orders),native_fills=len(fills),fees=fees,actual_cashflow=cashflow,
        account_cash=cash,ending_equity=equity,residual_native_quantities=residual,quote_predicate_counts=counts,
        original_missing_exit_reproduced=valid and len(fills)==6,
        limitation='Exact isolated WDC holdings/clock/gate reproduction only; no raw quotes exported or synthetic liquidation.'),attempts,events


def audit_history(result,full):
    fields=('bars','same_session','minute','fill_forward','future','positive_bid','positive_ask','noncrossed')
    counts={};issues=[];rt=full.get('runtimeStatistics',{})
    for side in ('put','call'):
        for label in ('prior','due'):
            key=side+'_'+label
            try:
                values=json.loads(rt['wdch_'+key])
                if len(values)!=len(fields) or any(type(x)is not int or x<0 for x in values):raise ValueError()
                d=dict(zip(fields,values));n=d['bars']
                if any(x>n for x in values) or d['same_session']!=n or d['minute']!=n or d['fill_forward'] or d['future']:raise ValueError()
                counts[key]=d
            except (KeyError,ValueError,TypeError):issues.append('Invalid bounded history predicates: '+key)
    if rt.get('wdch_unchanged')!='1':issues.append('History account/order immutability not established')
    valid=result['engineering_diagnostic_verified'] and not issues
    diagnosis='inconclusive'
    if valid and all(counts[s+'_prior']['bars']>0 and counts[s+'_due']['bars']==0 for s in ('put','call')):
        diagnosis='Prior-session real quotes available; mandatory-session native quote history empty for both held legs'
    elif valid and all(counts[s+'_due']['bars']>0 for s in ('put','call')):
        diagnosis='Native mandatory-session quote history exists; investigate live stream/cache configuration'
    result.update(engineering_diagnostic_verified=valid,history_availability_counts=counts,
        retrospective_history_diagnosis=diagnosis,history_diagnostic_issues=issues)
    result['issues']+=issues
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('campaign',type=Path);args=parser.parse_args();c=args.campaign.resolve()
    m=json.loads((c/'manifest.json').read_text())
    if m['phase'] not in ('basket-wdc-quote','basket-wdc-history') or len(m['jobs'])!=1:raise ValueError('Wrong campaign')
    key='wdc_history' if m['phase']=='basket-wdc-history' else 'wdc_quote'
    name=m['jobs'][0]
    with native.storage.connect(f'file:{native.ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as db:
        db.row_factory=native.storage.Row;saved=db.execute('SELECT * FROM backtest_queue WHERE name=?',(name,)).fetchone()
    if saved is None:print(json.dumps(dict(status='dry_run_not_queued',qualified=False)));return
    row=dict(saved);proof=source_proof(c,row,m['variants'][key],key)
    if not row.get('backtest_id'):print(json.dumps(dict(status=row['status'],name=name)));return
    u,t=native.credentials(native.ROOT/'data/S001.duckdb');response=shared.read_research_backtest(u,t,c,name,row);full=response['backtest'];native.validate_identity(full,row)
    if native.terminal_status(full) is None:print(json.dumps(dict(status=full.get('status'),backtest_id=row['backtest_id'])));return
    folder=shared.collect_terminal(u,t,c,name,row,response)
    orders=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text());rust=rust['orders'] if isinstance(rust,dict) else rust
    result,attempts,events=audit(orders,rust,full)
    if key=='wdc_history':result=audit_history(result,full)
    result.update(backtest_id=row['backtest_id'],project_id=row['project_id'],source_proof=proof)
    out=c/'wdc_quote_report';shared.write_tables(out,dict(native_attempts=attempts,native_events=events));native.atomic_json(out/'summary.json',result);print(json.dumps(result,indent=2))


if __name__=='__main__':main()
