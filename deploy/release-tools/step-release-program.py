"""B-only single-step schema cutover after the 59 chain (S line, generalized from first59-release-program).

Preflight is read-only; apply is one-shot. Runs on the Hong Kong host as root from
/srv/g2c-beta/probes/step<TARGET>-release-<day>/ with its gate.json next to it:

    python3 -B step-release-program.py <dir>/gate.json            # preflight
    python3 -B step-release-program.py <dir>/gate.json --apply    # one cutover

Order: close API (drain proof) -> stop worker -> original data snapshot and safety export
with the old operator image (schema 1..FROM) -> `demo_schema.upgrade(target=TARGET)` with the
new operator image (#2017: one migration, its own signed anchor) -> the original rows and
sequences are unchanged, the tables the migration's down would drop are empty, cj_ops_console
stays NOLOGIN, the 59 and every later anchor are COMPLETE -> both selectors switch atomically ->
API/worker start on the new image -> readiness and a final idle proof. Any failure after
ingress closes leaves API/worker stopped for reconciliation: it never starts the FROM binary
on TARGET and never rewinds data. Source CI, reviews, the release range and hk-verify are
checked before the gate is written; the gate pins the exact images that hk-verify compared.
"""
import fcntl,hashlib,json,os,re,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path('/srv/g2c-beta')
SOURCE='dfc8a8d8ccef1bb6c893a9b95ed5ede01ee13439'  # filled after the source is chosen; first push CI verified before the gate
OLD='e0bea8430d1223b23919d82ae276af03b878b575'  # running after first59
OLD_OPERATOR='e0bea8430d1223b23919d82ae276af03b878b575'
FROM,TARGET=59,60
FILES=('common.env','api.env','worker.env','operator.env','deploy/hk/compose.yaml','deploy/hk/compose.local-pg.yaml')
# 0060 adds no column to an existing table; a later step that does must list it here.
ADDED_COLUMNS={}

def command(arguments):
    return subprocess.check_output(arguments,stderr=subprocess.PIPE,timeout=300)

def inspect(name):return json.loads(command(['docker','inspect',name]))[0]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def instant(value):return datetime.strptime(value,'%Y-%m-%dT%H:%M:%S.%f+00:00').replace(tzinfo=timezone.utc)
def idle(proof):
    return proof['global_pending']==proof['global_active']==0 and not any(
        proof[k].get(s,0)for k,states in (('background_states',('queued','running','publishing')),
            ('memory_states',('pending','inflight')))for s in states)

def selectors(raw):
    if b'\r'in raw:raise ValueError('canonical LF selector required')
    result={}
    for line in raw.decode().splitlines():
        if not line.strip()or line.startswith('#'):continue
        match=re.fullmatch(r'(CJ_BETA_IMAGE|CJ_BETA_OPERATOR_IMAGE)=([^\s]+)',line)
        if match is None or match[1]in result:raise ValueError('single canonical selector assignment required')
        result[match[1]]=match[2]
    if set(result)!={'CJ_BETA_IMAGE','CJ_BETA_OPERATOR_IMAGE'}:raise ValueError('complete canonical selectors required')
    return result

PREFIX=("from pathlib import Path;import json;from deploy.hk.configuration import load_secret_environment;"
        "load_secret_environment('recovery');from deploy.hk import checkpoint;")

def snapshot_program(tables=None,sequences=None):
    """Row-multiset hashes of the original tables without the two added columns, plus sequences.

    jsonb minus a missing key is a no-op, so the same expression hashes the FROM and TARGET rows alike.
    """
    added={table:column for table,(column,_) in ADDED_COLUMNS.items()}
    return PREFIX+(
        "from deploy.hk import staging;import migrate,hashlib;from psycopg import sql\n"
        "added="+repr(added)+"\n"
        "with checkpoint.operator()as pair:\n db=pair[0]\n with db.transaction():\n"
        "  db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')\n"
        "  tables="+("[t for t in staging.business_tables(migrate.inventory(db))]" if tables is None else repr(tables))+"\n"
        "  names="+("staging.sequence_names(db)" if sequences is None else repr(sequences))+"\n"
        "  data={}\n"
        "  for t in tables:\n"
        "   rows=db.execute(sql.SQL(\"SELECT encode(sha256(convert_to((to_jsonb(r)-%s::text)::text,'UTF8')),'hex') FROM {} r ORDER BY 1\").format(sql.Identifier(*t.split('.'))),(added.get(t,''),)).fetchall()\n"
        "   data[t]=dict(count=len(rows),sha256=hashlib.sha256(''.join(x[0] for x in rows).encode('ascii')).hexdigest())\n"
        "  print(json.dumps({'tables':tables,'data':data,'sequences':staging.sequence_state(db,names)},sort_keys=True))")

