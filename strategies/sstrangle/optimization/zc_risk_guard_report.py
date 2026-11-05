"""Read-only native ZC control/guard-retry execution audit. Never submits jobs."""
import argparse
import ast
from collections import Counter
from datetime import date, datetime
import fcntl
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import report as shared
from account_drawdown import chart_drawdown

FROZEN = HERE.parent / 'results/strangle_basket-calmar_20261019_163122'
GOLD = FROZEN / 'SSTRANGLE_20261019_163122_cap20_stop1_guard_exit21/orders.json'
GOLD_IDS = {569, 570, 571, 572, 573, 574, 579, 580, 581, 582}
INITIAL = 56740.79


def economic(rows):
    keys = ('timestamp', 'strategy_key', 'reason', 'symbol_id', 'quantity', 'qc_price', 'multiplier', 'fee')
    return sorted([tuple(row[k] for k in keys) for row in rows])


def source_proof(campaign, key, config, row):
    source = (campaign / (key + '.py')).read_text()
    extras = json.loads((campaign / 'extra_files.json').read_text())
    queued = json.loads(row['extra_files']) if isinstance(row['extra_files'], str) else row['extra_files']
    if source != row['code'] or queued != extras:
        raise ValueError('Actual queued ZC source/helpers differ from frozen campaign')
    configs = [ast.literal_eval(n.value) for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'CONFIG' for t in n.targets)]
    if configs != [config] or type(config.get('cross_asset_voluntary_guard')) is not bool:
        raise ValueError('Unexpected native fixture configuration')
    if key not in ('zc_control','zc_guard_retry') or config['cross_asset_voluntary_guard'] is not (key == 'zc_guard_retry'):
        raise ValueError('Native ZC control/candidate policy identity is reversed or absent')
    if config.get('stop_multiple') != 1 or config.get('risk_interval_minutes') != 15:
        raise ValueError('Fixture changed declared stop threshold or interval')
    original = json.loads((FROZEN / 'extra_files.json').read_text())
    for name, value in original.items():
        if extras.get(name) != value:
            raise ValueError('Preserved execution dependency changed: ' + name)
    if extras['guarded_control_strategy.py'] != (FROZEN / 'cap20_stop1_guard_exit21.py').read_text():
        raise ValueError('ZC control is not the preserved full strategy')
    receipts = {name: json.loads((campaign / name).read_text()) for name in (
        'equity_rv_source_receipt_20261019.json', 'risk_retry_source_receipt_20261019.json',
        'cross_asset_guard_source_receipt_20261019.json')}
    equity, retry, cross = receipts.values()
    if (hashlib.sha256(extras['guarded_control_strategy.py'].encode()).hexdigest() != equity['parent_sha256']
            or equity['generated_sha256'] != retry['parent_sha256']
            or retry['generated_sha256'] != cross['parent_sha256']
            or hashlib.sha256(extras['cross_asset_candidate_strategy.py'].encode()).hexdigest() != cross['generated_sha256']):
        raise ValueError('Prospective source transformation chain differs')
    def methods(text):
        c = next(n for n in ast.parse(text).body if isinstance(n, ast.ClassDef) and n.name == 'ResearchShortStrangle')
        return {n.name: ast.dump(n, include_attributes=False) for n in c.body if isinstance(n, ast.FunctionDef)}
    a, b = methods(extras['guarded_control_strategy.py']), methods(extras['cross_asset_candidate_strategy.py'])
    changed = {k for k in a if a[k] != b.get(k)}
    if changed != {'initialize', 'prepare_day', 'intraday_risk_exits', 'voluntary_quote_ready', 'process_exit_requests'} or set(b)-set(a) != {'equity_rv_for', 'admit_equity_rv'}:
        raise ValueError('Candidate changed undeclared native strategy methods')
    for text in (source, extras['cross_asset_buyback_guard.py'], extras['fresh_risk_slots.py']):
        if any(needle in text for needle in ('set_fill_model(', 'set_buying_power_model(', 'set_margin_call_model(')):
            raise ValueError('Fixture replaced a native execution/risk model')
    return dict(queued_source_and_helpers_identical=True, preserved_control_identical=True,
                main_sha256=hashlib.sha256(source.encode()).hexdigest(),
                extras_sha256=hashlib.sha256((campaign / 'extra_files.json').read_bytes()).hexdigest())


