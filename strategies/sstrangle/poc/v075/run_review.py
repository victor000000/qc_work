"""Read archived evidence and a pinned provider sample; write only v0.7.5 outputs.

Run from any cwd. No provider ingestion, optimizer or QC submissions.
"""
from pathlib import Path
from datetime import timedelta
import hashlib,json,sys
from collections import Counter
import pandas as pd
from data_contract import quote_rejections,storage_plan
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'strategies/sstrangle/results/qc_design_poc_20261026_v075'
REPORT=ROOT/'strategies/sstrangle/research/design_20261026_v075'
V7=ROOT/'strategies/sstrangle/results/qc_final_poc_20261024'
PROVIDER=Path('/home/vic/data_providers')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(ROOT/'strategies/sstrangle/poc/v07'))
    from recheck_baselines import reconstruct
    from optimize import BASES
    paths=[ROOT/'docs/OPTIONS_DATA_REVIEW_20261026.md',
           ROOT/'data/options_storage_estimate_20261026.json',
           ROOT/'strategies/sstrangle/research/design_20261024_v7/DESIGN_REPORT.txt',
           ROOT/'strategies/sstrangle/research/design_20261024_v8/DESIGN_REPORT.txt',
           V7/'frozen_rules.json',V7/'final_comparison.csv',V7/'final_verification.json',
           ROOT/'strategies/sstrangle/results/qc_sizing_poc_20261024/final_verification.json',
           PROVIDER/'docs/requirements/QC_STRATEGY_OPTIONS_DATA_REQUIREMENTS_20261026.md']
    results={'version':'0.7.5','status':'local_design_poc_verified_independent_execution_pending',
             'native_runs_started':0,'network_acquisition_requests':0,
             'baseline_reproduction':{},'final_candidate_reproduction':{}}
    for kind,(_,folder,_) in BASES.items():
        _,r=reconstruct(folder);results['baseline_reproduction'][kind]=r
        for name in ['orders.json','episodes.parquet','backtest.json']:paths.append(folder/name)
    for kind in ('condor','strangle','put'):
        folder=V7/(kind+'_alpha_full_evidence')
        _,r=reconstruct(folder);results['final_candidate_reproduction'][kind]=r
        for name in ['orders.json','episodes.parquet','backtest.json']:paths.append(folder/name)
    provenance=json.loads((V7/'optimizer_provenance.json').read_text())
    assert sha(V7/'frozen_rules.json')==provenance['rules_sha256']
    assert sha(ROOT/'strategies/sstrangle/poc/v07/optimize.py')==provenance['source_sha256']
    results['frozen_v07_rule_and_optimizer_hashes_match']=True
    table=pd.read_csv(V7/'final_comparison.csv')
    table.to_csv(OUT/'inherited_v07_comparison.csv',index=False)
    sample_report=PROVIDER/'runtime/var/maintenance/theta-spxw-5m-pilot-20261026/sampling-mechanics/report.json'
    if sample_report.exists():
        saved=sample_report.read_bytes();m=json.loads(saved)
        (OUT/'provider_sampling_report_snapshot.json').write_bytes(saved)
        p=Path(m['views']['5m']['path']);assert sha(p)==m['views']['5m']['sha256']
        f=pd.read_parquet(p);counts=Counter();accepted=0
        for r in f.to_dict('records'):
            for key in ('interval_ts','quote_ts','available_at'):
                v=r.get(key);r[key]=None if pd.isna(v) else pd.Timestamp(v).to_pydatetime()
            # Give every snapshot a decision one second later. Even that generous
            # hypothetical timing cannot fix absent historical/source clocks.
            r['quote_type']='NBBO'
            rejection=quote_rejections(r,r['interval_ts']+timedelta(seconds=1))
            counts.update(rejection);accepted+=not rejection
        results['provider_sample_admission']={'source_scope':m['scope'],'release':m['release'],
            'rows':len(f),'contracts':int(f.contract_id.nunique()),'strict_quote_input_accepted':accepted,
            'rejection_counts':dict(counts),'same_timestamp_assumed_available':False,
            'test_decision':'hypothetical snapshot + 1 second; no execution claim',
            'strict_pre_0935_comparison':m['0935_strict_prior_comparison']}
        paths.extend([OUT/'provider_sampling_report_snapshot.json',p])
    else:
        results['provider_sample_admission']={'status':'blocked','reason':'saved provider sample report absent'}
    scopes=[('SPXW core',1100*1000),('QQQ surface extension',1100*400),
            ('SPY optional execution expansion',1100*400),('SPXW 11-date pilot',11*1000)]
    results['storage']={'units':'decimal GB','assumptions':'1100 full sessions; counts are total call+put contracts across retained expiries per session, not listing census; 150–300 bytes/row including assumed Greeks and storage copies',
        'scopes':{name:{str(freq)+'m':storage_plan(cd,freq) for freq in [1,5]} for name,cd in scopes}}
    results['storage']['all_seven_underlying_inputs']={str(freq)+'m':storage_plan(7*1100,freq,(40,160)) for freq in [1,5]}
    results['storage']['full_0dte_core_plus_qqq_surface']={str(freq)+'m':storage_plan(1100*1400,freq) for freq in [1,5]}
    (OUT/'review_results.json').write_text(json.dumps(results,indent=2)+'\n')
    paths.extend(Path(__file__).parent.glob('*.py'))
    contract=REPORT/'design_contract.json'
    if contract.exists():paths.append(contract)
    (OUT/'source_manifest.json').write_text(json.dumps({'version':'0.7.5','sources':[{'path':str(p),'sha256':sha(p)} for p in paths]},indent=2)+'\n')
    print(json.dumps({k:v for k,v in results.items() if k not in ['storage','baseline_reproduction','final_candidate_reproduction']},indent=2))
    print('Reconstructed',sum(r['episodes'] for r in results['baseline_reproduction'].values()),'baseline episodes and',sum(r['episodes'] for r in results['final_candidate_reproduction'].values()),'final candidate episodes')

if __name__=='__main__':main()
