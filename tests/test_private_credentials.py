import json
from pathlib import Path
import pytest
from scripts import qc_api_check


def test_private_credentials_never_open_database(tmp_path, monkeypatch):
    monkeypatch.delenv('QC_USER_ID', raising=False)
    monkeypatch.delenv('QC_API_TOKEN', raising=False)
    file = tmp_path / 'private.json'
    monkeypatch.setenv('QC_CREDENTIALS_FILE', str(file))
    monkeypatch.setattr(qc_api_check.storage, 'connect', lambda *a, **k: pytest.fail('database accessed'))
    with pytest.raises(RuntimeError, match='database credentials are unsupported'):
        qc_api_check.credentials(tmp_path / 'legacy.db')
    file.write_text(json.dumps({'qc_user_id': 'test-user', 'qc_api_token': 'test-token'}))
    file.chmod(0o644)
    with pytest.raises(RuntimeError, match='0600'):
        qc_api_check.credentials()
    file.chmod(0o600)
    assert qc_api_check.credentials() == ('test-user', 'test-token')
    monkeypatch.setenv('QC_API_TOKEN', 'environment-token')
    assert qc_api_check.credentials() == ('test-user', 'environment-token')
    monkeypatch.setenv('QC_USER_ID', 'environment-user')
    file.unlink()
    assert qc_api_check.credentials() == ('environment-user', 'environment-token')
