"""Assemble a fresh, unsubmitted diagnostic source with auditable provenance."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
from .probe import validate_plan


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build(base, plan, out):
    base, plan, out = Path(base), Path(plan), Path(out)
    if out.exists():
        raise ValueError('new output directory required')
    raw, plan_raw = base.read_bytes(), plan.read_bytes()
    checkpoints = validate_plan(json.loads(plan_raw))
    source = raw.decode()
    tree = ast.parse(source)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and any(isinstance(b, ast.Name) and b.id == 'QCAlgorithm' for b in n.bases)]
    if len(classes) != 1:
        raise ValueError('require one direct QCAlgorithm class')
    cls = classes[0]
    if '_v091' in source or 'MarginProbe' in source or cls.decorator_list:
        raise ValueError('reserved identifier or decorated class')
    signatures = {'initialize': ['self'], 'on_data': ['self', 'data'],
                  'on_order_event': ['self', 'event'], 'on_margin_call': ['self', 'requests']}
    inserts = []
    for name, args in signatures.items():
        matches = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
        hook = ('self._v091_probe = MarginProbe(_v091_plan)' if name == 'initialize' else
                f'self._v091_probe.observe(self, {name!r})')
        if len(matches) > 1:
            raise ValueError('duplicate callback')
        if matches:
            node = matches[0]
            a = node.args
            if (not isinstance(node, ast.FunctionDef) or node.decorator_list or
                [v.arg for v in a.args] != args or a.posonlyargs or a.kwonlyargs or a.defaults or a.vararg or a.kwarg or
                node.body[0].lineno == node.lineno):
                raise ValueError('unsupported callback signature or layout')
            inserts.append((node.body[0].lineno - 1, ' ' * node.body[0].col_offset + hook + '\n'))
        else:
            if name == 'initialize':
                raise ValueError('initialize required')
            extra = '\n    def ' + name + '(' + ', '.join(args) + '):\n        ' + hook + '\n'
            if name == 'on_margin_call':
                extra += '        return requests\n'
            inserts.append((cls.end_lineno, extra))
    lines = source.splitlines(keepends=True)
    if lines and not lines[-1].endswith('\n'):
        lines[-1] += '\n'
    for index, value in sorted(inserts, reverse=True):
        lines.insert(index, value)
    # Insert after future imports/docstring to preserve legal Python source.
    header_at = 0
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == '__future__' or isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            header_at = node.end_lineno
        else:
            break
    lines.insert(header_at, 'from margin_probe_v091 import MarginProbe\n_v091_plan = ' + repr(checkpoints) + '\n')
    here = Path(__file__).parent
    files = {'main.py': ''.join(lines), 'margin_diagnostic_v091.py': (here/'margin_diagnostic.py').read_text(),
             'margin_probe_v091.py': (here/'probe.py').read_text().replace('from .margin_diagnostic import', 'from margin_diagnostic_v091 import')}
    for name, content in files.items():
        compile(content, name, 'exec')
    manifest = dict(version='0.9.1', status='assembled_not_submitted', base_source=str(base.resolve()),
                    base_sha256=digest(raw), plan_sha256=digest(plan_raw), plan=checkpoints,
                    files={name: digest(content.encode()) for name, content in files.items()},
                    cloud_parity=False, economic_acceptance=False)
    out.mkdir(parents=True)
    for name, content in files.items():
        (out/name).write_text(content)
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('base', 'plan', 'out'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.base, args.plan, args.out), indent=2))
