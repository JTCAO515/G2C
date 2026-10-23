from pathlib import Path
import json
import subprocess

module = Path(__file__).resolve().parents[1]
products = module / '.prepare/Modules/CJFeasibilityClient/.build/out/Products/Debug'
base = ['xcrun','swiftc','-swift-version','6','-typecheck','-I',str(products)]
positive = subprocess.run(base + [str(module/'evidence/PublicAPI.swift')],capture_output=True,text=True)
assert positive.returncode == 0, positive.stderr
negative = module / '.prepare/ForbiddenAPI.swift'
negative.write_text('import CJFeasibilityClient\nlet forged = PreparedFeasibilityRead()\n')
rejected = subprocess.run(base + [str(negative)],capture_output=True,text=True)
assert rejected.returncode != 0 and 'inaccessible' in rejected.stderr and 'internal' in rejected.stderr, rejected.stderr
symbols = module / '.prepare/symbols'; symbols.mkdir(exist_ok=True)
sdk = subprocess.check_output(['xcrun','--show-sdk-path']).decode().strip()
result = subprocess.run(['xcrun','swift-symbolgraph-extract','-module-name','CJFeasibilityClient','-I',str(products),
    '-target','arm64-apple-macos14.0','-sdk',sdk,'-minimum-access-level','public','-output-dir',str(symbols)],capture_output=True,text=True)
assert result.returncode == 0, result.stderr
all_symbols = json.loads((symbols/'CJFeasibilityClient.symbols.json').read_text())['symbols']
initializers = [s['pathComponents'] for s in all_symbols if s['kind']['identifier'] == 'swift.init' and s['pathComponents'][0] == 'FeasibilityModel']
assert initializers == [['FeasibilityModel','init(session:currentBinding:)']], initializers
assert not any(s['pathComponents'][0] in ['FeasibilityTransport','StrictFeasibilityJSON'] for s in all_symbols)
(module/'evidence/public-api.json').write_text(json.dumps({'normal_import_typecheck':'PASS','opaque_work_forge_rejected':'PASS',
    'model_public_initializers':initializers,'internal_transport_and_parser_hidden':'PASS'},indent=2)+'\n')
print('PASS normal-import host typecheck, closed sole model initializer, unforgeable work, internal fixture seam hidden')
