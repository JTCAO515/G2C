"""Fixed read-only NEEDS source/ABI delta analysis, no runtime alias or mutation."""
import argparse,ast,hashlib,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--needs-repository',type=Path,required=True);a=p.parse_args()
old='c821b34d607016c6dbc1020c203621841f1a60e8';new='4cc9c815293a4e03225b26adfa228fdd0b50b2e7'
def blob(rev,path):return subprocess.check_output(['git','-C',str(a.needs_repository),'show',rev+':'+path])
def nodes(rev,name):
    result={}
    for n in ast.parse(blob(rev,'backend/needs/cj_needs/'+name)).body:
        if isinstance(n,(ast.ClassDef,ast.FunctionDef)):result[n.name]=n
        if isinstance(n,ast.ClassDef):
            for m in n.body:
                if isinstance(m,ast.FunctionDef):result[n.name+'.'+m.name]=m
    return result
checks={}
for path in ['backend/needs/cj_needs/domain.py','backend/needs/cj_needs/__init__.py','backend/needs/sql/candidate.sql']:
    assert blob(old,path)==blob(new,path);checks[path]='UNCHANGED_BYTES'
for name,methods in {'boundary.py':['Boundary','Metadata','Operation.act','Operation.query_action','Operation.detail','Operation.revision'],'postgres.py':['Repository._receipt','Repository._snapshot','Repository.act','Repository.query_action','Repository.detail','Repository.revision']}.items():
    before,after=nodes(old,name),nodes(new,name)
    for method in methods:
        assert ast.dump(before[method])==ast.dump(after[method]),(name,method)
        checks[name+':'+method]='UNCHANGED_AST'
params=nodes(new,'postgres.py')['Repository.__init__'].args
assert [n.arg for n in params.args]==['self','connect','scope','guard'] and [n.arg for n in params.kwonlyargs]==['strict_close'] and isinstance(params.kw_defaults[0],ast.Constant) and params.kw_defaults[0].value is False
checks['postgres.py:Repository.__init__']='ADDITIVE kw-only strict_close=False, original 3 positional args retained'
checks['postgres.py:Repository.transaction']='REVIEWED strict_close opt-in raises ordinary close failure and calls closed guard only when True; legacy default False path retained'
checks['boundary.py:Operation.__run']='REVIEWED additive read_only flag denies methods other than detail/revision; legacy state has no flag, default False'
print(json.dumps(dict(old=old,new=new,checks=checks),indent=2))
