"""Read-only fixed-input and package-graph check; no generation or network."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

API_REPO = sys.argv[1]
GRAPH = Path(sys.argv[2])
OLD = '9d0f4b4c1e89b28d01de18092b5bf695de5bcde7'
NEW = '33cec5ba71d74820cb0acd3c89ecbe39ba125590'
OWNER = '6936a632ecc5cdbfd615b80c75312a09ed64b23a'
BASE = 'ba61baa2cd18ae9d13bc9733c1175b936512a786'
root = Path(__file__).resolve().parents[2]
repo = root.parents[2]
def read(pin, path, repository=API_REPO):
    return subprocess.check_output(['git', '-C', str(repository), 'show', f'{pin}:{path}'])
def digest(data): return hashlib.sha256(data).hexdigest()
old = json.loads(read(OLD, 'contracts/api/openapi.json'))
new = json.loads(read(NEW, 'contracts/api/openapi.json'))
assert all(new['paths'][key] == value for key, value in old['paths'].items())
assert all(new['components']['schemas'][key] == value for key, value in old['components']['schemas'].items())
unchanged = ['ios/Package.swift', 'ios/Package.resolved', 'ios/Sources/CJAPI/MemoryClientConfiguration.swift']
assert all(read(OLD, p) == read(NEW, p) for p in unchanged)
# Compare every previous top-level generated schema declaration, including nested enums/codec code.
schema_file = 'ios/Sources/CJAPI/Generated/Types+Components+Schemas.swift'
old_code = read(OLD, schema_file).decode()
new_code = read(NEW, schema_file).decode()
starts = list(re.finditer(r'^        (?:@frozen )?public (?:struct|enum|typealias) \w+', old_code, re.M))
for start in starts:
    opening = old_code.find('{', start.start())
    depth = 0
    for end in range(opening, len(old_code)):
        if old_code[end] == '{': depth += 1
        if old_code[end] == '}': depth -= 1
        if depth == 0: break
    assert old_code[start.start():end+1] in new_code
operations = [op['operationId'] for path in old['paths'].values() for op in path.values()
              if isinstance(op, dict) and 'operationId' in op]
checked_sdk = {}
for file, pattern in [('Client.swift', r'    public func %s\('),
                      ('Types+Operations.swift', r'    public enum %s \{'),
                      ('Types.swift', r'    public func %s\(')]:
    path = 'ios/Sources/CJAPI/Generated/' + file
    before = read(OLD, path).decode(); after = read(NEW, path).decode()
    for operation in operations:
        match = re.search(pattern % re.escape(operation), before)
        assert match is not None, (file, operation)
        opening = before.index('{', match.start()); depth = 0
        for end in range(opening, len(before)):
            if before[end] == '{': depth += 1
            if before[end] == '}': depth -= 1
            if depth == 0: break
        block = before[match.start():end+1]
        assert block in after, (file, operation)
        checked_sdk[file + ':' + operation] = digest(block.encode())
message = repo / 'ios/Modules/CJMessageClient'
manifest = json.loads((message / 'evidence/generated-pin.json').read_text())
assert manifest['commit'] == NEW
for path, sha in manifest['sha256'].items():
    data = (message / '.generated' / NEW / 'CJFoundation' / path.removeprefix('ios/')).read_bytes()
    assert data == read(NEW, path) and digest(data) == sha
for path in ['ios/Modules/CJMessageClient/Package.swift', 'ios/Modules/CJMessageClient/scripts/prepare_generated.py', 'ios/Modules/CJMessageClient/Sources/CJMessageHTTP/Transport.swift']:
    assert (repo / path).read_bytes() == read(OWNER, path, repo)
protected = ['ios/Modules/CJTripClient/Package.resolved']
protected += subprocess.check_output(['git', '-C', str(repo), 'ls-tree', '-r', '--name-only', BASE,
    'ios/Modules/CJTripClient/Sources', 'ios/Modules/CJTripClient/Tests'], text=True).splitlines()
for path in protected: assert (repo / path).read_bytes() == read(BASE, path, repo)
found = set()
def walk(node):
    if node['identity'] == 'cjfoundation': found.add(node['path'])
    for child in node.get('dependencies', []): walk(child)
walk(json.loads(GRAPH.read_text()))
expected = str(message / '.generated' / NEW / 'CJFoundation')
assert found == {expected}, found
old_export = message / '.generated' / OLD / 'CJFoundation'
assert old_export.is_dir()
result = {
    'product_source_base': BASE, 'shared_owner': OWNER, 'old_api': OLD, 'new_api': NEW,
    'old_paths_equal': len(old['paths']), 'old_schemas_equal': len(old['components']['schemas']),
    'old_generated_schema_declarations_exact': len(starts),
    'old_operation_count': len(operations), 'old_sdk_blocks_exact': checked_sdk,
    'manifest_lock_date_helper_identical': unchanged,
    'official_export_files_exact': len(manifest['sha256']),
    'single_cjfoundation_path': expected, 'old_export_preserved': True,
    'product_sources_tests_lock_unchanged': {path: digest((repo / path).read_bytes()) for path in protected},
    'new_package_sha256': digest((root / 'Package.swift').read_bytes()),
    'status': 'PASS; compatibility only, not business HOLD release'
}
print(json.dumps(result, indent=2))
