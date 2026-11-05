import json
import pytest
from runtime_export import bounded_statistics

def test_full_diagnostic_counts_round_trip_under_native_limit():
    from pathlib import Path
    import ast
    p=Path(__file__).parents[2]/'results/qc_three_demo_poc_20261023/condor_full_v1.py'
    tree=ast.parse(p.read_text())
    keys={n.slice.value for n in ast.walk(tree) if isinstance(n,ast.Subscript) and isinstance(n.value,ast.Attribute) and n.value.attr=='counts' and isinstance(n.slice,ast.Constant) and isinstance(n.slice.value,str)}
    # Dynamic categories cover missing, stale, crossed and combined wing failures.
    keys|={'wing_reason_'+a+'_'+b for a in ['ok','absent','age','crossed'] for b in ['ok','absent','age','crossed']}
    counts={k:i for i,k in enumerate(sorted(keys))}
    core={f'account_{i}':str(i) for i in range(18)}
    result=bounded_statistics(core,counts,{str(y):1000 for y in range(2022,2027)})
    decoded={k:int(v) for k,v in result.items() if k in counts}
    for i in range(1,int(result['counts_chunks'])+1):decoded.update(json.loads(result[f'counts_{i:02d}']))
    assert decoded==counts and len(result)<=50

def test_quota_overflow_fails_instead_of_silently_losing_evidence():
    with pytest.raises(ValueError):bounded_statistics({str(i):'x' for i in range(51)},{},{})
    with pytest.raises(ValueError):bounded_statistics({'x':'a'*201},{},{})
