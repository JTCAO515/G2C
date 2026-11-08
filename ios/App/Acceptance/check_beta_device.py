"""#498: prepare, then execute one existing-record beta device scenario.

No model/message/delete call is made by this harness. The App uses system TLS
for the exact beta origin; only its separate XCTest control uses local pinning.
Tokens are requested from B after preparation and enter the App via one-use
Caches input, never XCTest environment or generated source.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import secrets
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from m4_device import LocalTLS, ROOT, configure_project
from m4_native import DeviceNative, authenticated_control

BUNDLE='space.go2china.beta.acceptance'
CASE='beta-readonly-05'
TEST='DevelopmentBetaUITests/testExistingAnswerRestoreAndOwnerIsolation'
ENGLISH_DIAGNOSTIC='DevelopmentBetaUITests/testOriginalEnglishDiagnostic'
CHINESE_RECOVERY='DevelopmentBetaUITests/testChineseRecoveryAndOwnerIsolation'
SCENARIOS={
    'full':(CASE,TEST),
    'english-diagnostic':(CASE,ENGLISH_DIAGNOSTIC),
    'chinese-recovery':(CASE,CHINESE_RECOVERY),
    'general-feedback-recovery':('beta-general-feedback-recovery','DevelopmentBetaUITests/testGeneralFeedbackOriginalRecoveryOnly'),
}


def product_hashes(build):
    products=build/'Build/Products'
    return {str(p.relative_to(products)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in products.rglob('*') if p.is_file() and not p.is_symlink()}


def project_hashes(work):
    paths=[work/'G2CControl.swift',work/'M4Device.xcconfig',work/'M4ControlBootstrap.plist',
           *list((work/'G2CAcceptance.xcodeproj').rglob('*'))]
    return {str(path.relative_to(work)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths if path.is_file() and not path.is_symlink()}


def operator_accounts(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_uid!=os.getuid() or path.stat().st_mode&0o777!=0o600:
        raise ValueError('Owned regular 0600 one-use B account input required')
    if path.stat().st_size>131072:raise ValueError('Account input exceeds the existing boundary')
    value=json.loads(path.read_bytes())
    if not isinstance(value,dict) or set(value)!={'A','B'} or not all(isinstance(v,str) and v and len(v.encode())<=16384 and all(32<ord(c)<127 for c in v) for v in value.values()):
        raise ValueError('Exact A/B account map required; API remains signature authority')
    return value


def feedback_original(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_uid!=os.getuid() or path.stat().st_mode&0o777!=0o600:
        raise ValueError('Owned regular 0600 synthetic Feedback evidence required')
    if path.stat().st_size > 1024:
        raise ValueError('Feedback evidence exceeds the input boundary')
    raw = path.read_bytes()
    value = json.loads(raw)
    if (not isinstance(value, dict) or set(value) != {'action_id', 'problem_sha256'}
            or not all(isinstance(item, str) for item in value.values())
            or not re.fullmatch(r'[A-F0-9]{8}(?:-[A-F0-9]{4}){3}-[A-F0-9]{12}', value['action_id'])
            or not re.fullmatch(r'[a-f0-9]{64}', value['problem_sha256'])):
        raise ValueError('Exact original Feedback action and SHA-256 required')
    return value, hashlib.sha256(raw).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device',required=True);p.add_argument('--output',required=True,type=Path)
    modes=p.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare-only',action='store_true');modes.add_argument('--prepared',type=Path)
    p.add_argument('--local-tls',type=Path);p.add_argument('--build-dir',type=Path);p.add_argument('--work-dir',type=Path)
    p.add_argument('--accounts-file',type=Path)
    p.add_argument('--feedback-original',type=Path,help='Synthetic original action and problem SHA-256; recovery preparation only')
    p.add_argument('--case',choices=SCENARIOS)
    a=p.parse_args();os.umask(0o077)
    if bool(a.feedback_original) != (a.prepare_only and a.case=='general-feedback-recovery'):
        p.error('--feedback-original is required only when preparing general-feedback-recovery')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('Commit candidate before preparing or executing')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    output=a.output.resolve()
    if output.is_relative_to(ROOT):raise ValueError('External evidence output required')
    output.mkdir(mode=0o700)
    case_id,selected=SCENARIOS[a.case or 'full']
    report=dict(status='RUNNING',head=head,layer='authorized physical iPhone / actual beta service; synthetic existing records',
        cases={selected:'UNRUN'},raw_native_bundle_shareable=False,build_inputs_shareable=False,
        unrun=['new messages/providers','Needs/Trip/typed Memory/cleanup cloud profiles','target-network quality','TestFlight'])
    def save():(output/'report.json').write_text(json.dumps(report,indent=2))
    save();native=None;server=None;thread=None;accounts={};native_run_incomplete=False
    try:
        if a.prepare_only:
            if not all([a.local_tls,a.build_dir,a.work_dir]) or a.accounts_file:p.error('Preparation needs local TLS/build/work paths, with no account input')
            tls=LocalTLS.load(a.local_tls)
            work=a.work_dir.resolve();build=a.build_dir.resolve()
            for path in (work,build):
                if path.is_relative_to(ROOT) or path.is_relative_to(output) or output.is_relative_to(path):raise ValueError('Private build/work must be separate from exports/repository')
            work.mkdir(mode=0o700)
            spec=importlib.util.spec_from_file_location('beta_builder',ROOT/'scripts/check_ios_trip_confirm.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            builder=object.__new__(module.XCTestDriver);builder.directory=work;builder.write_project(0)
            source=(ROOT/'ios/App/Acceptance/DevelopmentBetaUITests.swift').read_text()
            original_provenance = None
            if a.feedback_original:
                original, original_provenance = feedback_original(a.feedback_original)
                source = source.replace('__FEEDBACK_ORIGINAL_ID__', original['action_id'])
                source = source.replace('__FEEDBACK_ORIGINAL_PROBLEM_SHA__', original['problem_sha256'])
            control_token=secrets.token_urlsafe(32)
            server=ThreadingHTTPServer((tls.host,0),BaseHTTPRequestHandler)
            endpoint='https://'+tls.host+':'+str(server.server_port)
            (work/'G2CControl.swift').write_text(source.replace('__FIXTURE_URL__',endpoint))
            project=work/'G2CAcceptance.xcodeproj'
            _,config,_=configure_project(project,tls,endpoint,control_token,bundle=BUNDLE,app_local_tls=False)
            meta=dict(head=head,device=a.device,test=selected,work=str(work),build=str(build),tls=str(a.local_tls.resolve()),
                endpoint=endpoint,certificate_sha256=hashlib.sha256(tls.public_der).hexdigest())
            if original_provenance:
                meta['feedback_original_sha256'] = original_provenance
        else:
            if not a.accounts_file or a.local_tls or a.build_dir or a.work_dir:p.error('Execution needs --prepared private metadata and --accounts-file only')
            meta=json.loads(a.prepared.read_text());work=Path(meta['work']);build=Path(meta['build'])
            if meta['head']!=head or meta['device']!=a.device:raise ValueError('Prepared head/device differs')
            if a.case is not None and meta['test']!=selected:raise ValueError('Prepared selected method differs')
            selected=meta['test'];report['cases']={selected:'UNRUN'}
            allowed={test:case for case,test in SCENARIOS.values()}
            if selected not in allowed:raise ValueError('Unknown prepared beta scenario')
            case_id=allowed[selected]
            if case_id!=CASE:
                if a.case is None:p.error('Feedback recovery requires the explicit prepared --case')
                provenance=meta.get('feedback_original_sha256')
                if not isinstance(provenance,str) or not re.fullmatch(r'[a-f0-9]{64}',provenance):
                    p.error('Prepared original Feedback evidence is missing')
            if product_hashes(build)!=meta['products']:raise ValueError('Prepared signed products changed')
            if project_hashes(work)!=meta['project_inputs']:raise ValueError('Prepared project/control inputs changed')
            tls=LocalTLS.load(Path(meta['tls']))
            if hashlib.sha256(tls.public_der).hexdigest()!=meta['certificate_sha256']:raise ValueError('Prepared control pin changed')
            bootstrap=plistlib.loads((work/'M4ControlBootstrap.plist').read_bytes())
            if bootstrap['endpoint']!=meta['endpoint']:raise ValueError('Prepared control origin changed')
            control_token=bootstrap['token'];project=work/'G2CAcceptance.xcodeproj';config=work/'M4Device.xcconfig'
            accounts=operator_accounts(a.accounts_file)
        report['scenario']=case_id
        report['app_write_scope']='none: existing-record reads only'
        native=DeviceNative(a.device,BUNDLE,project,config,build,ROOT,output,accounts,control_token,report,case_id=case_id)
        env={k:v for k,v in os.environ.items() if not k.startswith(('G2C_DEV_','G2C_M4_','SIMCTL_CHILD_','PG','LIBPQ','CJ_LOCAL_'))}
        env['OS_ACTIVITY_MODE']='disable'
        if a.prepare_only:
            native.build_for_testing('Debug',[selected],env)
            app=build/'Build/Products/Debug-iphoneos/CJProbeApp.app'
            if (app/'G2CM4LocalServer.cer').exists() or plistlib.loads((app/'Info.plist').read_bytes()).get('NSAppTransportSecurity'):
                raise ValueError('Public beta App must not contain local TLS/ATS configuration')
            meta.update(products=product_hashes(build),project_inputs=project_hashes(work))
            (work/'prepared.json').write_text(json.dumps(meta,indent=2))
            report.update(status='PREPARED_EXECUTION_UNRUN',system_tls_product_boundary='PASS')
        else:
            class Control(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):self.send_error(404)
            handler=authenticated_control(Control,control_token,lambda _:native.stage(case_id),lambda:case_id)
            origin=urlsplit(meta['endpoint'])
            if origin.scheme!='https' or origin.hostname!=tls.host or not origin.port:raise ValueError('Invalid prepared control origin')
            server=ThreadingHTTPServer((tls.host,origin.port),handler);tls.secure_http_server(server)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            native_run_incomplete=True
            native.run('Debug',[selected],env)
            native_run_incomplete=False
            native.scan('Debug')
            report.update(status='PARTIAL_PASS',cases={selected:'PASS'},token_key_scan='PASS',
                provider_accounting='UNKNOWN: read-only UI scenario; server accounting requires separate evidence',
                operator_account_file_cleanup='Mac handoff source remains owner-managed; App one-use input checked separately')
        if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=head:raise ValueError('Candidate changed during acceptance')
    except BaseException as error:
        report.update(status='FAIL',error_type=type(error).__name__);raise
    finally:
        if server:
            if thread:server.shutdown();thread.join()
            server.server_close()
        if native:
            if native_run_incomplete and report['status']=='FAIL':
                report['failure_container_scan']={'status':'UNRUN','reason':'pending exact input cleanup and device access'}
            try:native.cleanup_input()
            except BaseException:report.update(status='FAIL',cleanup='FAIL: exact input cleanup pending');save();raise
            if native_run_incomplete and report['status']=='FAIL':
                try:
                    native.scan('Debug')
                    report['failure_container_scan']={'status':'PASS'}
                except Exception as scan_error:
                    # Preserve the original native failure. A scan rejection is
                    # separate from an unavailable/uncompleted device scan.
                    report['failure_container_scan']={'status':'FAIL' if isinstance(scan_error,AssertionError) else 'UNRUN',
                        'error_type':type(scan_error).__name__}
        save()


if __name__=='__main__':main()
