"""Explicit M4 iPhone-only build/TLS helpers. No automatic device/key discovery."""
from dataclasses import dataclass, field
import ipaddress
import json
import os
from pathlib import Path
import plistlib
import re
import socket
import ssl
import subprocess
import tempfile
import time
from m4_artifacts import verified_public_certificate

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class FrozenAMapKey:
    path: Path
    value: str = field(repr=False)


def freeze_amap_key(source, private_directory):
    source = Path(source)
    if source.is_symlink() or not source.is_file():
        raise ValueError('Regular authorized SDK key configuration required')
    try:
        fields = plistlib.loads(source.read_bytes())
    except Exception:
        raise ValueError('Invalid local SDK key resource') from None
    if not isinstance(fields, dict) or set(fields) != {'apiKey'}:
        raise ValueError('Invalid local SDK key fields')
    key = fields['apiKey']
    if not isinstance(key, str) or not key or any(ord(c)<32 or ord(c)>126 for c in key):
        raise ValueError('Invalid local SDK key value')
    directory = Path(tempfile.mkdtemp(prefix='m4-build-key-',dir=private_directory))
    directory.chmod(0o700)
    path = directory/'AMapLocalKey.plist'
    with path.open('xb') as output:
        output.write(plistlib.dumps({'apiKey':key},fmt=plistlib.FMT_BINARY))
    path.chmod(0o600)
    return FrozenAMapKey(path,key)


@dataclass(frozen=True)
class LocalTLS:
    host: str
    certificate: Path
    private_key: Path
    public_certificate: Path
    team: str
    public_der: bytes

    @classmethod
    def load(cls, path):
        path = Path(path).resolve()
        if path.is_relative_to(ROOT):
            raise ValueError('TLS operator profile must be outside repository')
        data = json.loads(path.read_text())
        if set(data) != {'version', 'host', 'team'} or data['version'] != 'G2C-M4-LOCAL-TLS.1':
            raise ValueError('Invalid local TLS operator profile')
        host = data['host']
        address = ipaddress.IPv4Address(host)
        networks = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16')
        if str(address) != host or not any(address in ipaddress.IPv4Network(n) for n in networks):
            raise ValueError('Explicit private IPv4 required')
        if re.fullmatch(r'[A-Z0-9]{10}', data['team']) is None:
            raise ValueError('Explicit developer team required')
        files = [path.parent / name for name in ('server.pem', 'server.key', 'G2CM4LocalServer.cer')]
        for file in files:
            if file.is_symlink() or not file.is_file() or file.stat().st_uid != os.getuid():
                raise ValueError('Owned regular TLS files required')
        if files[1].stat().st_mode & 0o777 != 0o600:
            raise ValueError('TLS private key must be 0600')
        public_der = verified_public_certificate(files[0].read_bytes(), files[2].read_bytes())
        return cls(host, *files, data['team'], public_der)

    def listener(self):
        listener = socket.socket()
        try:
            listener.bind((self.host, 0))
            listener.listen()
        except BaseException:
            listener.close()
            raise
        return listener

    def secure_http_server(self, server):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(self.certificate), str(self.private_key))
        server.socket = context.wrap_socket(server.socket, server_side=True)

    def uvicorn_options(self):
        return dict(ssl_certfile=str(self.certificate), ssl_keyfile=str(self.private_key),
                    ssl_version=ssl.PROTOCOL_TLS_SERVER, ssl_ciphers='ECDHE+AESGCM:ECDHE+CHACHA20')