QUALIFY=PREFIX+(
    "from deploy.hk import demo_schema;import migrate\n"
    "with checkpoint.operator()as pair:\n db=pair[0]\n with db.transaction():\n"
    "  db.execute('SET TRANSACTION READ ONLY')\n"
    "  assert migrate.applied(db)==list(range(1,"+str(TARGET+1)+"))\n"
    "  demo_schema.rollback_rows(db,"+str(TARGET)+")\n"
    "  assert db.execute(\"SELECT rolcanlogin FROM pg_roles WHERE rolname='cj_ops_console'\").fetchall()==[(False,)]\n"
    +"".join("  assert db.execute("+repr('SELECT count(*) FROM '+table+' WHERE NOT ('+predicate+')')+").fetchone()==(0,)\n"
             for table,(_,predicate) in ADDED_COLUMNS.items())+
    "  prior=checkpoint.verified(Path('/control/demo-schema59.json'))\n"
    "  assert prior['state']=='COMPLETE' and prior['from_version']==55\n"
    "  for n in range(60,"+str(TARGET+1)+"):\n"
    "   marker=checkpoint.verified(Path('/control/demo-schema%d.json'%n))\n"
    "   assert marker['state']=='COMPLETE' and 'from_version' not in marker and marker['lineage']==prior['lineage']\n"
    "  print('SCHEMA"+str(TARGET)+"_QUALIFIED')")

