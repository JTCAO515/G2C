"""Generate the iOS SDK from the canonical frozen OpenAPI.

The pinned Swift generator drops bare type:null schemas. Its documented type
schema override maps those exact nodes to a strict ExplicitJSONNull codec.
Only the transient generator input differs; the canonical contract is read-only.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
NULL_NAME='CJExplicitJSONNull'


def generator_input(canonical):
    value=copy.deepcopy(canonical)
    schemas=value['components']['schemas']
    if NULL_NAME in schemas:raise ValueError('generator-only null type conflicts with canonical schema')
    replacements=[]
    def walk(node,path):
        if isinstance(node,dict):
            if node.get('type')=='null':
                if set(node)-{'type','description','title'}:raise ValueError('unsupported constrained null shape')
                replacements.append(path)
                result={'$ref':'#/components/schemas/'+NULL_NAME}
                for key in ('description','title'):
                    if key in node:result[key]=node[key]
                return result
            return {key:walk(item,path+[key]) for key,item in node.items()}
        if isinstance(node,list):return [walk(item,path+[str(i)]) for i,item in enumerate(node)]
        return node
    value=walk(value,[])
    value['components']['schemas'][NULL_NAME]={}
    return value,replacements


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'ios/Sources/CJAPI/Generated')
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--provenance',type=Path)
    args=parser.parse_args()
    canonical_path=ROOT/'contracts/api/openapi.json';original=canonical_path.read_bytes()
    value,replacements=generator_input(json.loads(original))
    with tempfile.TemporaryDirectory(prefix='cj-swift-api-') as directory:
        temporary=Path(directory);schema=temporary/'openapi.json';schema.write_text(json.dumps(value,indent=2)+'\n')
        generated=temporary/'swift'
        subprocess.run([str(ROOT/'scripts/swift.sh'),'run','swift-openapi-generator','generate',str(schema),
            '--config',str(ROOT/'ios/scripts/swift-generator.yaml'),'--output-directory',str(generated)],cwd=ROOT,check=True)
        outputs={p.name:p.read_bytes() for p in generated.glob('*.swift')}
        if not outputs:raise RuntimeError('generator produced no Swift output')
        if args.check:
            existing={p.name:p.read_bytes() for p in args.output.glob('*.swift')}
            if existing!=outputs:raise RuntimeError('iOS generated SDK is stale')
        else:
            args.output.mkdir(parents=True,exist_ok=True)
            if set(p.name for p in args.output.glob('*.swift'))-set(outputs):raise RuntimeError('unmanaged generated Swift files')
            for name,data in outputs.items():(args.output/name).write_bytes(data)
        if canonical_path.read_bytes()!=original:raise RuntimeError('canonical OpenAPI changed during generation')
        if args.provenance:
            path=args.provenance.resolve()
            if path.is_relative_to(ROOT):raise ValueError('provenance artifacts must be outside the repository')
            path.write_text(json.dumps(dict(canonical_sha256=hashlib.sha256(original).hexdigest(),
                null_paths=replacements,derived_input_sha256=hashlib.sha256(schema.read_bytes()).hexdigest(),
                outputs={name:hashlib.sha256(data).hexdigest() for name,data in outputs.items()}),indent=2)+'\n')
    print('Canonical contract unchanged; iOS SDK '+('checked' if args.check else 'generated')+'.')

if __name__=='__main__':main()
