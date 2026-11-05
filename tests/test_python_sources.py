"""Parse research sources without importing algorithms or submitting experiments."""
import ast
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {'.git', '.local', '.venv', 'target', '__pycache__', '.pytest_cache'}


def test_all_python_sources_are_syntactically_valid():
    errors = []
    for base, directories, files in os.walk(ROOT, followlinks=False):
        directories[:] = [d for d in directories if d not in EXCLUDE and not d.startswith('.venv')]
        for name in files:
            if name.endswith('.py'):
                path = Path(base) / name
                try:
                    ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
                except (SyntaxError, UnicodeDecodeError) as error:
                    errors.append(f'{path.relative_to(ROOT)}: {error}')
    assert not errors, '\n'.join(errors)
