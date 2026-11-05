#!/usr/bin/env python3
"""Read-only ObjectStore metadata inventory; never downloads or deletes objects."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import hashlib
import html
import importlib.util
import re
import json
from pathlib import Path
import qc_storage as storage
import threading
import time
try:
    from .qc_api_check import ROOT, credentials, request
except ImportError:
    from qc_api_check import ROOT, credentials, request


def absolute_path(path):
    return '/' + path.strip('/')


def read_directory(transport, organization, path):
    """Require pagination to advance; never silently repeat the first page."""
    objects, pages, fingerprints = [], 1, set()
    page = 1
    while page <= pages:
        body = {'organizationId':organization, 'path':absolute_path(path)}
        if page > 1:
            body['page'] = page
        response = transport('/object/list', body)
        if not response.get('success'):
            raise RuntimeError(f'Listing rejected at {path}: {response.get("errors")}')
        pages = max(1,int(response.get('totalPages') or 1))
        if pages > 1 and int(response.get('page') or 0) != page:
            raise RuntimeError(f'Pagination did not advance at {path}, requested page {page}')
        rows = response.get('objects') or []
        fingerprint = tuple(sorted(row['key'] for row in rows))
        if fingerprint and fingerprint in fingerprints:
            raise RuntimeError(f'Repeated listing page at {path}')
        fingerprints.add(fingerprint)
        parent = absolute_path(path).rstrip('/')
        for row in rows:
            key = absolute_path(row['key'])
            if parent and key != parent and not key.startswith(parent+'/'):
                raise RuntimeError(f'Listing escaped directory {path}: {key}')
            objects.append({**row,'key':key.lstrip('/')})
        page += 1
    return objects


def collect_inventory(transport, organization, workers=4):
    pending, seen, leaves, errors = ['/'], set(), {}, []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        while pending:
            batch = sorted(set(pending)-seen)
            pending = []
            if not batch:
                break
            seen.update(batch)
            if len(seen)>20000:
                raise RuntimeError('Directory inventory exceeded 20,000 paths')
            futures = [(path,executor.submit(read_directory,transport,organization,path)) for path in batch]
            for path,future in futures:
                try:
                    for row in future.result():
                        if row.get('folder') or row['key'].endswith('/'):
                            pending.append(absolute_path(row['key']))
                        else:
                            leaves[row['key']] = row
                except Exception as error:
                    errors.append({'path':path,'error':str(error)})
            print(f'Listed {len(seen)} directories; {len(leaves)} files; {len(pending)} directories pending; {len(errors)} errors',flush=True)
    return sorted(leaves.values(),key=lambda row:row['key']), errors, len(seen)


def known_model_keys():
    """Conservative hints from local research state, not proof all other files are unused."""
    knowledge=ROOT/'strategies/sml01/knowledge.json'
    module_path=ROOT/'strategies/sml01/src/lb/harness/psuf.py'
    if not knowledge.exists() or not module_path.exists():return set()
    spec=importlib.util.spec_from_file_location('inventory_cell_suffix',module_path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    keys=set()
    for ticker,entry in json.loads(knowledge.read_text()).get('per_etf_best',{}).items():
        cfg=entry.get('config') or {}
        if not all(key in cfg for key in ('axis','labeler','sizing','thresh')):continue
        label=str(cfg['labeler']).replace('+','_x_')
        cell=f"{cfg['axis']}_{label}_{cfg['sizing']}_t{int(round(float(cfg['thresh'])*100))}"+module.cell_suffix(cfg)
        for kind in ('cell','model','returns'):
            keys.add(f'autoresearch/{ticker}/{kind}_{cell}.json')
    return keys


def write_reports(folder, rows, errors, directory_count, used_bytes=None, quota_files=None, quota_bytes=None, protected_keys=None, expected_files=None):
    fields=['key','size','modified','mime','group','review']
    protected_keys=protected_keys or set()
    groups=defaultdict(lambda:{'files':0,'bytes':0,'oldest':'','newest':''})
    for row in rows:
        row['group']=row['key'].split('/')[0] if '/' in row['key'] else '(root files)'
        name=row['key'].rsplit('/',1)[-1]
        if name in {'latest_key.json','manifest.json'}:
            row['review']='Preserve: selector or manifest; dependencies need review'
        elif row['key'] in protected_keys:
            row['review']='Preserve: matches local SML01 per_etf_best config'
        elif re.fullmatch(r'v\d+.*',row['group']) or row['group'] in {'test','v69min'}:
            row['review']='Review: historical trial folder; obsolescence unverified'
        else:
            row['review']='Preserve pending owner review' 
        group=groups[row['group']]
        group['files']+=1
        group['bytes']+=int(row.get('size') or 0)
        modified=row.get('modified') or ''
        if modified:
            group['oldest']=min(group['oldest'] or modified,modified)
            group['newest']=max(group['newest'],modified)
    with (folder/'objects.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,extrasaction='ignore')
        writer.writeheader();writer.writerows(rows)
    total=sum(group['bytes'] for group in groups.values())
    summary={'generated_utc':datetime.now(timezone.utc).isoformat(),'files':len(rows),
             'bytes':total,'api_storage_bytes':used_bytes,'directories':directory_count,
             'errors':errors,'complete':not errors and (used_bytes is None or total==used_bytes) and (expected_files is None or len(rows)==expected_files),
             'expected_files':expected_files,
             'groups':dict(groups),'quota_files':quota_files,'quota_bytes':quota_bytes,
             'minimum_files_to_remove':None if quota_files is None else max(0,len(rows)-quota_files+1),
             'minimum_bytes_to_remove':None if quota_bytes is None else max(0,total-quota_bytes+1),
             'protected_hints_found':sum(row['key'] in protected_keys for row in rows)}
    for filename,predicate in [('review_candidates.csv',lambda row:row['review'].startswith('Review:')),
                               ('preserve_hints.csv',lambda row:row['review'].startswith('Preserve:'))]:
        with (folder/filename).open('w',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=fields,extrasaction='ignore');writer.writeheader()
            writer.writerows(row for row in rows if predicate(row))
    candidates=[row for row in rows if row['review'].startswith('Review:')]
    summary['candidate_files']=len(candidates)
    summary['candidate_bytes']=sum(int(row.get('size') or 0) for row in candidates)
    missing=sorted(protected_keys-{row['key'] for row in rows})
    summary['local_reference_hints']=len(protected_keys)
    summary['local_reference_hints_missing']=len(missing)
    with (folder/'missing_local_reference_keys.csv').open('w',newline='') as handle:
        writer=csv.writer(handle);writer.writerow(['key','meaning'])
        writer.writerows((key,'Local config hint absent from this metadata snapshot; persistence history unverified') for key in missing)
    (folder/'summary.json').write_text(json.dumps(summary,indent=2))
    with (folder/'groups.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=['group','files','bytes','oldest','newest'])
        writer.writeheader()
        for name,group in sorted(groups.items(),key=lambda item:-item[1]['bytes']):writer.writerow({'group':name,**group})
    table=''.join('<tr><td>'+html.escape(name)+'</td><td>'+str(group['files'])+'</td><td>'+f"{group['bytes']/1048576:.2f}"+'</td><td>'+html.escape(group['oldest'])+'</td><td>'+html.escape(group['newest'])+'</td></tr>' for name,group in sorted(groups.items(),key=lambda item:-item[1]['bytes']))
    quota_note='Quota was not supplied for this scan.'
    if quota_files is not None and quota_bytes is not None:
        quota_note=f'Observed quota: {quota_files:,} files / {quota_bytes/1048576:.0f} MiB. Minimum removal to leave room for one new file: {summary["minimum_files_to_remove"]:,} files and {summary["minimum_bytes_to_remove"]/1073741824:.3f} GiB. Training needs more headroom.'
    report='''<!doctype html><meta charset="utf-8"><title>QC ObjectStore inventory</title>
<style>body{font:16px system-ui;max-width:1200px;margin:40px auto;padding:0 24px;color:#162435}table{border-collapse:collapse;width:100%}th,td{padding:9px;text-align:left;border-bottom:1px solid #ccd5df}th{background:#eef3f9;position:sticky;top:0}input{font:inherit;padding:10px;width:95%}a{color:#135bba}strong{color:#993a18}</style>
<h1>ObjectStore cleanup inventory</h1><p>Metadata only. No stored contents downloaded or objects deleted. All objects require owner review before deletion.</p>
'''+f'<p>Snapshot: {html.escape(summary["generated_utc"])}. <b>{len(rows):,} files · {total/1073741824:.3f} GiB</b>. Complete metadata reconciliation: {summary["complete"]}.</p>'+'''
'''+f'<p>{html.escape(quota_note)}</p><p>Historical trial candidates: {summary["candidate_files"]:,} files / {summary["candidate_bytes"]/1048576:.1f} MiB. These are unverified candidates, not approved deletions.</p>'+'''<p>The quota supplied for this snapshot is recorded in summary.json. Its minimum-removal figures leave room for one new file; a training workflow needs additional headroom. Increasing the quota can preserve research history.</p>
<p><a href="missing_local_reference_keys.csv">Local reference hints absent from this snapshot (CSV)</a></p>
<p><a href="review_candidates.csv">Historical trial candidates (CSV; unverified)</a> · <a href="preserve_hints.csv">Selectors and local champion matches to preserve (CSV)</a></p>
<p><a href="objects.csv">Full file inventory (CSV)</a> · <a href="groups.csv">Group totals (CSV)</a> · <a href="summary.json">Snapshot and completeness evidence (JSON)</a></p>
<p><strong>Folder names and age do not prove that a model or cache is obsolete.</strong> Preserve latest pointers, active models, their preprocessing/calibration files and source data needed for reproducibility. Trial folders are candidates for review, not approved deletions.</p>
<input id="filter" placeholder="Filter groups by name" aria-label="Filter groups"><table><thead><tr><th>Group</th><th>Files</th><th>MiB</th><th>Oldest modification (UTC)</th><th>Newest modification (UTC)</th></tr></thead><tbody>'''+table+'''</tbody></table><script>document.getElementById('filter').oninput=e=>{for(const row of document.querySelectorAll('tbody tr'))row.hidden=!row.cells[0].textContent.toLowerCase().includes(e.target.value.toLowerCase())}</script>'''
    (folder/'review.html').write_text(report)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'data/S001.duckdb')
    parser.add_argument('--out',type=Path,default=ROOT/'.local/object-store-inventory'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    parser.add_argument('--workers',type=int,default=8,help='Parallel read-only requests; globally spaced at four per second')
    parser.add_argument('--expected-files',type=int,help='Independent file-count observation to reconcile against')
    parser.add_argument('--max-files',type=int,help='Observed cloud quota for this snapshot')
    parser.add_argument('--max-bytes',type=int,help='Observed cloud byte quota for this snapshot')
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    user,token=credentials(args.db)
    with storage.connect(args.db.resolve().as_uri()+'?mode=ro',uri=True) as conn:
        organization=conn.execute("SELECT value FROM settings WHERE category='project' AND key='organization_id'").fetchone()[0]
    cache=args.out/'pages';cache.mkdir(exist_ok=True)
    lock=threading.Lock();next_request=[0.0];used=[None]
    def transport(path,body):
        digest=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
        saved=cache/(digest+'.json')
        if saved.exists():
            try:return json.loads(saved.read_text())
            except json.JSONDecodeError:saved.unlink()
        for attempt in range(3):
            with lock:
                delay=max(0,next_request[0]-time.monotonic())
                next_request[0]=max(time.monotonic(),next_request[0])+0.25
            if delay:time.sleep(delay)
            try:
                response=request(user,token,path,body)
                with lock:used[0]=response.get('objectStorageUsed',used[0])
                saved.write_text(json.dumps(response))
                return response
            except Exception:
                if attempt==2:raise
                time.sleep(2**attempt)
    rows,errors,count=collect_inventory(transport,organization,workers=max(1,args.workers))
    if used[0] is None:
        for saved in cache.glob('*.json'):
            used[0]=json.loads(saved.read_text()).get('objectStorageUsed')
            if used[0] is not None:break
    summary=write_reports(args.out,rows,errors,count,used[0],args.max_files,args.max_bytes,known_model_keys(),args.expected_files)
    print(json.dumps({k:v for k,v in summary.items() if k!='groups'},indent=2))
    print(f'Inventory: {args.out}',flush=True)
    if not summary['complete']:raise SystemExit('Inventory incomplete; review errors/reconciliation before any cleanup')


if __name__=='__main__':main()