def main(arguments=None):
    args=sys.argv[1:]if arguments is None else arguments
    if len(args)not in(1,2)or len(args)==2 and args[1]!='--apply':raise ValueError('explicit preflight or one apply required')
    if re.fullmatch('[0-9a-f]{40}',SOURCE)is None:raise ValueError('reviewed fixed source required')
    gate_path=Path(args[0]);gate=json.loads(gate_path.read_bytes())
    if(gate['source'],gate['previous_source'],gate['previous_operator_source'])!=(SOURCE,OLD,OLD_OPERATOR):
        raise ValueError('fixed release identities required')
    directory=gate_path.parent
    if re.fullmatch(r'step'+str(TARGET)+r'-release-20261[12][0-9]{2}',directory.name)is None or directory.parent!=ROOT/'probes':
        raise ValueError('fixed private release directory required')
    if digest(Path(__file__))!=gate['script_sha256']:raise ValueError('fixed reviewed release program required')
    def save(name,value):
        fd=os.open(str(directory/name),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb')as f:f.write(json.dumps(value,sort_keys=True).encode());f.flush();os.fsync(f.fileno())
        fd=os.open(str(directory),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
    def window():
        now=datetime.now(timezone.utc);start=instant(gate['starts_at']);end=instant(gate['ends_at'])
        if not start<=now<end or not 0<(end-start).total_seconds()<=7200:
            raise ValueError('current bounded announced-idle window required')
    base=['docker','compose','--env-file',str(ROOT/'compose.env'),'-f',str(ROOT/'deploy/hk/compose.yaml'),
        '-f',str(ROOT/'deploy/hk/compose.local-pg.yaml')]
    lock=(ROOT/'probes/application-deploy.lock').open('r');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    window()
    if not gate['independent_review_approved']:raise ValueError('independent review of this program required')
    static={name:digest(ROOT/name)for name in FILES}
    if static!=gate['configuration_sha256']:raise ValueError('original configuration changed')
    selector=(ROOT/'compose.env').read_bytes()
    if hashlib.sha256(selector).hexdigest()!=gate['selector_sha256']:raise ValueError('original selector changed')
    if any(key in os.environ for key in ('CJ_BETA_IMAGE','CJ_BETA_OPERATOR_IMAGE')):
        raise ValueError('ambient selectors forbidden')
    if selectors(selector)!={'CJ_BETA_IMAGE':'g2c-beta:'+OLD,'CJ_BETA_OPERATOR_IMAGE':'g2c-beta-operator:'+OLD_OPERATOR}:
        raise ValueError('single exact original selectors required')
    for name,key,source in (('g2c-beta:'+SOURCE,'image_id',SOURCE),
            ('g2c-beta-operator:'+SOURCE,'operator_image_id',SOURCE),
            ('g2c-beta:'+OLD,'previous_image_id',OLD),
            ('g2c-beta-operator:'+OLD_OPERATOR,'previous_operator_image_id',OLD_OPERATOR)):
        item=inspect(name)
        if item['Id']!=gate[key]or item['Architecture']!='amd64'or item['Config']['Labels']['org.opencontainers.image.revision']!=source:
            raise ValueError('exact actual loaded image required')
    for role in ('api','worker'):
        item=inspect('g2c-beta-'+role+'-1')
        if(item['Image']!=gate['previous_image_id']or not item['State']['Running']or
                item['Config']['Labels']['org.opencontainers.image.revision']!=OLD or item['Config']['Cmd']!=[role]):
            raise ValueError('original running application required')
    control=(ROOT/'control/budget/adoption.json').read_bytes()
    expected_selector=selector
    def unchanged():
        if({name:digest(ROOT/name)for name in FILES}!=static or
                (ROOT/'control/budget/adoption.json').read_bytes()!=control or
                (ROOT/'compose.env').read_bytes()!=expected_selector):
            raise ValueError('original configuration or financial control changed')
        for name,key in (('g2c-beta:'+SOURCE,'image_id'),('g2c-beta-operator:'+SOURCE,'operator_image_id'),
                ('g2c-beta-operator:'+OLD_OPERATOR,'previous_operator_image_id')):
            if inspect(name)['Id']!=gate[key]:raise ValueError('pinned image tag changed')
    def run(image,program,*,write=False):
        flags=['docker','run','--pull=never','--rm','--network','none','--read-only','--tmpfs','/tmp',
            '--user','10001:10001','--env-file',str(ROOT/'common.env'),'--entrypoint','python']
        for source,target,mutable in (('operator.env','/run/secrets/operator.env',False),
                ('control','/control',write),('local-pg-socket','/run/g2c-pg',False),
                ('backups','/backups',write),('budget','/budget',False),
                ('probes/836-platform-release-proof-plan.json','/plan.json',False),
                ('probes/836-release-export.py','/export.py',False),
                ('836-platform-release-evidence','/evidence',False)):
            mount='type=bind,src='+str(ROOT/source)+',dst='+target+(''if mutable else',readonly')
            flags+=['--mount',mount]
        if write:unchanged();window()
        execution=['-B',program]if program=='/export.py'else['-B','-c',program]
        output=command(flags+[image,*execution])
        if write:window()
        return output
    def proof(image):return json.loads(run(image,'/export.py'))
    old_image=gate['previous_image_id'];new_image=gate['image_id']
    before=proof(old_image)
    if not idle(before)or before['ledger']!=gate['ledger']:raise ValueError('empty original financial anchor required')
    window();unchanged()
    print(json.dumps(dict(stage='STEP%d_PREFLIGHT_PASS'%TARGET,ledger=before['ledger'],source=SOURCE)),flush=True)
    if '--apply'not in args:return
    save('intent.json',dict(source=SOURCE,gate_sha256=digest(gate_path),ledger=before['ledger'],
        original_selector_sha256=hashlib.sha256(selector).hexdigest(),configuration_sha256=static))
    closed=False
    try:
        unchanged();window();closed=True;command(base+['stop','-t','20','api'])
        drained=proof(old_image);save('drained.json',drained)
        if not idle(drained)or drained['ledger']!=before['ledger']:raise ValueError('new original during ingress close')
        unchanged();window();command(base+['stop','-t','20','worker']);window();unchanged()
        original=json.loads(run(gate['previous_operator_image_id'],snapshot_program()))
        save('original-data.json',original)
        pre=PREFIX+"m=checkpoint.export(Path('/backups/step"+str(TARGET)+"-before-'+"+repr(SOURCE[:8])+"),Path('/control'));print(json.dumps({'schema':m['schema'],'dump_sha256':m['dump_sha256'],'lineage':m['lineage']}))"
        backup=json.loads(run(gate['previous_operator_image_id'],pre,write=True));save('before-backup.json',backup)
        if backup['schema']!=list(range(1,FROM+1)):raise ValueError('original schema'+str(FROM)+' safety checkpoint required')
        window();unchanged()
        upgrade=PREFIX+"from deploy.hk import demo_schema;demo_schema.upgrade(Path('/control'),Path('/backups'),target="+str(TARGET)+")"
        run(gate['operator_image_id'],upgrade,write=True)
        after=json.loads(run(gate['operator_image_id'],snapshot_program(original['tables'],list(original['sequences']))))
        save('schema%d-data.json'%TARGET,after)
        if after!=original:raise ValueError('original data or sequence changed during additive'+str(TARGET))
        run(gate['operator_image_id'],QUALIFY)
        upgraded=proof(new_image);save('schema%d-proof.json'%TARGET,upgraded)
        if not idle(upgraded)or upgraded['ledger']!=before['ledger']:raise ValueError('original ledger or drain changed')
        window();unchanged()
        updated=selector.decode()
        for key,old,new in (('CJ_BETA_IMAGE','g2c-beta:'+OLD,'g2c-beta:'+SOURCE),
                ('CJ_BETA_OPERATOR_IMAGE','g2c-beta-operator:'+OLD_OPERATOR,'g2c-beta-operator:'+SOURCE)):
            pattern=r'(?m)^'+key+'='+re.escape(old)+r'$'
            if len(re.findall(pattern,updated))!=1:raise ValueError('exact selector occurrence required')
            updated=re.sub(pattern,key+'='+new,updated)
        save('selector.before.json',dict(sha256=hashlib.sha256(selector).hexdigest()))
        kept=directory/'compose.before.env'
        fd=os.open(str(kept),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb')as f:f.write(selector);f.flush();os.fsync(f.fileno())
        p=ROOT/'compose.env';metadata=p.stat();temporary=directory/'compose.pending.env'
        fd=os.open(str(temporary),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,metadata.st_mode&0o777)
        with os.fdopen(fd,'wb')as f:f.write(updated.encode());f.flush();os.fsync(f.fileno())
        os.chown(str(temporary),metadata.st_uid,metadata.st_gid);unchanged();window();temporary.replace(p)
        expected_selector=updated.encode()
        directory_fd=os.open(str(ROOT),os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
        unchanged();window();command(base+['up','-d','--no-deps','api','worker'])
        end=time.monotonic()+180
        while True:
            api=inspect('g2c-beta-api-1');worker=inspect('g2c-beta-worker-1')
            if api['Image']!=new_image or worker['Image']!=new_image:raise ValueError('new actual image differs')
            if api['State'].get('Health',{}).get('Status')=='healthy'and worker['State']['Running']:
                window();break
            if time.monotonic()>end:raise ValueError('new application readiness unknown')
            window();time.sleep(3)
        unchanged();window();post=proof(new_image);save('post.json',post)
        if not idle(post)or post['ledger']!=before['ledger']:raise ValueError('post-cutover original work requires reconciliation')
        window();save('result.json',dict(stage='STEP%d_CUTOVER_PASS'%TARGET,source=SOURCE,ledger=post['ledger'],
            image_id=new_image,operator_image_id=gate['operator_image_id'],schema=TARGET,
            rollback='check-rollback %d then down to %d and the %s image; no schema%d restart on %d'%(TARGET,FROM,OLD[:8],FROM,TARGET),
            provider_calls=0))
        print('STEP%d_CUTOVER_PASS'%TARGET,flush=True)
    except BaseException:
        if closed:command(base+['stop','-t','20','api','worker'])
        raise

if __name__=='__main__':main()
