"""Check the completed release and write a checksum inventory without new QC work."""
from campaign import ROOT,P,OUT,digest,save,rows
import json
from datetime import datetime,timezone
REPORT=ROOT/'strategies/sstrangle/research/design_20261026_v085'
def main():
 v=json.loads((OUT/'final_verification.json').read_text());assert v['engineering_pass'] and v['frequency_pass'];assert v['rejected_addon']['status']=='rejected_at_native_baseline_gate'
 rule=json.loads((OUT/'frozen_rules.json').read_text());assert set(rule)=={'condor'}
 provenance=json.loads((OUT/'research_provenance.json').read_text());assert provenance['source_sha256']==digest(P/'research.py') and provenance['rules_sha256']==digest(OUT/'frozen_rules.json')
 checks=0
 for key in ['put_spread_smoke','condor_baseline','condor_final']:
  folder=OUT/(key+'_evidence')
  for n,h in json.loads((folder/'manifest.json').read_text())['files'].items():assert digest(folder/n)==h,(key,n);checks+=1
  raw=json.loads((folder/'raw_order_pages_manifest.json').read_text())
  for n,h in raw['files'].items():assert digest(folder/'raw_order_pages'/n)==h,(key,n);checks+=1
 for item in json.loads((OUT/'official_settlement_sources/manifest.json').read_text()):assert digest(OUT/'official_settlement_sources'/item['snapshot'])==item['sha256'];checks+=1
 for item in json.loads((OUT/'late_provider_review/manifest.json').read_text())['sources']:assert digest(OUT/'late_provider_review'/item['snapshot'])==item['sha256'];checks+=1
 for n,h in json.loads((REPORT/'manifest.json').read_text())['files'].items():assert digest(REPORT/n)==h,n;checks+=1
 queue=rows();assert len(queue)==4 and all(r['status'] in ['done','failed'] for r in queue)
 assert sum(r['status']=='done' for r in queue)==3
 assert not any(r['name'].endswith('PUT_SPREAD_FINAL') for r in queue)
 assert '11 passed' in (OUT/'tests.log').read_text();assert '21 passed' in (OUT/'inherited_admission_tests.log').read_text()
 ledger=[]
 for r in queue:
  key=r['name'].split('20261026_',1)[1].lower();m=json.loads((OUT/(key+'_manifest.json')).read_text());ledger.append(dict(**r,source_sha256=m['source_sha256'],role='failed optional baseline' if r['status']=='failed' else 'smoke' if m['smoke'] else 'frozen final' if m['alpha'] else 'baseline'))
 save(OUT/'native_trial_ledger.json',ledger)
 files={str(p.relative_to(ROOT)):digest(p) for base in [P,REPORT,OUT] for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name not in ['release_audit.json','release_manifest.json']}
 save(OUT/'release_manifest.json',dict(version='0.8.5',generated_utc=datetime.now(timezone.utc).isoformat(),files=files))
 save(OUT/'release_audit.json',dict(version='0.8.5',status='verified_research_release',checksum_checks=checks,manifest_files=len(files),native_completed=3,native_failed=1,tests_passed=32,engineering_pass=True,frequency_pass=True,condor_candidate_positive_sampled_margin=v['runs']['condor_final']['minimum_margin_remaining']>=0,baseline_margin_gate=False,independent_quote_replay=False,official_settlement_parity=False,robust_alpha=False,live_approved=False))
 print('Verified release:',checks,'frozen checks,',len(files),'files, 3 successful native jobs and 1 preserved failure')
if __name__=='__main__':main()