def configure_project(project, tls, control_url, control_token, amap=False,
                      bundle=None, include_release=False):
    """Adapt the existing generated native project; real keys stay local-only."""
    project = Path(project)
    pbx = project / 'project.pbxproj'
    text = pbx.read_text()
    if bundle is None:
        bundle = 'space.go2china.app' if amap else 'space.go2china.scoped.acceptance'
    if amap and bundle != 'space.go2china.app':
        raise ValueError('AMap requires its authorized formal Bundle ID')
    if amap and include_release:
        raise ValueError('Local AMap device configuration is Debug only')
    text = text.replace('space.go2china.foundation.local', bundle).replace(
        'space.go2china.foundation.control', 'space.go2china.m4.device.control')
    text = text.replace('GENERATE_INFOPLIST_FILE = YES;',
        'GENERATE_INFOPLIST_FILE = YES; INFOPLIST_KEY_NSLocalNetworkUsageDescription = "M4 synthetic-data test control on the development Mac";')
    if not include_release:
        text = re.sub(r'buildConfigurations = \(000000000000000000000012[^)]*\)',
                      'buildConfigurations = (000000000000000000000012)', text)
        text = re.sub(r'buildConfigurations = \(000000000000000000000014[^)]*\)',
                      'buildConfigurations = (000000000000000000000014)', text)
    # The simulator entitlement is never reused as a device signing identity.
    text = re.sub(r'"CODE_SIGN_ENTITLEMENTS\[sdk=iphonesimulator\*\]"\s*=\s*[^;]+;', '', text)
    device_entitlements = project.parent/'M4Device.entitlements'
    device_entitlements.write_bytes(plistlib.dumps({
        'application-identifier':'$(AppIdentifierPrefix)$(PRODUCT_BUNDLE_IDENTIFIER)',
        'keychain-access-groups':['$(AppIdentifierPrefix)$(PRODUCT_BUNDLE_IDENTIFIER)']}))
    target_anchor='PRODUCT_BUNDLE_IDENTIFIER = '+bundle+';'
    if text.count(target_anchor) not in (2,3):
        raise ValueError('App identity configurations changed')
    text=text.replace(target_anchor,target_anchor+' CODE_SIGN_ENTITLEMENTS = '+json.dumps(str(device_entitlements))+';')
    entries = []
    resource_ids = []
    counter = 0

    def resource(path):
        nonlocal counter
        ref, build = f'D{counter:023X}', f'E{counter:023X}'
        counter += 1
        entries.extend([f'{ref} = {{isa = PBXFileReference; path = {json.dumps(str(path))}; sourceTree = "<absolute>"; }};',
                        f'{build} = {{isa = PBXBuildFile; fileRef = {ref}; }};'])
        return build

    pin_file = project.parent / 'G2CM4LocalServer.cer'
    with pin_file.open('xb') as output:
        output.write(tls.public_der)
    pin_file.chmod(0o600)
    resource_ids.append(resource(pin_file))
    local = ROOT / 'ios/.local-amap-device'
    frozen_key = None
    if amap:
        if not (local / 'AMapLocalKey.plist').is_file():
            raise ValueError('Prepare the authorized ignored AMap build first')
        frozen_key = freeze_amap_key(local/'AMapLocalKey.plist',local)
        resource_ids += [resource(next((local / 'sdk').rglob('AMap.bundle'))), resource(frozen_key.path)]
    app_anchor = '000000000000000000000120 = {isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = ('
    if text.count(app_anchor) != 1:
        raise ValueError('App resource phase changed')
    text = text.replace(app_anchor, app_anchor + ', '.join(resource_ids) + ', ')
    bootstrap = project.parent / 'M4ControlBootstrap.plist'
    with bootstrap.open('xb') as output:
        output.write(plistlib.dumps(dict(endpoint=control_url, token=control_token)))
    bootstrap.chmod(0o600)
    control_resources = [resource(pin_file), resource(bootstrap)]
    control_anchor = f'A{9:023X} = {{isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = ('
    if text.count(control_anchor) != 1:
        raise ValueError('Control resource phase changed')
    text = text.replace(control_anchor, control_anchor + ', '.join(control_resources))
    sources = []
    control_sources = [HERE / 'M4DeviceControl.swift', ROOT / 'ios/Modules/CJMessageClient/Sources/CJMessageHTTP/M4LocalServerTrust.swift']
    if include_release:
        control_sources.append(HERE / 'M4DeviceTestSession.swift')
    for source in control_sources:
        sources.append(resource(source))
    source_anchor = f'A{7:023X} = {{isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = ('
    if text.count(source_anchor) != 1:
        raise ValueError('Control source phase changed')
    text = text.replace(source_anchor, source_anchor + ', '.join(sources) + ', ')
    pbx.write_text(text.replace('};\nrootObject', '\n'.join(entries) + '\n};\nrootObject'))
    configuration = project.parent / 'M4Device.xcconfig'
    lines = ['OTHER_SWIFT_FLAGS = $(inherited) -D G2C_M4_DEVICE_ACCEPTANCE',
             'SWIFT_ACTIVE_COMPILATION_CONDITIONS = $(inherited) DEBUG',
             'DEBUG_INFORMATION_FORMAT = dwarf',
             'CODE_SIGNING_ALLOWED = YES', 'CODE_SIGN_STYLE = Automatic',
             'CODE_SIGN_IDENTITY = Apple Development', 'DEVELOPMENT_TEAM = ' + tls.team]
    if include_release:
        # Release product stays disconnected. Only its separate XCTest runner
        # needs the pinned control connection, not the product or its packages.
        lines[:2] = [
            'M4_DEVICE_FLAGS_Debug = -D DEBUG -D G2C_M4_DEVICE_ACCEPTANCE',
            'M4_CONTROL_FLAGS_G2CControl = -D DEBUG -D G2C_M4_DEVICE_ACCEPTANCE',
            'OTHER_SWIFT_FLAGS = $(inherited) $(M4_DEVICE_FLAGS_$(CONFIGURATION)) $(M4_CONTROL_FLAGS_$(TARGET_NAME))']
    if amap:
        # This include supplies only local SDK paths/flags; no key value.
        lines = ['#include ' + json.dumps(str(local / 'AMap.xcconfig'))] + lines
        lines[1] += ' -D G2C_AMAP_LOCAL'
        sdk_flags = '-ObjC -framework MAMapKit -framework AMapFoundationKit -framework GLKit -framework OpenGLES -framework CoreLocation -framework CoreTelephony -framework CoreMotion -framework SystemConfiguration -framework Security -framework CFNetwork -framework Metal -framework MetalKit -lc++ -lz'
        lines += ['M4_AMAP_LDFLAGS_CJProbeApp = '+sdk_flags,
                  'OTHER_LDFLAGS = $(inherited) $(M4_AMAP_LDFLAGS_$(TARGET_NAME))']
    configuration.write_text('\n'.join(lines) + '\n')
    return bundle, configuration, frozen_key


