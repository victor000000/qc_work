"""Freeze and verify the declared full research source chain, without live imports."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
STAGES=('equity_rv','risk_retry','cross_asset_guard','holding_cap')
HELPERS=('completed_volatility.py','equity_rv_features.py','fresh_risk_slots.py',
         'cross_asset_buyback_guard.py','holding_age.py','voluntary_quote_guard.py')


def sha(data):return hashlib.sha256(data).hexdigest()


def freeze_chain(campaign,extras):
    folder=campaign/'source_chain';folder.mkdir()
    stages=[];previous=None
    for index,name in enumerate(STAGES):
        receipt=json.loads((HERE/(name+'_source_receipt_20261019.json')).read_text())
        parent=Path(receipt['parent']).read_bytes()
        generated=(HERE/(name+'_main.py')).read_bytes()
        if sha(parent)!=receipt['parent_sha256'] or sha(generated)!=receipt['generated_sha256']:
            raise ValueError('Research source chain differs from declared transformation: '+name)
        if previous is not None and parent!=previous:
            raise ValueError('Research source chain has a disconnected parent')
        if index==0:(folder/'root.py').write_bytes(parent)
        (folder/(name+'.py')).write_bytes(generated)
        stages.append(dict(name=name,parent_sha256=sha(parent),generated_sha256=sha(generated),receipt=receipt))
        previous=generated
    missing=set(HELPERS)-set(extras)
    if missing:raise ValueError('Missing chain dependencies: '+str(missing))
    manifest=dict(stages=stages,helpers={name:sha(extras[name].encode()) for name in HELPERS},
        scope='Frozen source provenance only; native engineering fixtures are separate evidence; no performance claim')
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


def verify_chain(campaign,unrendered,extras):
    folder=campaign/'source_chain';manifest=json.loads((folder/'manifest.json').read_text())
    if [r['name'] for r in manifest['stages']]!=list(STAGES):
        raise ValueError('Incomplete or reordered research source chain')
    parent=(folder/'root.py').read_bytes()
    for row in manifest['stages']:
        generated=(folder/(row['name']+'.py')).read_bytes()
        receipt=row['receipt']
        if (sha(parent)!=row['parent_sha256'] or sha(generated)!=row['generated_sha256']
                or row['parent_sha256']!=receipt['parent_sha256']
                or row['generated_sha256']!=receipt['generated_sha256']):
            raise ValueError('Frozen research source chain hash mismatch')
        parent=generated
    if unrendered.encode()!=parent:raise ValueError('Queued implementation differs from holding-cap source chain')
    if set(manifest['helpers'])!=set(HELPERS):raise ValueError('Incomplete chain helper manifest')
    for name,expected in manifest['helpers'].items():
        if name not in extras or sha(extras[name].encode())!=expected:
            raise ValueError('Queued dependency differs from frozen chain: '+name)
    return manifest
