"""Exercise the actual pure functions embedded in the uploaded QC algorithm."""
import ast,math
from datetime import date,timedelta
from pathlib import Path

def namespace():
 tree=ast.parse((Path(__file__).parent/'strategy.py').read_text())
 nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['feature_value','rule_pass']]
 scope=dict(math=math,date=date,timedelta=timedelta)
 exec(compile(ast.Module(body=nodes,type_ignores=[]),'uploaded_feature_functions','exec'),scope)
 return scope

def test_uploaded_function_excludes_decision_day_and_future():
 fn=namespace()['feature_value'];rows=[['2024-01-02',103.,99.,100.,1000],['2024-01-03',1e12,0.,1.,10],['2024-01-04',1e15,0.,1.,1]]
 assert fn(rows,'2024-01-03','gld_range_pct')==(.04,'2024-01-02')
 assert fn(rows[:1],'2024-01-03','gld_range_pct')==fn(rows,'2024-01-03','gld_range_pct')
 assert fn(rows[:1],'2024-01-10','gld_range_pct')==(None,'2024-01-02')

def test_uploaded_threshold_equality_and_missing():
 fn=namespace()['rule_pass'];assert fn(.04,.04,'below');assert not fn(.04,.04,'above');assert not fn(None,.04,'below')
