"""Build with an explicit source-only context, never workspace secrets or logs."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def source_context(root, destination):
    entries=subprocess.check_output(['git','ls-tree','-rz','HEAD','--',
        'pyproject.toml','uv.lock','backend','scripts','deploy'],cwd=root).split(b'\0')
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
        target=destination/path;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(subprocess.check_output(['git','cat-file','blob',oid.decode()],cwd=root))


def main():
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    print('BUILD_SOURCE_COMMIT='+revision,flush=True)
    with tempfile.TemporaryDirectory(prefix='g2c-build-') as directory:
        source_context(ROOT,Path(directory))
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