def audit(orders, rust, full, prospective, gold_orders):
    fills = shared.execution_rows(orders)
    if shared.execution_signature(fills) != shared.execution_signature(shared.execution_rows(rust)):
        raise ValueError('Actual Rust/Python ZC fills differ')
    gold = shared.execution_rows(gold_orders)
    if len(gold_orders) != 10 or {o['id'] for o in gold_orders} != GOLD_IDS:
        raise ValueError('Wrong preserved native ZC reference')
    if len(orders) != int(str(full['statistics']['Total Orders']).replace(',', '')) or len(fills) != len(orders):
        raise ValueError('Incomplete actual ZC order/fill export')
    if len(orders) not in (4, 6, 8, 10):
        raise ValueError('Unexpected ZC native action count')
    inventory = Counter()
    for order, fill in zip(sorted(orders, key=lambda o:o['id']), sorted(fills, key=lambda f:f['order_id'])):
        if order['status'] != 3 or abs(fill['quantity']) != 1 or abs(float(order['quantity'])-fill['quantity']) > 1e-9:
            raise ValueError('Rejected, partial or wrong-sized native ZC action')
        if fill['strategy_key'] != 'FUT_ZC' or fill['underlying_id'] != 'ZC WDW91DY3IAZP' or fill['multiplier'] != 5000:
            raise ValueError('ZC native delivery/multiplier identity mismatch')
        if fill['fee'] != 2.47:
            raise ValueError('Actual native fee differs from the fixed one-lot control')
        inventory[fill['symbol_id']] += fill['quantity']
        if not -1 <= inventory[fill['symbol_id']] <= 0:
            raise ValueError('Native ZC path overclosed or changed short quantity')
    if any(inventory.values()):
        raise ValueError('Actual ZC residual holdings')
    opening = [f for f in fills if f['reason'] == 'OPEN']
    if economic(opening) != economic([f for f in gold if f['reason'] == 'OPEN']):
        raise ValueError('Actual original ZC entry economics changed')
    closing = sorted([o for o in orders if o['tag'].split(';',1)[0].split(':',1)[1]
                      not in ('OPEN','ROLL')], key=lambda o:o['id'])
    if len(closing) != 2 or any(o['type'] != 0 or shared.order_group_id(o) >= 0 for o in closing):
        raise ValueError('ZC close must retain two genuine sequential market orders')
    closing_fills = {f['order_id']: f for f in fills if f['reason'] not in ('OPEN','ROLL')}
    submissions = [datetime.fromisoformat(o['time'].replace('Z','+00:00')) for o in closing]
    actual = [datetime.fromisoformat(closing_fills[o['id']]['timestamp']) for o in closing]
    if any(filled < submitted for filled,submitted in zip(actual,submissions)) or submissions[1] < actual[0]:
        raise ValueError('Sequential ZC close did not wait for each actual fill')
    if (max(actual)-min(submissions)).total_seconds() > 300:
        raise ValueError('Actual ZC closing fills exceeded five minutes')
    if not prospective and economic(fills) != economic(gold):
        raise ValueError('Control does not reproduce all ten genuine source fills')
    cycles = shared.audit_dte(orders)
    if len(cycles) != 1:
        raise ValueError('Expected one complete actual ZC cycle')
    cycle = cycles[0]
    if cycle['expiry'] != '2016-07-22' or cycle['entry_dte'] != 39 or cycle['rolls'] > 3:
        raise ValueError('Wrong actual ZC tenor or rolls')
    exited = shared.ny_time(cycle['exit'])
    if cycle['reason'] == 'TIME':
        if exited.date() != date(2016, 7, 1) or not shared.time(12) <= exited.time() <= shared.time(12, 5):
            raise ValueError('Native ZC TIME close missed first eligible21DTE noon')
    elif cycle['reason'] not in ('STOP', 'PROFIT') or cycle['exit_dte'] <= 21:
        raise ValueError('Unexpected or late actual voluntary ZC close')
    fees = sum(f['fee'] for f in fills)
    net = sum(-f['quantity'] * f['qc_price'] * f['multiplier'] - f['fee'] for f in fills)
    rt = full['runtimeStatistics']
    if (abs(shared.money(rt['Equity']) - INITIAL - net) > .0051
            or abs(abs(shared.money(rt['Fees'])) - fees) > .0051
            or any(shared.money(rt[k]) != 0 for k in ['Holdings', 'Unrealized'])
            or abs(float(rt['fixture_cycle_net']) - net) > .0051):
        raise ValueError('Actual ZC native cash/fees/terminal account mismatch')
    for key, expected in dict(fixture_replayed_entry='1', fixture_synthetic_fills='0',
                              fixture_calmar_claim='0', fixture_open_completed='1',
                              fixture_guard_and_retry=str(int(prospective))).items():
        if str(rt.get(key)) != expected:
            raise ValueError('Missing actual fixture proof: ' + key)
    if prospective and (int(rt.get('fixture_future_guard_checks','0')) <= 0
                        or int(rt.get('research_fresh_risk_evaluations','0')) <= 0):
        raise ValueError('Prospective native guard/fresh-evaluation path was not exercised')
    return dict(native_execution_account_audit_passed=True, native_orders=len(orders),
                actual_fills=len(fills), actual_fees=fees, native_single_cycle_pnl=net,
                ending_equity=INITIAL+net, original_entry_economics_equal=True,
                all_ten_control_fills_equal=not prospective, cycle=cycle,
                future_quote_deferrals=int(rt.get('fixture_future_quote_deferrals', '0')),
                fresh_risk_evaluations=int(rt.get('research_fresh_risk_evaluations', '0')),
                future_guard_checks=int(rt.get('fixture_future_guard_checks','0')),
                strategy_calmar_proven=False), fills


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('campaign', type=Path)
    c = p.parse_args().campaign.resolve(); m = json.loads((c/'manifest.json').read_text())
    if m['phase'] != 'basket-zc-risk-guard' or set(m['variants']) != {'zc_control','zc_guard_retry'} or set(m['source_order_ids']) != GOLD_IDS:
        raise ValueError('Wrong ZC native control/candidate campaign')
    if m.get('source_orders_sha256') != hashlib.sha256(GOLD.read_bytes()).hexdigest():
        raise ValueError('Preserved native reference orders differ from the frozen campaign')
    lock = (c/'zc_report.lock').open('a')
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('Another ZC collector owns this campaign'); return
    user, token = shared.credentials(shared.ROOT/'data/S001.duckdb')
    gold = [o for o in json.loads(GOLD.read_text()) if o['id'] in GOLD_IDS]
    results = {}; identities = []
    for name in m['jobs']:
        key, cfg = shared.config_for(name, m)
        with shared.storage.connect(f'file:{shared.ROOT}/data/SSTRANGLE.duckdb?mode=ro', uri=True) as conn:
            conn.row_factory = shared.storage.Row
            saved = conn.execute('select * from backtest_queue where name=?', (name,)).fetchone()
        if saved is None: raise ValueError('Missing frozen ZC queue identity')
        row = dict(saved); proof = source_proof(c,key,cfg,row)
        identities.append({k:row[k] for k in ['name','status','project_id','backtest_id']})
        if not row['backtest_id']:
            results[key] = dict(status=row['status']); continue
        response = shared.read_research_backtest(user,token,c,name,row); full = response['backtest']
        shared.validate_identity(full,row); status = shared.terminal_status(full)
        if status is None:
            results[key] = dict(status=full.get('status'), progress=full.get('progress'),backtest_id=row['backtest_id']); continue
        folder = shared.collect_terminal(user,token,c,name,row,response)
        r = dict(status=status, error=full.get('error'), backtest_id=row['backtest_id'],source_proof=proof)
        if status == 'done':
            orders = json.loads((folder/'orders.json').read_text()); rust = json.loads((folder/'orders.rust.json').read_text())
            rust = rust['orders'] if isinstance(rust,dict) else rust
            audited, fills = audit(orders,rust,full,cfg['cross_asset_voluntary_guard'],gold); r.update(audited)
            charts = []
            for filename in ('trading_period.json','strategy_equity.json'):
                if (folder/filename).exists():
                    charts.append(dict(source=filename,**chart_drawdown(json.loads((folder/filename).read_text()),INITIAL,date(2016,6,10),date(2016,7,5))))
            if not charts: raise ValueError('Actual ZC account drawdown chart unavailable')
            r['account_chart_drawdown_audits'] = charts
            shared.write_tables(folder/'zc_report',dict(executions=fills,cycles=[r['cycle']]))
        shared.atomic_json(folder/'zc_audit.json',r); results[key] = r
    passed = all(results.get(k,{}).get('native_execution_account_audit_passed') for k in m['variants'])
    result = dict(results=results, jobs=identities, paired_native_audit_passed=passed,
                  strategy_calmar_proven=False, engineering_only=True,
                  scope='Known native ZC entry/roll-identity replay; candidate combines two changes. No independent full opportunity path or factorial causal attribution.')
    shared.atomic_json(c/'zc_risk_guard_summary.json', result)
    print(json.dumps(result,indent=2))


if __name__ == '__main__': main()
