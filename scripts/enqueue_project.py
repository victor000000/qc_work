#!/usr/bin/env python3
"""Submit a Python QC project folder through the shared Rust server queue."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 128_000


def bundle_files(project):
    project = Path(project).resolve()
    main = project / 'main.py'
    if not main.is_file():
        raise ValueError(f'{project} has no main.py')
    files = {}
    for path in sorted(project.rglob('*.py')):
        relative = path.relative_to(project)
        if any(part.startswith('.') or part == '__pycache__' for part in relative.parts):
            continue
        content = path.read_text(encoding='utf-8')
        if len(content.encode('utf-8')) > MAX_BYTES:
            raise ValueError(f'{relative} exceeds {MAX_BYTES} bytes')
        files[relative.as_posix()] = content
    files.pop('main.py')
    return main, files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strategy', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--data-dir', type=Path, default=Path(os.getenv('QC_DATA_DIR', ROOT / 'data')))
    parser.add_argument('--batch')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    main_file, extras = bundle_files(args.project)
    if args.dry_run:
        print(json.dumps({'strategy': args.strategy, 'name': args.name,
                          'main': str(main_file), 'extra_files': list(extras)}, indent=2))
        return
    binary = ROOT / 'target/release/qc-backtest-server'
    if not binary.is_file():
        raise RuntimeError('Build the shared server first: cargo build --release --locked')
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', encoding='utf-8') as handle:
        json.dump(extras, handle)
        handle.flush()
        command = [str(binary), '--data-dir', str(args.data_dir.resolve()), 'queue',
                   '--strategy', args.strategy, '--name', args.name,
                   '--code-file', str(main_file), '--extra-files', handle.name]
        if args.batch:
            command.extend(['--batch', args.batch])
        subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
