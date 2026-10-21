"""Read immutable AUTH git blobs into a temporary import root; never read worktree code."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

REVISION = 'e49ea1a2abcdd82c93a28aeba8b2d6a1248a0f3b'
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
    result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'auth_consumption', '-v'], env=env)
    sys.exit(result.returncode)
