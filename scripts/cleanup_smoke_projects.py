#!/usr/bin/env python3
"""Resume cleanup of recorded, owned QC smoke projects after a network failure."""
import argparse
import json
import re
from pathlib import Path
try:
    from .qc_api_check import ROOT, credentials, request
except ImportError:
    from qc_api_check import ROOT, credentials, request


def cleanup_record(path, user, token, transport=request):
    owned = json.loads(path.read_text())
    project = owned['project_id']
    if owned.get('object_store_prefix'):
        cleanup_objects(user, token, owned['organization_id'], owned['object_store_prefix'], transport)
    response = transport(user, token, f'/projects/read?projectId={project}')
    matches = [p for p in response.get('projects', []) if p.get('projectId') == project]
    if matches:
        name = matches[0].get('name', '')
        original_name = name.rsplit(' ', 1)[-1] if name.startswith('Recycle Bin/') else name
        if not original_name.startswith(('qc-server-smoke-', 'qc-work-smoke-')):
            raise RuntimeError(f'Project {project} has no smoke-test ownership prefix; preserved')
        if owned.get('name') and original_name != owned['name']:
            raise RuntimeError(f'Project {project} was renamed; preserved for inspection')
        if not name.startswith('Recycle Bin/'):
            transport(user, token, '/projects/delete', {'projectId': project}, method='DELETE')
    path.unlink()
    return project


def cleanup_objects(user, token, organization, prefix, transport=request):
    if not re.fullmatch(r'qcv/[0-9a-f]{32}/', prefix):
        raise RuntimeError('Unrecognised validation ObjectStore namespace; preserved')
    stack, visited, leaves = [prefix], set(), set()
    while stack:
        path = stack.pop()
        if path in visited:
            continue
        visited.add(path)
        response = transport(user, token, '/object/list', {'organizationId': organization, 'path': '/' + path.lstrip('/')})
        if int(response.get('totalPages') or 1) > 1:
            raise RuntimeError('Validation namespace exceeded one result page; cleanup record retained')
        for item in (response.get('objects') or []):
            key = item.get('key', '').lstrip('/')
            if not key.startswith(prefix):
                raise RuntimeError('ObjectStore returned a key outside the owned namespace; preserved')
            if item.get('folder') or key.endswith('/'):
                stack.append(key)
            else:
                leaves.add(key)
    for key in sorted(leaves):
        transport(user, token, '/object/delete', {'organizationId': organization, 'key': key})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT / 'data/S001.duckdb')
    args = parser.parse_args()
    pending = sorted((ROOT / '.local/verification/pending-cloud').glob('*.json'))
    if not pending:
        print('No pending smoke project cleanup')
        return
    user, token = credentials(args.db.resolve())
    for path in pending:
        project = cleanup_record(path, user, token)
        print(f'Smoke project {project}: cleaned up')


if __name__ == '__main__':
    main()
