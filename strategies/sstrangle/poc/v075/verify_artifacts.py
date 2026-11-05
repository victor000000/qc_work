"""Verify v0.7.5 evidence hashes and documentation without modifying frozen runs."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'strategies/sstrangle/results/qc_design_poc_20261026_v075'
REPORT=ROOT/'strategies/sstrangle/research/design_20261026_v075'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    source=json.loads((OUT/'source_manifest.json').read_text())
    for r in source['sources']:
        assert sha(Path(r['path']))==r['sha256'],r['path']
    manifest=json.loads((REPORT/'manifest.json').read_text())
    for name,digest in manifest['files'].items():assert sha(REPORT/name)==digest,name
    result=json.loads((OUT/'review_results.json').read_text())
    for group in ['baseline_reproduction','final_candidate_reproduction']:
        assert set(result[group])=={'condor','strangle','put'}
        for r in result[group].values():
            assert r['max_episode_error']<1e-5 and r['residual_contracts']==0
            assert abs(r['native_account_pnl']-r['net_pnl'])<.01
    assert result['native_runs_started']==result['network_acquisition_requests']==0
    sample=result['provider_sample_admission']
    assert sample['rows']==46136 and sample['strict_quote_input_accepted']==0
    assert sample['rejection_counts']['unknown_quote_ts']==sample['rows']
    assert sample['rejection_counts']['unknown_available_at']==sample['rows']
    contract=json.loads((REPORT/'design_contract.json').read_text())
    assert len(contract['scope']['daily_context'])==7
    assert contract['scope']['option_surface_extension']==['QQQ']
    assert contract['scope']['execution_option_roots']==['SPXW']
    allfiles=list(Path(__file__).parent.glob('*.py'))+[Path(__file__).parent/'README.md']
    allfiles+=list(REPORT.glob('DESIGN_REPORT.*'))+[REPORT/'design_contract.json',REPORT/'build_report.py']
    allfiles+=[OUT/'review_results.json',OUT/'source_manifest.json',OUT/'provider_sampling_report_snapshot.json',OUT/'inherited_v07_comparison.csv']
    allfiles+=[ROOT/'docs/CURRENT_WORK.md',ROOT/'docs/TODO.md',ROOT/'strategies/sstrangle/README.md',Path('/home/vic/data_providers/docs/requirements/QC_0DTE_V075_ADDENDUM_20261026.md')]
    evidence={'version':'0.7.5','status':'passed_local_design_and_admission_poc','source_hashes_verified':len(source['sources']),
        'report_artifacts_verified':len(manifest['files']),
        'baseline_episodes_reconstructed':sum(r['episodes'] for r in result['baseline_reproduction'].values()),
        'candidate_episodes_reconstructed':sum(r['episodes'] for r in result['final_candidate_reproduction'].values()),
        'targeted_tests':{'command':'.venv/bin/python -m pytest strategies/sstrangle/poc/v075 strategies/sstrangle/poc/v07/test_feature_rule.py strategies/sstrangle/poc/v07/test_reproduction.py -q','passed':26,'evidence':'Executed during this revision; 26 passed in 0.36s. Artifact checker does not rerun tests.'},
        'pdf_validation':{'pages':6,'text_extracted_all_pages':True,'visual_review_pages':[1,5]},
        'independent_spxw_execution_validated':False,'new_native_runs':0,'robust_alpha_established':False,
        'files':{str(p):sha(p) for p in allfiles}}
    (OUT/'final_verification.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print('Verified',len(source['sources']),'source hashes,',len(manifest['files']),'report artifacts, six reconstructed accounts and complete ticker roles.')

if __name__=='__main__':main()
