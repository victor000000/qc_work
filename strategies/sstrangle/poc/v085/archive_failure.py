"""Archive the already failed spread identity without retrying or altering the run."""
from campaign import ROOT,OUT,save,read,credentials,digest
from collect import archive_raw_orders
import json,hashlib

def main():
 key='put_spread_baseline';response=json.loads((OUT/(key+'_progress.json')).read_text());b=response['backtest'];assert b['completed'] and 'Margin Call' in b['error']
 save(OUT/(key+'_terminal.json'),response)
 u,t=credentials(ROOT/'data/S001.duckdb');ids=dict(projectId=b['projectId'],backtestId=b['backtestId'])
 m=json.loads((OUT/(key+'_manifest.json')).read_text());cloud=read(u,t,'/files/read',{'projectId':ids['projectId']});remote={f['name']:f['content'] for f in cloud['files']};assert hashlib.sha256(remote['main.py'].encode()).hexdigest()==m['source_sha256'];save(OUT/(key+'_cloud_source_files.json'),cloud)
 folder=OUT/(key+'_evidence');folder.mkdir(exist_ok=True);save(folder/'backtest.json',response)
 archive_raw_orders(u,t,ids,int(b['statistics']['Total Orders']),folder)
 orders=json.loads((folder/'orders.json').read_text());margin=[o for o in orders if 'margin call' in o.get('tag','').lower()]
 assert margin and any(e.get('fillQuantity') for o in margin for e in o.get('events',[]))
 result=dict(key=key,project_id=b['projectId'],backtest_id=b['backtestId'],status='rejected_at_native_baseline_gate',error=b['error'],actual_margin_call_orders=margin,orders_archived=len(orders),source_verified=True,completed_full_requested_period=False,accounting_pass=False,selection_started=False,final_candidate_submitted=False,performance_interpretation='Early-aborted account with open exposure; displayed return/CAGR are not accepted full-period strategy performance',decision='Reject optional put-spread add-on at original $100k/one-lot/20-point/13-slot specification; no capital increase, retuning, or forced liquidation bypass')
 save(OUT/'put_spread_failure.json',result)
 amendment=dict(version='0.8.5',reason='Optional put-spread native baseline stopped on margin intervention before full-period acceptance',original_contract_sha256=digest(OUT/'experiment_contract.json'),active_research_strategies=['condor'],rejected_addons=['put_spread'],condor_rule_budget_and_selection_unchanged=True,planned_rule_trials=26,executed_rule_trials=13,saved_before_local_selection=not (OUT/'frozen_rules.json').exists(),scope='Complete condor QC baseline -> local research -> final QC; preserve failed optional spread rather than optimize a truncated tape')
 assert amendment['saved_before_local_selection'] or (OUT/'scope_amendment.json').exists()
 if not (OUT/'scope_amendment.json').exists():save(OUT/'scope_amendment.json',amendment)
 print(result['status'],len(margin),'margin call orders',flush=True)
if __name__=='__main__':main()