def scan_app_container(device, bundle, output, tokens):
    output = Path(output)
    result = subprocess.run(['xcrun', 'devicectl', 'device', 'copy', 'from', '--device', device,
        '--domain-type', 'appDataContainer', '--domain-identifier', bundle,
        '--source', '.', '--destination', str(output), '--timeout', '60'], capture_output=True)
    if result.returncode:
        raise RuntimeError('Device App-container scan unavailable; preserve result as FAIL')
    for file in output.rglob('*'):
        if file.is_file() and not file.is_symlink():
            data = file.read_bytes()
            if any(token.encode() in data for token in tokens) or b'-----BEGIN PRIVATE KEY-----' in data:
                raise AssertionError('Credential/private key found in device App data')


def stage_accounts(device, bundle, app, private_directory, tokens):
    """One-use operator input; never put JWTs into XCTest launch/activity metadata."""
    result=subprocess.run(['xcrun','devicectl','device','install','app','--device',device,str(app),
        '--timeout','60'],capture_output=True)
    if result.returncode:raise RuntimeError('Approved device App install failed')
    copy_accounts(device,bundle,private_directory,tokens)


def copy_accounts(device, bundle, private_directory, tokens):
    """Stage a fresh one-use input for a relaunch, without reinstalling the App."""
    with tempfile.TemporaryDirectory(prefix='operator-input-',dir=private_directory) as temporary:
        source=Path(temporary)/'G2CM4DeviceAccounts.json'
        with source.open('x') as output:json.dump(tokens,output)
        source.chmod(0o600)
        result=subprocess.run(['xcrun','devicectl','device','copy','to','--device',device,
            '--domain-type','appDataContainer','--domain-identifier',bundle,'--source',str(source),
            '--destination','Library/Caches/G2CM4DeviceAccounts.json','--timeout','30'],capture_output=True)
        if result.returncode:raise RuntimeError('Device one-use credential staging failed')


def discard_staged_accounts(device,bundle):
    def present():
        result=subprocess.run(['xcrun','devicectl','device','info','files','--device',device,
            '--domain-type','appDataContainer','--domain-identifier',bundle,'--subdirectory','Library/Caches',
            '--no-recurse','--json-output','-','--quiet','--timeout','20'],capture_output=True)
        if result.returncode:raise RuntimeError('Device staged-input cleanup state UNKNOWN')
        data=json.loads(result.stdout)['result']['files']
        return any(item['name']=='G2CM4DeviceAccounts.json' for item in data)
    if not present():return
    # This App-owned one-use input is the only cleanup target, never a business
    # journal or Keychain item. The App rejects symlinks and verifies removal.
    result=subprocess.run(['xcrun','devicectl','device','process','launch','--device',device,
        '--terminate-existing','--environment-variables',json.dumps({
            'OS_ACTIVITY_MODE':'disable','G2C_M4_DISCARD_ACCOUNTS_FILE':'1'}),'--timeout','20',bundle],capture_output=True)
    if result.returncode:raise RuntimeError('Staged device credential cleanup pending; device unlock required')
    deadline=time.monotonic()+5
    while present():
        if time.monotonic()>deadline:raise RuntimeError('Device staged credential remains; do not record PASS')
        time.sleep(0.2)
