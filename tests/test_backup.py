"""Workspace backup regression: WAL commits must survive without sidecar files."""
import qc_storage as storage
import tarfile
from scripts.gdrive_backup import create_tar


def test_archive_contains_consistent_wal_snapshot_and_excludes_local_environments(tmp_path):
    root = tmp_path / 'workspace'
    (root / 'data').mkdir(parents=True)
    (root / '.local').mkdir()
    (root / '.local/ignored').write_text('large private cache')
    (root / 'README.md').write_text('source')
    live = storage.connect(root / 'data/S001.duckdb')
    live.execute('PRAGMA journal_mode=WAL')
    live.execute('CREATE TABLE experiments(value TEXT)')
    live.execute("INSERT INTO experiments VALUES ('committed in WAL')")
    live.commit()
    archive_path, _ = create_tar(root)
    try:
        with tarfile.open(archive_path) as archive:
            names = archive.getnames()
            assert 'workspace/README.md' in names
            assert not any('.local' in name or name.endswith('.duckdb-wal') for name in names)
            contents = archive.extractfile('workspace/data/S001.duckdb').read()
        snapshot = tmp_path / 'snapshot.duckdb'
        snapshot.write_bytes(contents)
        with storage.connect(snapshot) as conn:
            assert conn.execute('SELECT value FROM experiments').fetchone()[0] == 'committed in WAL'
        assert archive_path.stat().st_mode & 0o077 == 0
    finally:
        archive_path.unlink()
        live.close()
