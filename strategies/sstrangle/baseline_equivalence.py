"""Compare the optimized baseline's native economic fills with its frozen reference."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from insolvency_report import economic_signature
from qc_contracts import execution_rows

HERE=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('campaign',type=Path)
    args=parser.parse_args();campaign=args.campaign.resolve()
    reference=HERE/'results/strangle_basket_20261018_173739'
    def rows(path):
        manifest=json.loads((path/'manifest.json').read_text())
        if manifest['phase']!='basket' or len(manifest['jobs'])!=1:raise ValueError('Require one full basket')
        name=manifest['jobs'][0]
        return execution_rows(json.loads((path/name/'orders.json').read_text()))
    expected=rows(reference);actual=rows(campaign)
    left=economic_signature(expected);right=economic_signature(actual)
    differences=[dict(index=i,reference=a,optimized=b) for i,(a,b) in enumerate(zip(left,right)) if a!=b]
    result=dict(utc=datetime.now(timezone.utc).isoformat(),reference_campaign=str(reference),
        optimized_campaign=str(campaign),reference_actual_fills=len(left),optimized_actual_fills=len(right),
        all_native_economic_fills_identical=len(left)==len(right) and not differences,
        compared_fields=list(left[0]),difference_count=len(differences),first_differences=differences[:20],
        limitation='Identical observed execution through insolvency does not supply observations after bankruptcy or independently validate vendor quotes')
    (campaign/'baseline_equivalence.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='first_differences'},indent=2))
    if not result['all_native_economic_fills_identical']:raise ValueError('Optimized native economic fills diverged from preserved reference')


if __name__=='__main__':main()
