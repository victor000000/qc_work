import ast,json
from pathlib import Path
import pytest
from volatility_source_report import audit_roots
ROOT=Path(__file__).resolve().parents[1]
CAMPAIGN=ROOT/'results/strangle_basket-volatility-roots_20261019_175112'
ROOTS=['CL','RB','HO','NG','ZN','ZT','ZB','ZC','ZS','ZW','NQ','ES','HG','GC','SI']
def test_exact_all_root_native_render_uses_verified_parent():
 m=json.loads((CAMPAIGN/'manifest.json').read_text());cfg=m['variants']['vol_all_roots']
 assert cfg['roots']==ROOTS and cfg['probe']=='futures' and m['evidence_only']
 assert (CAMPAIGN/'vol_all_roots.py').read_text()==(ROOT/'optimization/volatility_all_roots_fixture.py').read_text().replace('CONFIG = {}','CONFIG = '+repr(cfg),1)
 extras=json.loads((CAMPAIGN/'extra_files.json').read_text())
 assert extras['volatility_original_fixture.py']==(ROOT/'results/strangle_basket-volatility-source_20261019_174306/vol_futures.py').read_text()
 assert extras['completed_volatility.py']==(ROOT/'optimization/completed_volatility.py').read_text()

def test_all_roots_and_all_native_windows_must_reconcile():
 rt={'vol_root_'+r:'6' for r in ROOTS};assert len(audit_roots(rt,ROOTS,90))==15
 with pytest.raises(ValueError):audit_roots(rt,ROOTS[:-1],84)
 with pytest.raises(ValueError):audit_roots(rt,ROOTS,91)
 rt['vol_root_CL']='0'
 with pytest.raises(ValueError):audit_roots(rt,ROOTS,84)

def test_no_new_trading_or_source_price_mutation():
 s=(ROOT/'optimization/volatility_all_roots_fixture.py').read_text();tree=ast.parse(s)
 calls=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
 assert not any(n in calls for n in ['market_order','combo_market_order','set_holdings','set_fill_model','set_buying_power_model','set_margin_call_model'])
 assert 'self.probe_symbol(symbol)' in s and "self.counts['root_'+self.symbol_to_root[symbol]]+=1" in s
 assert "len(set(str(s.id) for s in selected))!=2" in s


def test_calendar_failure_remains_fatal_and_exports_only_label_metadata():
 s=(ROOT/'optimization/volatility_all_roots_fixture.py').read_text()
 assert 'except RuntimeError as error:' in s and "raise RuntimeError('Native daily calendar metadata '" in s
 assert 'source_last_start=str(last[-1].time)' in s and 'source_last_end=str(last[-1].end_time)' in s
 assert 'price=' not in s and 'volume=' not in s and 'iv=' not in s
