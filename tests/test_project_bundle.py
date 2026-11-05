from scripts.enqueue_project import bundle_files
import pytest


def test_bundle_keeps_nested_python_modules_and_excludes_research_assets(tmp_path):
    (tmp_path / 'main.py').write_text('import features.model')
    (tmp_path / 'features').mkdir()
    (tmp_path / 'features/model.py').write_text('value = 42')
    (tmp_path / 'research.ipynb').write_text('{}')
    (tmp_path / '.private').mkdir()
    (tmp_path / '.private/ignored.py').write_text('private')
    main, files = bundle_files(tmp_path)
    assert main == tmp_path / 'main.py'
    assert files == {'features/model.py': 'value = 42'}


def test_bundle_rejects_missing_entrypoint_and_oversized_module(tmp_path):
    with pytest.raises(ValueError, match='main.py'):
        bundle_files(tmp_path)
    (tmp_path / 'main.py').write_text('pass')
    (tmp_path / 'oversized.py').write_text('x' * 128001)
    with pytest.raises(ValueError, match='exceeds'):
        bundle_files(tmp_path)
