"""Read exact Git objects into this module's ignored local dependency closure."""
from pathlib import Path
import hashlib,json,subprocess
MODULE=Path(__file__).resolve().parents[2]
REPO=MODULE.parents[2]
INPUTS=REPO.parent
BASE='e98f9cd31a8117dce16bb6d7373a65203b1cc393'
SHARED='5075bcf604e959d5c4592071a1e9de39d8687395'
TRIP='a5cc42005c69811ccb05754793107141fb4a9f02'
SDK='f87a78a9d8984c59905e385483f17dddd8144d8a'
OUT=MODULE/'.build/f87-5075-a5cc'
OUT.mkdir(parents=True,exist_ok=False)
modules=OUT/'modules'
records={}
def git(repo,*args):return subprocess.check_output(['git','-C',str(repo),*args])
def write(path,data,source):
    path.parent.mkdir(parents=True,exist_ok=True)
    assert not path.exists()
    path.write_bytes(data)
    records[str(path.relative_to(OUT))]={'sha256':hashlib.sha256(data).hexdigest(),'source':source}
def extract(repo,pin,prefix,target):
    for entry in git(repo,'ls-tree','-r',pin,prefix).decode().splitlines():
        metadata,path=entry.split('\t');mode,kind,_=metadata.split()
        assert mode in ('100644','100755') and kind=='blob',(mode,path)
        rel=Path(path).relative_to(prefix)
        write(target/rel,git(repo,'show',pin+':'+path),str(repo)+':'+pin+':'+path)
extract(INPUTS/'cj-009-memory-api-pin',SHARED,'ios/Modules/CJMessageClient',modules/'CJMessageClient')
extract(INPUTS/'cj-015-trip-client',TRIP,'ios/Modules/CJTripClient',modules/'CJTripClient')
extract(REPO,BASE,'ios/Modules/CJAuth',modules/'CJAuth')
# Only own candidate manifest, exact lock and unchanged business sources/tests are copied.
paths=['Package.swift','Package.resolved']
paths += [str(p.relative_to(MODULE)) for part in ['Sources','Tests'] for p in (MODULE/part).rglob('*') if p.is_file()]
for rel in sorted(paths):
    data=(MODULE/rel).read_bytes()
    if rel!='Package.swift':assert data==git(REPO,'show',BASE+':'+str((MODULE/rel).relative_to(REPO)))
    write(modules/'CJManualPreviewClient'/rel,data,'candidate:'+rel)
source=INPUTS/'cj-005-foundation'
manifest=json.loads(git(INPUTS/'cj-009-memory-api-pin','show',SHARED+':ios/Modules/CJMessageClient/evidence/generated-pin.json'))
assert manifest['commit']==SDK
export=modules/'CJMessageClient/.generated'/SDK/'CJFoundation'
for path,sha in manifest['sha256'].items():
    data=git(source,'show',SDK+':'+path);assert hashlib.sha256(data).hexdigest()==sha
    write(export/Path(path).relative_to('ios'),data,str(source)+':'+SDK+':'+path)
# All active local pins name this exact SDK. No substitutions in sibling inputs.
for name in ['CJMessageClient','CJTripClient','CJManualPreviewClient']:
    text=(modules/name/'Package.swift').read_text();assert SDK in text
receipt={'base':BASE,'shared':SHARED,'trip':TRIP,'sdk':SDK,'auth_source':BASE,'root':str(OUT),'files':records}
Path(__file__).with_name('isolated-inputs.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(modules/'CJManualPreviewClient')
