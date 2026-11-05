"""A green source probe requires all intended methods and an untouched account."""
from copy import deepcopy
import pytest
from equity_rv_gate_report import audit


def fixture():
    counts = dict(gate_pass_reject_pairs=12, verified_future_bypasses=3,
                  unsubscribed_symbol_windows=9, equity_rv_history_requests=36,
                  equity_rv_admitted=12, equity_iv_rv_below_threshold=12,
                  equity_rv_future_bypasses=3, synthetic_IV=1, no_trades=1)
    rt = {'Equity': '$60,000', 'Fees': '$0', 'Holdings': '$0', 'Unrealized': '$0'}
    rt.update({'rv_gate_' + k: str(v) for k, v in counts.items()})
    return dict(statistics={'Total Orders': '0'}, runtimeStatistics=rt)


def test_full_method_probe_is_engineering_evidence_only():
    r = audit(fixture(), [], [], 'EQUITY_RV_GATE_CHECKSUM ' + 'a' * 64)
    assert r['actual_strategy_methods_verified']
    assert not r['market_iv_gate_performance_proven'] and not r['strategy_calmar_proven']


@pytest.mark.parametrize('field', ['unsubscribed_symbol_windows', 'verified_future_bypasses',
                                  'gate_pass_reject_pairs', 'equity_rv_history_requests'])
def test_partial_source_coverage_cannot_pass(field):
    f = deepcopy(fixture()); f['runtimeStatistics']['rv_gate_' + field] = '0'
    with pytest.raises(ValueError):
        audit(f, [], [], 'EQUITY_RV_GATE_CHECKSUM ' + 'a' * 64)


def test_orders_or_changed_account_cannot_pass():
    log = 'EQUITY_RV_GATE_CHECKSUM ' + 'a' * 64
    with pytest.raises(ValueError): audit(fixture(), [{'id': 1}], [], log)
    f = fixture(); f['runtimeStatistics']['Equity'] = '$59,999'
    with pytest.raises(ValueError): audit(f, [], [], log)
