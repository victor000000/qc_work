"""Public navigation checks must not confuse examples with real documentation links."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('doc_checker', Path(__file__).parents[1]/'scripts/check_docs.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def test_heading_anchors_and_fenced_examples(tmp_path):
    (tmp_path/'guide.md').write_text('# Setup!\n\n## Next step\n## Next step\n')
    (tmp_path/'README.md').write_text('[setup](guide.md#setup)\n[next](guide.md#next-step-1)\n```md\n[example](absent.md)\n```\n')
    result = checker.inspect(tmp_path, Path('README.md'), {'README.md'})
    assert result['unavailable_links'] == []
    assert result['local_links'] == 2


def test_missing_path_fragment_and_workstation_reference(tmp_path):
    (tmp_path/'guide.md').write_text('# Setup\n')
    (tmp_path/'README.md').write_text('[missing](missing.md)\n[anchor](guide.md#absent)\n[private](/private/evidence.md)\n')
    result = checker.inspect(tmp_path, Path('README.md'), {'README.md'})
    assert result['unavailable_links'] == ['guide.md#absent', 'missing.md']
    assert result['workstation_local_references'] == 1


def test_native_inventory_excludes_generated_and_nested_owned_repositories(tmp_path):
    (tmp_path/'README.md').write_text('# Owned\n')
    for folder in ('target', 'data', '.local', '.pytest_cache', 'example.egg-info', 'nested/.git'):
        directory = tmp_path/folder
        directory.mkdir(parents=True)
        (directory/'ignored.md').write_text('# Not project prose\n')
    (tmp_path/'nested/README.md').write_text('# Independent project\n')
    assert checker.owned(tmp_path, native=True) == [Path('README.md')]


def test_first_inventory_generation_can_link_its_own_output(tmp_path):
    import json
    (tmp_path/'docs').mkdir()
    (tmp_path/'docs/doc-check.json').write_text(json.dumps(dict(canonical=['README.md'])))
    (tmp_path/'README.md').write_text('[inventory](docs/documentation-inventory.json)\n')
    assert checker.main(['--root', str(tmp_path), '--write-inventory']) is False
    inventory = json.loads((tmp_path/'docs/documentation-inventory.json').read_text())
    assert inventory['counts']['documents'] == 1
