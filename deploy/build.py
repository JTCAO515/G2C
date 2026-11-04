"""Build with an explicit source-only context, never workspace secrets or logs."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = [ROOT / 'pyproject.toml', ROOT / 'uv.lock']
    for directory in ('backend', 'scripts', 'deploy'):
        files.extend(p for p in (ROOT / directory).rglob('*') if p.is_file()
                     and not p.is_symlink() and not any(
                         part.startswith('.') or part in ('__pycache__', 'evidence', 'private-pg', 'tests')
                         for part in p.relative_to(ROOT).parts))
    with tempfile.TemporaryDirectory(prefix='g2c-build-') as directory:
        for path in sorted(files):
            target = Path(directory) / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        subprocess.run(['docker', 'build', '-f', str(Path(directory) / 'deploy/Dockerfile'),
                        '-t', 'g2c-m4-local:current', directory], check=True)


if __name__ == '__main__':
    main()
