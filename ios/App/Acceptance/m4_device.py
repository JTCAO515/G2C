"""Explicit M4 iPhone-only build/TLS helpers. No automatic device/key discovery."""
from dataclasses import dataclass
import ipaddress
import json
import os
from pathlib import Path
import plistlib
import re
import socket
import ssl
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class LocalTLS:
    host: str
    certificate: Path
    private_key: Path
    public_certificate: Path
    team: str

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
        return cls(host, *files, data['team'])

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


def configure_project(project, tls, control_url, control_token, amap=False):
    """Adapt the existing generated native project; real keys stay local-only."""
    project = Path(project)
    pbx = project / 'project.pbxproj'
    text = pbx.read_text()
    bundle = 'space.go2china.app' if amap else 'space.go2china.scoped.acceptance'
    text = text.replace('space.go2china.foundation.local', bundle).replace(
        'space.go2china.foundation.control', 'space.go2china.m4.device.control')
    text = text.replace('GENERATE_INFOPLIST_FILE = YES;',
        'GENERATE_INFOPLIST_FILE = YES; INFOPLIST_KEY_NSLocalNetworkUsageDescription = "M4 synthetic-data test control on the development Mac";')
    text = re.sub(r'buildConfigurations = \(000000000000000000000012[^)]*\)',
                  'buildConfigurations = (000000000000000000000012)', text)
    text = re.sub(r'buildConfigurations = \(000000000000000000000014[^)]*\)',
                  'buildConfigurations = (000000000000000000000014)', text)
    # The simulator entitlement is never reused as a device signing identity.
    text = re.sub(r'"CODE_SIGN_ENTITLEMENTS\[sdk=iphonesimulator\*\]"\s*=\s*[^;]+;', '', text)
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

    resource_ids.append(resource(tls.public_certificate))
    local = ROOT / 'ios/.local-amap-device'
    if amap:
        if not (local / 'AMapLocalKey.plist').is_file():
            raise ValueError('Prepare the authorized ignored AMap build first')
        resource_ids += [resource(next((local / 'sdk').rglob('AMap.bundle'))), resource(local / 'AMapLocalKey.plist')]
    app_anchor = '000000000000000000000120 = {isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = ('
    if text.count(app_anchor) != 1:
        raise ValueError('App resource phase changed')
    text = text.replace(app_anchor, app_anchor + ', '.join(resource_ids) + ', ')
    bootstrap = project.parent / 'M4ControlBootstrap.plist'
    with bootstrap.open('xb') as output:
        output.write(plistlib.dumps(dict(endpoint=control_url, token=control_token)))
    bootstrap.chmod(0o600)
    control_resources = [resource(tls.public_certificate), resource(bootstrap)]
    control_anchor = f'A{9:023X} = {{isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = ('
    if text.count(control_anchor) != 1:
        raise ValueError('Control resource phase changed')
    text = text.replace(control_anchor, control_anchor + ', '.join(control_resources))
    sources = []
    for source in [HERE / 'M4DeviceControl.swift', ROOT / 'ios/Modules/CJMessageClient/Sources/CJMessageHTTP/M4LocalServerTrust.swift']:
        sources.append(resource(source))
    source_anchor = f'A{7:023X} = {{isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = ('
    if text.count(source_anchor) != 1:
        raise ValueError('Control source phase changed')
    text = text.replace(source_anchor, source_anchor + ', '.join(sources) + ', ')
    pbx.write_text(text.replace('};\nrootObject', '\n'.join(entries) + '\n};\nrootObject'))
    configuration = project.parent / 'M4Device.xcconfig'
    lines = ['OTHER_SWIFT_FLAGS = $(inherited) -D G2C_M4_DEVICE_ACCEPTANCE',
             'SWIFT_ACTIVE_COMPILATION_CONDITIONS = $(inherited) DEBUG',
             'CODE_SIGNING_ALLOWED = YES', 'CODE_SIGN_STYLE = Automatic',
             'CODE_SIGN_IDENTITY = Apple Development', 'DEVELOPMENT_TEAM = ' + tls.team]
    if amap:
        # This include supplies only local SDK paths/flags; no key value.
        lines = ['#include ' + json.dumps(str(local / 'AMap.xcconfig'))] + lines
        lines[1] += ' -D G2C_AMAP_LOCAL'
    configuration.write_text('\n'.join(lines) + '\n')
    return bundle, configuration


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
