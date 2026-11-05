#!/usr/bin/env python3
"""Full project backup to Google Drive.

Usage: python3 scripts/gdrive_backup.py
  - Preserves previous backups until a new archive has been uploaded
  - Compresses entire project (excluding target/, .git/, .venv/, logs, docs)
  - Uploads single tar.gz
"""

import json
import qc_storage as storage
import tarfile
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
RCLONE_CONF = Path.home() / ".config/rclone/rclone.conf"


def parse_rclone_conf():
    conf = RCLONE_CONF.read_text()
    creds = {}
    for line in conf.splitlines():
        line = line.strip()
        if line.startswith("client_id"):
            creds["client_id"] = line.split("=", 1)[1].strip()
        elif line.startswith("client_secret"):
            creds["client_secret"] = line.split("=", 1)[1].strip()
        elif line.startswith("token"):
            creds["token"] = json.loads(line.split("=", 1)[1].strip())
        elif line.startswith("root_folder_id"):
            creds["root_folder_id"] = line.split("=", 1)[1].strip()
    return creds


def get_drive_service(creds):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_data = creds["token"]
    return build("drive", "v3", credentials=Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="REDACTED_RESTORE_FROM_PRIVATE_CREDENTIAL_BACKUP",
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        scopes=["https://www.googleapis.com/auth/drive"],
    ))


def create_tar(project_dir=PROJECT_DIR):
    """Archive source plus consistent checkpoint snapshots of runtime DuckDB databases."""
    project_dir = Path(project_dir).resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"qc_work_{stamp}.tar.gz"
    with tempfile.NamedTemporaryFile(prefix="qc_backup_", suffix=".tar.gz", delete=False) as handle:
        archive_path = Path(handle.name)
    try:
        with tempfile.TemporaryDirectory(prefix="qc_duckdb_") as staging:
            snapshots = []
            for source in (project_dir / "data").glob("*.duckdb"):
                target = Path(staging) / source.name
                storage.snapshot(source, target)
                snapshots.append((target, f"{project_dir.name}/data/{source.name}"))

            def include(info):
                relative = Path(info.name).parts[1:]
                if any(part in {"target", ".git", ".venv", ".local", ".claude", "__pycache__", ".pytest_cache", "logs"}
                       or part.startswith(".venv") for part in relative):
                    return None
                if relative and (relative[-1].endswith((".duckdb.wal", ".access.lock"))
                                 or relative[-1] == "qc-server.pid"):
                    return None
                if len(relative) == 2 and relative[0] == "data" and relative[-1].endswith(".duckdb"):
                    return None  # use the locked, checkpointed DuckDB snapshot below
                return info

            with tarfile.open(archive_path, "w:gz", dereference=False) as archive:
                archive.add(project_dir, arcname=project_dir.name, filter=include)
                for snapshot, name in snapshots:
                    archive.add(snapshot, arcname=name)
        print(f"  {filename} ({archive_path.stat().st_size / (1024 * 1024):.1f} MB)")
        return archive_path, filename
    except BaseException:
        archive_path.unlink(missing_ok=True)
        raise


def upload(service, filepath, filename, folder_id):
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(filepath), resumable=True)
    f = service.files().create(
        body={"name": filename, "parents": [folder_id]},
        media_body=media, fields="id,size",
    ).execute()
    size_mb = int(f.get("size", 0)) / (1024 * 1024)
    print(f"  uploaded: {filename} ({size_mb:.1f} MB) id={f['id']}")


def main():
    print("1. Connecting to Google Drive...")
    creds = parse_rclone_conf()
    folder_id = creds["root_folder_id"]
    service = get_drive_service(creds)

    print("2. Snapshotting databases and compressing project...")
    tar_path, tar_name = create_tar()

    print("3. Uploading; existing backups will be preserved...")
    upload(service, tar_path, tar_name, folder_id)

    tar_path.unlink()
    print("Done.")


if __name__ == "__main__":
    main()
