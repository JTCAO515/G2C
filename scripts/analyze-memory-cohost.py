"""Read-only fixed producer delta; no runtime import, schema apply or Git mutation."""
import argparse,ast,hashlib,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--memory-repository',type=Path,required=True);a=p.parse_args()
old='426d337b0647d7770f1716fad83f2e5e724d28e4';new='0045e423f004f873e2786aa98b2600b70772a921';cf6='cf6f9138147780de9cd6cd3df86642b0aec6ec5b'
def blob(rev,name):return subprocess.check_output(['git','-C',str(a.memory_repository),'show',rev+':'+name])
def nodes(rev,name):
    root=ast.parse(blob(rev,'backend/memory/cj_memory/'+name))
    result={}
    for node in root.body:
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)):result[node.name]=node
        if isinstance(node,ast.ClassDef):
            for child in node.body:
                if isinstance(child,ast.FunctionDef):result[node.name+'.'+child.name]=child
    return result
checks={}
for name,methods in {'domain.py':['Command','Receipt','Item','Context','Service.save','Service.save_manual','Service.query','Service.detail','Service.groups','Service.list_items','Service.check_fence','Service.with_operation'],'postgres.py':['Repository','Transaction.lock_scope','Transaction.operation','Transaction.source','Transaction.create_manual_source','Transaction.insert','Transaction.detail','Transaction.groups','Transaction.list_items','Transaction.effective']}.items():
    before,after=nodes(old,name),nodes(new,name)
    for method in methods:
        assert ast.dump(before[method])==ast.dump(after[method]),(name,method)
        checks[name+':'+method]='UNCHANGED_AST'
for name in ['backend/memory/schema.sql','backend/memory/cj_memory/manual.py','backend/memory/cj_memory/__init__.py']:
    assert blob(old,name)==blob(new,name);checks[name]='UNCHANGED_BYTES'
name='backend/memory/cj_memory/consumption.py';assert blob(cf6,name)==blob(new,name);checks[name+'@cf6']='UNCHANGED_BYTES'
checks['domain.py:Service.__init__']='ADDITIVE lifecycle_adapter kw-only default None and captured field'
checks['domain.py:Service.effective / postgres.py:Transaction.require_current']='REVIEWED canonical current_context helper; same selection, epoch, item/source/time equality'
checks['operation.py']='REVIEWED additive consume/lifecycle methods, busy flags default false, optional fence and adapter binding capture; old commit/rollback/unknown stages retained'
checks['lifecycle.py']='ADDITIVE restricted adapter, no original parser/SQL/AUTH replacement'
print(json.dumps({'old':old,'new':new,'accepted_consume_source':cf6,'checks':checks},indent=2))
