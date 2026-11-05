"""Execute actual research decision expressions without a LEAN installation."""
import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import pytest

TREE=ast.parse(Path(__file__).with_name('main.py').read_text())
CLASS=next(n for n in TREE.body if isinstance(n,ast.ClassDef) and n.name=='ResearchShortStrangle')
NOON=next(n for n in CLASS.body if isinstance(n,ast.FunctionDef) and n.name=='on_data')
REASON=next(n.value for n in ast.walk(NOON) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='reason' for t in n.targets))

@pytest.mark.parametrize('threshold,dte,wanted',[(21,28,None),(21,22,None),(21,21,'TIME'),(28,29,None),(28,28,'TIME'),(28,21,'TIME')])
def test_actual_noon_time_boundary(threshold,dte,wanted):
    obj=SimpleNamespace(time_exit_dte=threshold,end=date(2026,9,30),states={'x':{}})
    code=compile(ast.Expression(REASON),'<actual research reason>','eval')
    assert eval(code,{'self':obj,'today':date(2019,11,22),'dte':dte,'key':'x'})==wanted

def test_original_baseline_keeps_21dte():
    import hashlib
    baseline=Path(__file__).parents[1]/'basket/main.py'
    assert hashlib.sha256(baseline.read_bytes()).hexdigest()=='430c1186b7d049ee3adf91b229602d71518d3dd6b5728cf4afa4a24b5b78bf6c'
