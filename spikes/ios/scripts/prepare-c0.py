#!/usr/bin/env python3
"""Read only an immutable C0 commit. No tracked copy of the formal schema."""
import pathlib, subprocess, sys, hashlib, json
root = pathlib.Path(__file__).resolve().parents[1]
repo = pathlib.Path(sys.argv[1]).resolve()
head = 'db9c040f262032acaf5375db43d7169b3217e504'
def read(path): return subprocess.check_output(['git','-C',str(repo),'show',f'{head}:{path}'])
work = root/'.cache/c0-consumer'
sources = work/'Sources/C0API'; sources.mkdir(parents=True,exist_ok=True)
tests = work/'Tests/C0Tests'; tests.mkdir(parents=True,exist_ok=True)
schema = read('contracts/api/openapi.json')
(work/'openapi.json').write_bytes(schema)
subprocess.run([str(root/'.build/debug/swift-openapi-generator'),'generate',str(work/'openapi.json'),'--mode','types','--mode','client','--access-modifier','public','--output-directory',str(sources)],check=True)
fixtures=tests/'Fixtures';fixtures.mkdir(exist_ok=True)
for name in ['normal','failure','unknown','conflict']:
 (fixtures/(name+'.json')).write_bytes(read(f'contracts/api/examples/{name}.json'))
(tests/'C0Tests.swift').write_bytes((root/'C0Tests/C0Tests.swift').read_bytes())
# Consume official pinned runtime checkout already resolved by this spike.
runtime=root/'.build/checkouts/swift-openapi-runtime'
(work/'Package.swift').write_text('''// swift-tools-version: 6.2
import PackageDescription
let package = Package(name: "C0Consumer", platforms: [.macOS(.v15), .iOS(.v18)], dependencies: [.package(path: "'''+str(runtime)+'''")], targets: [.target(name: "C0API", dependencies: [.product(name: "OpenAPIRuntime", package: "swift-openapi-runtime")]), .testTarget(name: "C0Tests", dependencies: ["C0API"], resources: [.copy("Fixtures")])])
''')
(root/'evidence/c0-source.json').write_text(json.dumps({'head':head,'path':'contracts/api/openapi.json','sha256':hashlib.sha256(schema).hexdigest(),'generator':'1.14.2','snapshot':'ignored .cache/c0-consumer; never formal source'},indent=2)+'\n')
print(work)
