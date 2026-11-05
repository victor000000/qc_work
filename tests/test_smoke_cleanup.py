"""Cloud cleanup can delete only recorded, recognisable smoke projects."""
import json
import pytest
from scripts.cleanup_smoke_projects import cleanup_record


def test_cleanup_preserves_unrelated_project_and_ownership_record(tmp_path):
    record = tmp_path / '123.json'
    record.write_text(json.dumps({'project_id': 123}))
    calls = []
    def transport(*args, **kwargs):
        calls.append(args[2])
        return {'success': True, 'projects': [{'projectId': 123, 'name': 'important-strategy'}]}
    with pytest.raises(RuntimeError):
        cleanup_record(record, 'unused', 'unused', transport)
    assert calls == ['/projects/read?projectId=123']
    assert record.exists()


def test_cleanup_deletes_owned_smoke_project_before_removing_record(tmp_path):
    record = tmp_path / '123.json'
    record.write_text(json.dumps({'project_id': 123, 'name': 'qc-server-smoke-123'}))
    calls = []
    def transport(*args, **kwargs):
        calls.append((args[2], kwargs.get('method')))
        return {'success': True, 'projects': [{'projectId': 123, 'name': 'qc-server-smoke-123'}]}
    assert cleanup_record(record, 'unused', 'unused', transport) == 123
    assert calls[-1] == ('/projects/delete', 'DELETE')
    assert not record.exists()


def test_already_recycled_owned_project_clears_record_without_another_delete(tmp_path):
    record = tmp_path / '123.json'
    record.write_text(json.dumps({'project_id':123,'name':'qc-work-smoke-123'}))
    calls = []
    def transport(*args, **kwargs):
        calls.append(args[2])
        return {'success':True,'projects':[{'projectId':123,'name':'Recycle Bin/2026-10-17 00-00-00 qc-work-smoke-123'}]}
    cleanup_record(record,'unused','unused',transport)
    assert calls == ['/projects/read?projectId=123']
    assert not record.exists()


def test_object_cleanup_never_deletes_outside_owned_prefix():
    from scripts.cleanup_smoke_projects import cleanup_objects
    calls = []
    def transport(*args, **kwargs):
        calls.append(args[2])
        return {'success':True,'objects':[{'key':'production/model.json'}]}
    with pytest.raises(RuntimeError,match='outside'):
        cleanup_objects('unused','unused','org','qcv/'+'a'*32+'/',transport)
    assert calls == ['/object/list']


def test_object_cleanup_walks_only_owned_uuid_namespace():
    from scripts.cleanup_smoke_projects import cleanup_objects
    prefix = 'qcv/'+'a'*32+'/'
    deleted=[]
    def transport(user,token,path,body=None,**kwargs):
        if path == '/object/list':
            if body['path'] == '/' + prefix:
                return {'success':True,'objects':[{'key':'/'+prefix+'GLD/','folder':True}]}
            return {'success':True,'totalPages':None,'objects':[{'key':'/'+prefix+'GLD/model.json'}]}
        deleted.append(body['key'])
        return {'success':True}
    cleanup_objects('unused','unused','org',prefix,transport)
    assert deleted == [prefix+'GLD/model.json']


def test_empty_namespace_with_null_objects_needs_no_deletes():
    from scripts.cleanup_smoke_projects import cleanup_objects
    calls = []
    def transport(user,token,path,body=None,**kwargs):
        calls.append(path)
        return {'success':True,'objects':None,'totalPages':None}
    cleanup_objects('unused','unused','org','qcv/'+'a'*32+'/',transport)
    assert calls == ['/object/list']
