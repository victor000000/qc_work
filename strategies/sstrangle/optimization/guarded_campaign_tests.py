"""Check the actual frozen full-campaign render before it can be queued."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
CAMPAIGN=ROOT/'results/strangle_basket-calmar_20261019_163019'


def test_actual_render_uses_guard_implementation_and_retains_user_exit_rule():
    m=json.loads((CAMPAIGN/'manifest.json').read_text());cfg=m['variants']['cap20_stop1_guard_exit21']
    assert cfg['voluntary_spread_guard'] is True and cfg['time_exit_dte']==21
    assert cfg['initial_cash']==60000 and cfg['lookback']==504
    assert cfg['start']==[2012,1,3] and cfg['end']==[2026,9,30]
    source=(CAMPAIGN/'cap20_stop1_guard_exit21.py').read_text()
    assert source==(HERE/'guarded_main.py').read_text().replace('CONFIG = {}','CONFIG = '+repr(cfg),1)
    assert 'voluntary_market_buyback_guard' in source
    spec=importlib.util.spec_from_file_location('_full_guard_source_audit',HERE/'report.py')
    report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)
    extras=(CAMPAIGN/'extra_files.json').read_text()
    proof=report.verify_frozen_source(CAMPAIGN,'cap20_stop1_guard_exit21',cfg,dict(code=source,extra_files=extras,code_hash='dry-render-only'))
    assert proof['queued_code_and_helpers_identical']


def test_rendered_helpers_are_the_same_native_verified_execution_and_no_baseline_change():
    extra=json.loads((CAMPAIGN/'extra_files.json').read_text())
    original=json.loads((ROOT/'results/strangle_basket_20261018_191012/extra_files.json').read_text())
    for name in ('execution_base.py','rules.py','basket_rules.py','terminal_margin.py','premium_units.py','premium_filter.py'):
        assert extra[name]==original[name]
    assert extra['voluntary_quote_guard.py']==(HERE/'voluntary_quote_guard.py').read_text()
    assert hashlib.sha256((ROOT/'basket/main.py').read_bytes()).hexdigest()=='430c1186b7d049ee3adf91b229602d71518d3dd6b5728cf4afa4a24b5b78bf6c'
