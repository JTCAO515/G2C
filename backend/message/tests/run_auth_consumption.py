"""Read immutable AUTH git blobs into a temporary import root; never read worktree code."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

REVISION = '79f88b6552da1bd3d4b27e22f64a158bddf2853b'
source = sys.argv[1]
root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='cj009-auth-fixed-') as tmp:
    package = Path(tmp) / 'cj_auth'
    package.mkdir()
    for name in ('__init__.py', 'interfaces.py', 'admission.py'):
        blob = subprocess.check_output(['git', '-C', source, 'show',
                                       REVISION + ':backend/auth/cj_auth/' + name])
        (package / name).write_bytes(blob)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((tmp, str(root), str(root/'tests'))))
    result = subprocess.run([sys.executable, '-B', '-m', 'unittest', *(sys.argv[2:] or ['auth_consumption']), '-v'], env=env)
    sys.exit(result.returncode)
