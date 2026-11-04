"""Prepare an ignored, Debug-only iPhone SDK project. No signing or device action.

The optional --inject-key reads only M4 item 1's Keychain item. It is never a
build setting, command argument or environment variable. Default is no key.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[3]
PINS = {'map-11.3.100.zip':'231fedcd79532932864a9b39717164cb6a3267bf53dc5d755bf9894ebba04af7',
        'foundation-noidfa-1.9.4.zip':'e812db2c83e2542e8bcd1d6904e03d49fa1a2e20b33772e1c3f1ede14d5dd552'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk-cache', type=Path, required=True)
    p.add_argument('--inject-key', action='store_true')
    args = p.parse_args()
    os.umask(0o077)
    local = ROOT/'ios/.local-amap-device'
    subprocess.run(['git','check-ignore','-q',str(local)+'/'],cwd=ROOT,check=True)
    local.mkdir(mode=0o700,exist_ok=True)
    sdk = local/'sdk'
    if sdk.exists():
        raise ValueError('Preserve prior local build; move the ignored directory before preparing again')
    for name,digest in PINS.items():
        archive=args.sdk_cache/name
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=digest:
            raise ValueError('Official SDK archive pin mismatch: '+name)
        destination=sdk/('map' if name.startswith('map-') else 'foundation')
        destination.mkdir(parents=True)
        with zipfile.ZipFile(archive) as z:
            # Only regular SDK resources under the destination are extracted.
            for item in z.infolist():
                target=(destination/item.filename).resolve()
                if not target.is_relative_to(destination.resolve()):raise ValueError('SDK archive path escapes local directory')
            z.extractall(destination)
    frameworks={name:next(sdk.rglob(name+'.framework')) for name in ['MAMapKit','AMapFoundationKit']}
    for name,framework in frameworks.items():
        module=framework/'Modules/module.modulemap'
        if not module.exists():
            module.parent.mkdir(exist_ok=True)
            module.write_text('framework module '+name+' { umbrella header "'+name+'.h" export * module * { export * } }\n')
    key_file=local/'AMapLocalKey.plist'
    if args.inject_key:
        result=subprocess.run(['security','find-generic-password','-s','g2c-amap-ios-key','-w'],capture_output=True)
        if result.returncode:raise RuntimeError('Authorized AMap Keychain item unavailable')
        try:
            key=result.stdout.decode().strip()
        except UnicodeError:
            raise ValueError('Invalid local AMap key encoding') from None
        if not key or any(ord(c)<32 for c in key):raise ValueError('Invalid local AMap key configuration')
        key_file.write_bytes(plistlib.dumps({'apiKey':key}));key_file.chmod(0o600)
    elif key_file.exists():
        raise ValueError('Refuse to reuse a previous key without explicit --inject-key')

    project=local/'AMapLocal.xcodeproj';project.mkdir()
    quote=lambda x:json.dumps(str(x))
    text=(ROOT/'ios/CJProbeApp.xcodeproj/project.pbxproj').read_text()
    text=re.sub(r'path = (App/[^;]+);',lambda m:'path = '+quote(ROOT/'ios'/m[1])+';',text)
    text=re.sub(r'path = "(Branding/[^"]+)";',lambda m:'path = '+quote(ROOT/'ios'/m[1])+';',text)
    text=text.replace('relativePath = Modules/CJShell;','relativePath = '+quote(ROOT/'ios/Modules/CJShell')+';')
    text=text.replace('INFOPLIST_FILE = App/Info.plist;','INFOPLIST_FILE = '+quote(ROOT/'ios/App/Info.plist')+';')
    text=text.replace('"CODE_SIGN_ENTITLEMENTS[sdk=iphonesimulator*]" = App/Development.entitlements;',
                      '"CODE_SIGN_ENTITLEMENTS[sdk=iphonesimulator*]" = '+quote(ROOT/'ios/App/Development.entitlements')+';')
    text=text.replace('PRODUCT_BUNDLE_IDENTIFIER = space.go2china.foundation.local;','PRODUCT_BUNDLE_IDENTIFIER = space.go2china.app;')
    # A key/resource-bearing local project offers Debug only.
    text=re.sub(r'buildConfigurations = \(000000000000000000000012[^)]*\)', 'buildConfigurations = (000000000000000000000012)',text)
    text=re.sub(r'buildConfigurations = \(000000000000000000000014[^)]*\)', 'buildConfigurations = (000000000000000000000014)',text)
    entries=[];build_ids=[]
    resources=[frameworks['MAMapKit']/'AMap.bundle']+([key_file] if args.inject_key else [])
    for i,path in enumerate(resources):
        ref=f'B{i:023X}';build=f'C{i:023X}'
        entries.extend([f'{ref} = {{isa = PBXFileReference; path = {quote(path)}; sourceTree = "<absolute>"; }};',
                        f'{build} = {{isa = PBXBuildFile; fileRef = {ref}; }};'])
        build_ids.append(build)
    anchor='000000000000000000000120 = {isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = ('
    if text.count(anchor)!=1:raise ValueError('App resource phase changed')
    text=text.replace(anchor,anchor+', '.join(build_ids)+', ')
    (project/'project.pbxproj').write_text(text.replace('};\nrootObject','\n'.join(entries)+'\n};\nrootObject'))
    schemes=project/'xcshareddata/xcschemes';schemes.mkdir(parents=True)
    scheme=(ROOT/'ios/CJProbeApp.xcodeproj/xcshareddata/xcschemes/CJProbeApp.xcscheme').read_text().replace('container:CJProbeApp.xcodeproj','container:AMapLocal.xcodeproj')
    (schemes/'AMapLocal.xcscheme').write_text(scheme)
    lock=project/'project.xcworkspace/xcshareddata/swiftpm/Package.resolved';lock.parent.mkdir(parents=True)
    lock.write_bytes((ROOT/'ios/CJProbeApp.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved').read_bytes())
    config=local/'AMap.xcconfig'
    search=' '.join('"'+str(f.parent)+'"' for f in frameworks.values())
    config.write_text('\n'.join(['OTHER_SWIFT_FLAGS = $(inherited) -D G2C_M4_DEVICE_ACCEPTANCE -D G2C_AMAP_LOCAL',
        'FRAMEWORK_SEARCH_PATHS = $(inherited) '+search,
        'OTHER_LDFLAGS = $(inherited) -ObjC -framework MAMapKit -framework AMapFoundationKit -framework GLKit -framework OpenGLES -framework CoreLocation -framework CoreTelephony -framework CoreMotion -framework SystemConfiguration -framework Security -framework CFNetwork -framework Metal -framework MetalKit -lc++ -lz',
        'CODE_SIGNING_ALLOWED = NO','']))
    print('Prepared ignored Debug-only project; signing/device execution not performed; key injected: '+str(args.inject_key))


if __name__=='__main__':main()
