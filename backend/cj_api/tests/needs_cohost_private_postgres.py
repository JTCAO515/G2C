"""Fresh private PostgreSQL two NEEDS and FEASIBILITY cohost cases; canonical synthetic AUTH only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
PORT=55460

def command(argv,log,env):
    with log.open('w') as output:
        subprocess.run([str(x) for x in argv],env=env,stdout=output,stderr=subprocess.STDOUT,check=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auth-repository',type=Path,required=True)
    parser.add_argument('--feasibility-repository',type=Path,required=True)
    parser.add_argument('--needs-repository',type=Path,required=True)
    parser.add_argument('--driver-source',type=Path,required=True)
    parser.add_argument('--private-name',default='.local-cj005-nco-pg')
    args=parser.parse_args()
    if not re.fullmatch(r'\.local-cj005-nco-[a-z0-9-]+',args.private_name):raise RuntimeError('task-private lifecycle directory required')
    private=ROOT/args.private_name
    if any(k.startswith('PG') or k.startswith('LIBPQ') or k in ('DATABASE_URL','CJ_DATABASE_URL') for k in os.environ):raise RuntimeError('ambient DB configuration refused')
    if private.exists() or private.is_symlink():raise RuntimeError('existing private directory refused')
    assert len(str(private/'s'/('.s.PGSQL.'+str(PORT))).encode())<104
    private.mkdir(mode=0o700);(private/'s').mkdir(mode=0o700);(private/'empty.pgpass').touch(mode=0o600)
    clean={'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C','LC_ALL':'C'}
    pg=Path(subprocess.check_output(['pg_config','--bindir'],env=clean,text=True).strip())
    data=private/'data'
    evidence={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'scope':'new private empty PG + in-process ASGI wire tests; actual canonical AUTH with synthetic keys/accounts; no live HTTP listener or real account C2','result':'FAIL','checks':[]}
    def record(name):
        evidence['checks'].append({'name':name,'status':'PASS'});print('PASS '+name,flush=True)
    try:
        exported=subprocess.check_output([sys.executable,'-B',str(ROOT/'scripts/prepare-feasibility-deps.py'),'--auth-repository',str(args.auth_repository),'--source-repository',str(args.feasibility_repository),'--needs-repository',str(args.needs_repository)],cwd=ROOT,text=True).strip()
        pins=json.loads((ROOT/'backend/cj_api/feasibility_pins.json').read_text());evidence['pins']=pins
        evidence['legacy_needs_pins']=json.loads((ROOT/'backend/cj_api/needs_pins.json').read_text())
        # Reuse only immutable driver code, never old data/config/socket/logs.
        packages=[args.driver_source/'psycopg',args.driver_source/'psycopg-3.2.10.dist-info']
        assert not args.driver_source.is_symlink() and all(p.is_dir() for p in packages)
        files={}
        for package in packages:
            for path in [package,*package.rglob('*')]:
                assert not path.is_symlink() and path.resolve().is_relative_to(args.driver_source.resolve())
                if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':files[str(path.relative_to(args.driver_source))]=hashlib.sha256(path.read_bytes()).hexdigest()
        assert 'Version: 3.2.10\n' in (packages[1]/'METADATA').read_text()
        (private/'driver').mkdir(mode=0o700)
        for package in packages:shutil.copytree(package,private/'driver'/package.name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        for name,digest in files.items():assert hashlib.sha256((private/'driver'/name).read_bytes()).hexdigest()==digest
        evidence['driver']={'version':'3.2.10','file_count':len(files),'manifest_sha256':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()}
        (private/'driver-manifest.json').write_text(json.dumps(files,indent=2)+'\n')
        sys.path[:0]=[str(private/'driver'),str(ROOT/'backend'),str(Path(exported)/'backend/auth'),str(Path(exported)/'backend/needs'),str(Path(exported)/'backend/feasibility'),str(ROOT/'backend/message'),str(ROOT/'backend/cj_api/tests')]
        import psycopg
        import unittest
        assert psycopg.__version__=='3.2.10' and Path(psycopg.__file__).resolve().is_relative_to((private/'driver').resolve())
        evidence['driver']['implementation']=psycopg.pq.__impl__
        command([pg/'initdb','-D',data,'--username=cj005nco','--auth-local=trust','--auth-host=reject','--encoding=UTF8','--locale=C','--no-clean'],private/'initdb.txt',clean)
        command([pg/'pg_ctl','-D',data,'-l',private/'postgres.log','-o',shlex.join(['-c','listen_addresses=','-k',str(private/'s'),'-p',str(PORT),'-c','unix_socket_permissions=0700']),'-w','start'],private/'pg-start.txt',clean)
        config=dict(host=str(private/'s'),port=PORT,user='cj005nco',dbname='postgres',passfile=str(private/'empty.pgpass'),connect_timeout=5,options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=public')
        with psycopg.connect(**config) as c:
            identity=c.execute("SELECT current_setting('data_directory'),current_setting('listen_addresses'),current_setting('unix_socket_directories'),current_user,current_database(),version()").fetchone()
            assert identity[:5]==(str(data),'',str(private/'s'),'cj005nco','postgres')
            assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
            evidence['schemas']={}
            for repo,rev,name in [(args.needs_repository,pins['sources'][1]['commit'],'backend/needs/sql/candidate.sql')]:
                raw=subprocess.check_output(['git','-C',str(repo),'show',rev+':'+name])
                c.execute(raw.decode());evidence['schemas'][name]=hashlib.sha256(raw).hexdigest()
            assert c.execute('SELECT count(*) FROM cj_needs_revision').fetchone()[0]==0
        evidence['postgres']={'identity':list(identity),'role_scope':'new fixture bootstrap role only; no production grants/RLS/permissions proof'}
        record('verified new empty private PostgreSQL, no TCP, exact NEEDS candidate schema only')
        config_path=private/'test-config.json';config_path.touch(mode=0o600);config_path.write_text(json.dumps(config))
        os.environ['CJ005_FEASIBILITY_PG_CONFIG']=str(config_path)
        suite=unittest.defaultTestLoader.loadTestsFromName('needs_cohost_checks.NeedsCohostChecks')
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        evidence['tests']={'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)}
        assert result.wasSuccessful()
        for name,digest in files.items():
            assert hashlib.sha256((private/'driver'/name).read_bytes()).hexdigest()==digest
            assert hashlib.sha256((args.driver_source/name).read_bytes()).hexdigest()==digest
        evidence['result']='PASS'
    finally:
        if (data/'postmaster.pid').exists():command([pg/'pg_ctl','-D',data,'-m','fast','-w','stop'],private/'pg-stop.txt',clean)
        assert not (data/'postmaster.pid').exists() and not (private/'s'/('.s.PGSQL.'+str(PORT))).exists()
        evidence['safe_stop']='PASS'
        (private/'result.json').write_text(json.dumps(evidence,indent=2)+'\n')
        print('PASS exact new private PostgreSQL stopped; data retained',flush=True)

if __name__=='__main__':main()
