import importlib.util
import json
from pathlib import Path
spec=importlib.util.spec_from_file_location('early',Path(__file__).with_name('wag_early_report.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_original_failed21dte_control_cannot_qualify_as28dte_success():
    folder=Path(__file__).parents[1]/'results/strangle_basket-wag-regression_20261019_142652/SSTRANGLE_20261019_142652_wag_control'
    orders=json.loads((folder/'orders.json').read_text());full=json.loads((folder/'backtest.json').read_text())['backtest']
    result,fills=m.audit(orders,orders,full)
    assert not result['verified']
    assert 'Actual residual holdings' in result['issues']
    assert 'Missing exact28DTE noon buybacks' in result['issues']
    assert 'Cloud not cleanly completed' in result['issues']
    assert len(fills)==4
