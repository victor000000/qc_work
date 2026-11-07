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
    if len(cls.bases) != 1 or cls.keywords:
        raise ValueError('multiple inheritance or class keywords unsupported')
    if '_v092' in source or 'MarginProbe' in source or cls.decorator_list:
        raise ValueError('reserved identifier or decorated class')
    signatures = {'initialize': ['self'], 'on_data': ['self', 'data'],
                  'on_order_event': ['self', 'event'], 'on_margin_call': ['self', 'requests']}
    # Other class-scope bindings can replace or alias callbacks; fail closed.
    for statement in cls.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(statement):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)) and node.id in signatures:
                raise ValueError('callback binding outside a supported method')
            if isinstance(node, ast.alias) and (node.asname or node.name.split('.')[0]) in signatures:
                raise ValueError('callback import binding')
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in signatures:
                raise ValueError('conditional callback binding')
    init_nodes = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'initialize']
    if len(init_nodes) != 1:
        raise ValueError('one synchronous initialize required')
    source_lines = source.splitlines()
    def indentation(line):
        return line[:len(line) - len(line.lstrip())]
    method_indent = indentation(source_lines[init_nodes[0].lineno - 1])
    body_indent = indentation(source_lines[init_nodes[0].body[0].lineno - 1])
    inserts = []
    for name, args in signatures.items():
        matches = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
        hook = ('self._v092_probe = MarginProbe(_v092_plan)' if name == 'initialize' else
                f'self._v092_probe.observe(self, {name!r})')
        if len(matches) > 1:
            raise ValueError('duplicate callback')
        if matches:
            node = matches[0]
            a = node.args
            if (not isinstance(node, ast.FunctionDef) or node.decorator_list or
                [v.arg for v in a.args] != args or a.posonlyargs or a.kwonlyargs or a.defaults or a.vararg or a.kwarg or
                node.body[0].lineno == node.lineno):
                raise ValueError('unsupported callback signature or layout')
            if any(isinstance(item, (ast.Yield, ast.YieldFrom)) for item in ast.walk(node)):
                raise ValueError('generator callback unsupported')
            first = node.body[0]
            is_doc = isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str)
            position = first.end_lineno if is_doc else first.lineno - 1
            original_line = source.splitlines()[first.lineno - 1]
            indent = original_line[:len(original_line) - len(original_line.lstrip())]
            inserts.append((position, indent + hook + '\n'))
        else:
            if name == 'initialize':
                raise ValueError('initialize required')
            extra = '\n' + method_indent + 'def ' + name + '(' + ', '.join(args) + '):\n' + body_indent + hook + '\n'
            if name == 'on_margin_call':
                extra += body_indent + 'return requests\n'
            inserts.append((cls.end_lineno, extra))
    lines = source.splitlines(keepends=True)
    if lines and not lines[-1].endswith('\n'):
        lines[-1] += '\n'
    for index, value in sorted(inserts, key=lambda item: (item[0], item[1].startswith('\n')), reverse=True):
        lines.insert(index, value)
    # Insert after future imports/docstring to preserve legal Python source.
    header_at = 0
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == '__future__' or isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            header_at = node.end_lineno
        else:
            break
    lines.insert(header_at, 'from margin_probe_v092 import MarginProbe\n_v092_plan = ' + repr(checkpoints) + '\n')
    here = Path(__file__).parent
    files = {'main.py': ''.join(lines), 'margin_diagnostic_v092.py': (here/'margin_diagnostic.py').read_text(),
             'margin_probe_v092.py': (here/'probe.py').read_text().replace('from .margin_diagnostic import', 'from margin_diagnostic_v092 import')}
    for name, content in files.items():
        compile(content, name, 'exec')
    manifest = dict(version='0.9.2', status='assembled_not_submitted', base_source=str(base.resolve()),
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
