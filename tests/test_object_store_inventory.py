"""An inventory used for cleanup decisions must expose incomplete or repeated results."""
import json
import pytest
from scripts.inventory_object_store import collect_inventory, read_directory, write_reports


def test_pagination_cannot_silently_repeat_first_page():
    def transport(path,body):
        return {'success':True,'page':1,'totalPages':2,'objects':[{'key':'/models/a','size':3}]}
    with pytest.raises(RuntimeError,match='did not advance'):
        read_directory(transport,'unused','/models')


def test_absolute_folder_paths_and_cycles_are_counted_once():
    def transport(path,body):
        if body['path']=='/':return {'success':True,'objects':[{'key':'/models','folder':True}]}
        return {'success':True,'objects':[{'key':'/models','folder':True},{'key':'/models/a','size':3}]}
    rows,errors,directories=collect_inventory(transport,'unused',workers=1)
    assert not errors
    assert directories==2
    assert [row['key'] for row in rows]==['models/a']


def test_failed_subdirectory_keeps_inventory_explicitly_incomplete(tmp_path):
    def transport(path,body):
        if body['path']=='/':return {'success':True,'objects':[{'key':'/models','folder':True}]}
        raise RuntimeError('read denied')
    rows,errors,count=collect_inventory(transport,'unused',workers=1)
    summary=write_reports(tmp_path,rows,errors,count,used_bytes=3)
    assert not summary['complete']
    assert summary['errors'][0]['path']=='/models'


def test_report_reconciles_file_bytes_and_escapes_names(tmp_path):
    summary=write_reports(tmp_path,[{'key':'<script>/a','size':3,'modified':'2026-01-01'}],[],1,used_bytes=3)
    assert summary['complete']
    assert summary['files']==1 and summary['bytes']==3
    report=(tmp_path/'review.html').read_text()
    assert '&lt;script&gt;' in report
    assert '<td><script>' not in report
    assert json.loads((tmp_path/'summary.json').read_text())['bytes']==3


def test_equal_bytes_cannot_hide_a_missing_zero_byte_file(tmp_path):
    rows=[{'key':'model','size':3,'modified':''}]
    summary=write_reports(tmp_path,rows,[],1,used_bytes=3,expected_files=2)
    assert not summary['complete']
