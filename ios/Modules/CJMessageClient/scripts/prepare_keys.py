"""Compile-only manifest around an exact official interface blob, no rewritten types."""
from pathlib import Path
import hashlib,json,subprocess,sys
PIN='f1ce075e4b3f26e6c65bfe4b2fa8bcec8291a552'
source='ios/Modules/CJAuth/Sources/CJMessageKeys/MessageKeyInterfaces.swift'
root=Path(__file__).resolve().parents[1]
data=subprocess.check_output(['git','-C',sys.argv[1],'show',PIN+':'+source])
out=root/'.generated/CJMessageKeysInterface'
file=out/'Sources/CJMessageKeys/MessageKeyInterfaces.swift'
file.parent.mkdir(parents=True,exist_ok=True)
if file.exists() and file.read_bytes()!=data: raise SystemExit('different interface export exists')
file.write_bytes(data)
(out/'Package.swift').write_text('''// swift-tools-version: 6.1
// Local compilation harness only; interface source is exact CJ007 fixed git blob.
import PackageDescription
let package = Package(name: "CJMessageKeysInterface", platforms: [.iOS(.v17), .macOS(.v14)],
 products: [.library(name: "CJMessageKeys", targets: ["CJMessageKeys"])],
 targets: [.target(name: "CJMessageKeys")])
''')
(root/'evidence/key-interface-pin.json').write_text(json.dumps({'commit':PIN,'source':source,'sha256':hashlib.sha256(data).hexdigest()},indent=2)+'\n')
