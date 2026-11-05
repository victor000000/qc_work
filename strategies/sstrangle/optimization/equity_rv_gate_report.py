"""Collect the actual equity admission-method probe; never submit jobs."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import report as shared


def audit(full, orders, rust, log):
    if orders or rust or int(full['statistics']['Total Orders']) != 0:
        raise ValueError('Admission-method probe traded')
    rt = full['runtimeStatistics']
    if shared.money(rt['Equity']) != 60000 or any(
            shared.money(rt[key]) != 0 for key in ['Fees', 'Holdings', 'Unrealized']):
        raise ValueError('Admission-method account changed')
    expected = dict(gate_pass_reject_pairs=12, verified_future_bypasses=3,
                    unsubscribed_symbol_windows=9, equity_rv_history_requests=36,
                    equity_rv_admitted=12, equity_iv_rv_below_threshold=12,
                    equity_rv_future_bypasses=3)
    counts = {key: int(rt.get('rv_gate_' + key, '0')) for key in expected}
    if counts != expected:
        raise ValueError('Native admission-method coverage differs: ' + repr(counts))
    if rt.get('rv_gate_synthetic_IV') != '1' or rt.get('rv_gate_no_trades') != '1':
        raise ValueError('Missing synthetic-IV/no-trade disclosure')
    hashes = re.findall(r'EQUITY_RV_GATE_CHECKSUM ([0-9a-f]{64})(?![0-9a-z])', log)
    if len(hashes) != 1 or hashes[0] == hashlib.sha256().hexdigest():
        raise ValueError('Missing unique source-method fingerprint')
    return dict(actual_strategy_methods_verified=True, market_iv_gate_performance_proven=False,
                strategy_calmar_proven=False, actual_orders=0, actual_fills=0,
                actual_fees=0, ending_equity=60000, aggregate_counts=counts,
                fingerprint=hashes[0], synthetic_iv=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign', type=Path)
    campaign = parser.parse_args().campaign.resolve()
    manifest = json.loads((campaign / 'manifest.json').read_text())
    if manifest['phase'] != 'basket-equity-rv-gate' or len(manifest['jobs']) != 1:
        raise ValueError('Wrong admission-method campaign')
    lock = (campaign / 'equity_rv_report.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('Another admission-method collector owns this campaign')
        return
    name = manifest['jobs'][0]
    code = (campaign / 'equity_rv_gate.py').read_text()
    extra = json.loads((campaign / 'extra_files.json').read_text())
    with shared.storage.connect(f'file:{shared.ROOT}/data/SSTRANGLE.duckdb?mode=ro', uri=True) as conn:
        conn.row_factory = shared.storage.Row
        row = dict(conn.execute('select * from backtest_queue where name=?', (name,)).fetchone())
    queued = json.loads(row['extra_files']) if isinstance(row['extra_files'], str) else row['extra_files']
    if row['code'] != code or queued != extra:
        raise ValueError('Queued admission source differs from frozen source')
    required = {'completed_volatility.py', 'equity_rv_features.py', 'equity_rv_strategy.py'}
    if not required.issubset(extra):
        raise ValueError('Missing actual strategy dependencies')
    if not row['backtest_id']:
        print(json.dumps({k: row[k] for k in ['name', 'status', 'project_id', 'backtest_id']}))
        return
    user, token = shared.credentials(shared.ROOT / 'data/S001.duckdb')
    response = shared.read_research_backtest(user, token, campaign, name, row)
    full = response['backtest']
    shared.validate_identity(full, row)
    status = shared.terminal_status(full)
    if status is None:
        print(json.dumps({k: full.get(k) for k in ['backtestId', 'status', 'completed', 'progress']}))
        return
    folder = shared.collect_terminal(user, token, campaign, name, row, response)
    result = dict(status=status, error=full.get('error'), backtest_id=row['backtest_id'],
                  strategy_calmar_proven=False,
                  source_sha256=hashlib.sha256(code.encode()).hexdigest(),
                  helpers_sha256=hashlib.sha256((campaign / 'extra_files.json').read_bytes()).hexdigest())
    if status == 'done':
        orders = json.loads((folder / 'orders.json').read_text())
        rust = json.loads((folder / 'orders.rust.json').read_text())
        rust = rust['orders'] if isinstance(rust, dict) else rust
        result.update(audit(full, orders, rust, (folder / 'cloud.log').read_text()))
        shared.write_tables(folder / 'equity_rv_report', dict(aggregate_counts=[
            dict(metric=k, value=v) for k, v in result['aggregate_counts'].items()]))
    shared.atomic_json(campaign / 'equity_rv_gate_summary.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
