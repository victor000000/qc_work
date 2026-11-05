"""Review a concrete native-probe render before queue submission."""
import ast,json,hashlib
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
CAMPAIGN=ROOT/'results/strangle_basket-volatility-source_20261019_174228'
@pytest.mark.parametrize('key,probe',[('vol_equity','equity'),('vol_futures','futures')])
def test_frozen_render_and_dependency(key,probe):
 m=json.loads((CAMPAIGN/'manifest.json').read_text());cfg=m['variants'][key]
 assert cfg==dict(engineering_smoke=True,probe=probe)
 assert (CAMPAIGN/(key+'.py')).read_text()==(ROOT/'optimization/volatility_source_fixture.py').read_text().replace('CONFIG = {}','CONFIG = '+repr(cfg),1)
 extras=json.loads((CAMPAIGN/'extra_files.json').read_text())
 assert extras=={'completed_volatility.py':(ROOT/'optimization/completed_volatility.py').read_text()}
 assert m['evidence_only'] and len(m['jobs'])==2 and m['phase']=='basket-volatility-source'

def test_actual_no_trade_probe_and_source_guards():
 s=(ROOT/'optimization/volatility_source_fixture.py').read_text();tree=ast.parse(s)
 calls=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='self']
 assert not any(n in calls for n in ['market_order','combo_market_order','set_holdings','liquidate','save'])
 assert s.count("self.plot('Trading period','Equity',float(self.portfolio.total_portfolio_value))")==1
 assert 'DataNormalizationMode.SCALED_RAW' in s and 'DataNormalizationMode.RAW' in s
 assert 'fill_forward=False' in s and 'data_normalization_mode=mode' in s
 assert 'if bar.symbol!=symbol' in s and 'if bar.is_fill_forward' in s
 assert 'if end>asof' in s and 'if end.date()>=self.time.date()' in s
 assert 'np.std(returns[-20:],ddof=1)' in s and 'np.std(returns,ddof=1)' in s
 assert 'futures_chain(self.canonical)' in s and 'native_delivery_resets' in s
 assert 'actual_split_events' in s and 'split_basis_verified' in s
 assert 'synthetic arithmetic input, never a market IV' in s
 assert s.count("self.log('VOLATILITY_SOURCE_CHECKSUM '+self.digest.hexdigest())")==1
 assert 'self.portfolio.invested' in s and 'list(self.transactions.get_orders())' in s

def test_baseline_source_unchanged():
 assert hashlib.sha256((ROOT/'basket/main.py').read_bytes()).hexdigest()=='430c1186b7d049ee3adf91b229602d71518d3dd6b5728cf4afa4a24b5b78bf6c'
