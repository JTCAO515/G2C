"""Export only pinned runtime Git blobs into clone-local ignored dependencies.

No network, checkout, source-tree edit or provider configuration. Inputs are
read-only Git repositories; never imports their moving working files.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--auth-repository', type=Path, required=True)
    parser.add_argument('--message-repository', type=Path, required=True)
    args = parser.parse_args()
    pins = json.loads((ROOT / 'backend/cj_api/composition_pins.json').read_text())
    # Keep each exact source tuple separate; never overwrite earlier pinned evidence.
    export_key = '-'.join(source['commit'] for source in pins['sources'])
    target = ROOT / '.local/composition-deps' / export_key
    if target.is_symlink():
        raise ValueError('dependency export root must not be a symlink')
    target.mkdir(parents=True, exist_ok=True)
    for source in pins['sources']:
        repository = getattr(args, source['name'] + '_repository')
        for path, expected in source['files'].items():
            data = subprocess.check_output(['git', '-C', str(repository), 'show', source['commit'] + ':' + path])
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('pinned dependency content mismatch')
            # Retain the original layout; no second implementation is committed.
            output = target / path
            if output.exists():
                if output.is_symlink() or output.read_bytes() != data:
                    raise ValueError('existing dependency export differs; preserve it for inspection')
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(data)
        print(f"PASS fixed {source['name']} {source['commit']} ({len(source['files'])} runtime blobs)")
    print('Export root: ' + str(target))
    print('Use only the printed fixed export via PYTHONPATH for owner tests; production integration must contain the original commits.')


if __name__ == '__main__':
    main()
