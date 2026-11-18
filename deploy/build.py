"""Build with an explicit source-only context, never workspace secrets or logs."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def source_context(root, destination,revision='HEAD'):
    entries=subprocess.check_output(['git','ls-tree','-rz',revision,'--',
        'pyproject.toml','uv.lock','backend','scripts','deploy',
        'eval/optimization/cases.v2.json','eval/optimization/score_v2.py','tooling/optimization/uv.lock',
        'eval/lio_simulated_user/__init__.py','eval/lio_simulated_user/core.py',
        'eval/lio_simulated_user/runner.py','eval/lio_simulated_user/profiles.v1.json',
        'knowledge/visitor/entries'],cwd=root).split(b'\0')
    exported_directories={destination}
    for entry in entries:
        if not entry:continue
        metadata,raw_path=entry.split(b'\t',1)
        mode,kind,oid=metadata.split()
        path=Path(raw_path.decode())
        if (mode not in (b'100644',b'100755') or kind!=b'blob'
                or any(part.startswith('.') or part in ('evidence','private-pg','tests') for part in path.parts)
                or path.suffix not in ('.py','.sql','.json','.md','.toml','.lock','.yaml','.conf','.Dockerfile')
                    and path.name!='Dockerfile'):
            continue
        target=destination/path
        if target.parent not in exported_directories:
            target.parent.mkdir(parents=True,exist_ok=True)
            for directory in target.parents:
                if directory in exported_directories:break
                directory.chmod(0o755)
                exported_directories.add(directory)
        # The context root stays private. Copied public blobs must be
        # readable by the image runtime user regardless of the build umask.
        target.write_bytes(subprocess.check_output(['git','cat-file','blob',oid.decode()],cwd=root))
        target.chmod(0o644)


def main():
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    print('BUILD_SOURCE_COMMIT='+revision,flush=True)
    with tempfile.TemporaryDirectory(prefix='g2c-build-') as directory:
        source_context(ROOT,Path(directory),revision)
        import os
        uid=os.getuid()
        if uid in (0,999):raise ValueError('runtime uid must be separate from database/operator uid')
        subprocess.run(['docker','build','-f',str(Path(directory)/'deploy/postgres.Dockerfile'),
                        '--build-arg','CJ_RUNTIME_UID='+str(uid),'--label','org.opencontainers.image.revision='+revision,
                        '-t','g2c-m4-postgres:current',directory],check=True)
        subprocess.run(['docker', 'build', '-f', str(Path(directory) / 'deploy/Dockerfile'),
                        '--label','org.opencontainers.image.revision='+revision,'-t', 'g2c-m4-local:current', directory], check=True)


if __name__ == '__main__':
    main()
