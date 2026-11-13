"""Actual Beta workflow/Keychain with a local HTTP fixture; no real service."""
import argparse,base64,hashlib,importlib.util,json,os,plistlib,subprocess,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
BUNDLE='space.go2china.b691.acceptance'
SCENARIOS=['ready','registrationUnknown','enrolled','preparedUnregister','preparationUnknown','foreignOwner','confirmationDispatched','verifiedRefusal']
TRACE='69169169-1691-4691-8691-691691691691'

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--root-lifecycle',action='store_true')
 p.add_argument('--refusal',choices=['no-marker','wrong-bundle'])
 p.add_argument('--build-dir',type=Path,required=True);p.add_argument('--simulator');p.add_argument('--port',type=int,default=0)
 modes=p.add_mutually_exclusive_group();modes.add_argument('--prepare-only',action='store_true');modes.add_argument('--serve-only',action='store_true');a=p.parse_args()
 global BUNDLE
 if a.root_lifecycle and a.refusal!='wrong-bundle':BUNDLE='space.go2china.app'
 output=a.output.resolve();build=a.build_dir.resolve()
 if output.is_relative_to(ROOT)or build.is_relative_to(ROOT):p.error('keep generated project/build/evidence outside repository')
 output.mkdir(parents=True,exist_ok=False);os.chmod(output,0o700)
 report={'status':'UNRUN','layer':'actual Beta coordinator/Keychain/native clients/local HTTP fixture','real_server':'UNRUN','natural_seven_day_elapsed':'UNRUN','results':{},'root_results':{},'requests':[],'source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()for f in (Path(__file__),HERE/'DemoCleanupRenewalFixture.swift',HERE/'DemoCleanupRenewalUITests.swift',ROOT/'ios/App/DevelopmentTripHost.swift',ROOT/'ios/App/DevelopmentSessionConfiguration.swift',ROOT/'ios/App/DemoBetaConfiguration.swift',ROOT/'ios/Modules/CJMessageClient/Sources/CJMessageHTTP/Transport.swift')}}
 def save():
  path=output/'report.json';path.write_text(json.dumps(report,indent=2));path.chmod(0o600)
 save()
 class Server(BaseHTTPRequestHandler):
  def log_message(self,*unused):pass
  def send(self,status,value):
   raw=json.dumps({'request_id':TRACE,**value},separators=(',',':')).encode();self.send_response(status)
   for k,v in [('Content-Type','application/json'),('X-Request-ID',TRACE),('Cache-Control','no-store'),('Content-Length',str(len(raw)))]:self.send_header(k,v)
   self.end_headers();self.wfile.write(raw)
  def authorization(self):
   auth=self.headers.get('Authorization','')
   if not auth.startswith('Bearer b691fixture.'):return auth
   token=auth.removeprefix('Bearer ');payload=token.split('.')[1]
   try:claims=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
   except (ValueError,KeyError):return ''
   if claims.get('b691_scenario')not in SCENARIOS or not claims.get('sub','').startswith('m4-synthetic-demo-'):return ''
   return 'Bearer SDK.SYNTHETIC.B691.'+claims['b691_scenario']+('.renewed'if claims['b691_renewed']else '')
  def do_GET(self):
   path=urlsplit(self.path).path;query=parse_qs(urlsplit(self.path).query);auth=self.authorization()
   if path=='/v1/message-receipts'and query.get('message_id',[''])[0].startswith('session-'):
    report['requests'].append({'method':'GET','path':path,'scenario':auth.removeprefix('Bearer SDK.SYNTHETIC.B691.'),'root_verification':True});save();self.send(200,{'receipt':None});return
   if path=='/v1/message-receipts' and auth=='Bearer SDK.SYNTHETIC.B691.verifiedRefusal':
    report['requests'].append({'method':'GET','path':path,'scenario':'verifiedRefusal'});save()
    self.send(403,{'error':{'code':'ACCESS_DENIED','category':'access','message_en':'Unavailable','message_zh':'不可用','outcome':'failed','recovery':'do_not_retry'}});return
   if path=='/v1/account-cleanup-operations/operation-b691-preparedUnregister':
    if auth!='Cleanup PROGRESS.SYNTHETIC.B691.preparedUnregister':self.send_error(403);return
    report['requests'].append({'method':'GET','path':path,'scenario':'preparedUnregister','credential_kind':'original_progress','query':query});save()
    self.send(200,{'version':'CLEANUP-API@1','operation_id':'operation-b691-preparedUnregister','phase':'prepared','status':'awaiting_confirmation','revision':0,'steps':[]});return
   prefix='Bearer SDK.SYNTHETIC.B691.'
   if not auth.startswith(prefix) or not auth.endswith('.renewed'):self.send_error(403);return
   scenario=auth[len(prefix):-len('.renewed')]
   if scenario not in ('registrationUnknown','enrolled','preparationUnknown'):self.send_error(403);return
   report['requests'].append({'method':'GET','path':path,'scenario':scenario,'credential_kind':'renewed_sdk','query':query});save()
   if path=='/v4/cleanup-device-registrations' and set(query)=={'action_id','input_sha256'}:
    registration=None
    if scenario=='enrolled':
     original=next(row['body']for row in report['requests']if row['method']=='POST'and row['path']=='/v4/cleanup-devices'and row['scenario']==scenario)
     if query['action_id']!=[original['action_id']]:self.send_error(409);return
     registration={'version':'CLEANUP-DEVICE@4','binding_id':'binding-b691-'+scenario,'device_id':original['device_id'],'state_ref':original['state_ref'],'scope_digest':'a'*64,'device_token':'DEVICE.SYNTHETIC.B691.'+scenario,'server_time':1000,'business_access':'not_granted'}
    self.send(200,{'version':'CLEANUP-DEVICE@4','action_id':query['action_id'][0],'input_sha256':query['input_sha256'][0],'registration':registration});return
   if path=='/v1/account-cleanup-preparations' and set(query)=={'action_id'}:
    self.send(200,{'version':'CLEANUP-API@1','preparation':None});return
   self.send_error(404)
  def do_POST(self):
   transfer=self.headers.get('Transfer-Encoding','').lower()
   if transfer=='chunked' and 'Content-Length'not in self.headers:
    chunks=[];total=0
    while True:
     line=self.rfile.readline(128)
     if not line.endswith(b'\r\n'):self.send_error(400);return
     length=int(line.strip(),16)
     if length==0:
      if self.rfile.read(2)!=b'\r\n':self.send_error(400);return
      break
     total+=length
     if total>16384:self.send_error(413);return
     chunk=self.rfile.read(length)
     if len(chunk)!=length or self.rfile.read(2)!=b'\r\n':self.send_error(400);return
     chunks.append(chunk)
    raw=b''.join(chunks)
   elif not transfer:
    length=int(self.headers.get('Content-Length','0'))
    if not 0<length<=16384:self.send_error(400);return
    raw=self.rfile.read(length)
   else:self.send_error(400);return
   body=json.loads(raw);path=urlsplit(self.path).path
   if path=='/fixture-admission-result':
    if body!={'mode':a.refusal,'result':'DENIED'}:self.send_error(400);return
    report['fixture_admission']=body;report['status']='PASS';save();self.send(200,{'accepted':True});return
   if path=='/root-probe-result':
    scenario=body.get('scenario')
    if scenario not in SCENARIOS:self.send_error(400);return
    report['root_results'][scenario]=body;report['status']='PASS'if len(report['root_results'])==6 else 'RUNNING';save();self.send(200,{'accepted':True});return
   if path=='/probe-result':
    scenario=body['scenario']
    if scenario not in SCENARIOS or scenario in report['results']:self.send_error(409);return
    expected=scenario not in ('foreignOwner','confirmationDispatched','verifiedRefusal')
    expected_base={'scenario':scenario,'renewalAccepted':expected,'originalStateRefUnchanged':True,'originalControlsUnchanged':True,'manifestChangeIsOnlyRenewedSDKHash':True}
    if any(body.get(k)!=v for k,v in expected_base.items()):self.send_error(400);return
    recovered=scenario in ('registrationUnknown','enrolled','preparedUnregister','preparationUnknown')
    status='PASS'if recovered else 'NOT_APPLICABLE_NO_ORIGINAL'if scenario=='ready'else 'UNRUN_DENIED'
    if body.get('recoveryStatus')!=status:self.send_error(400);return
    if recovered:
     observed=[row for row in report['requests']if row['method']=='GET'and row['scenario']==scenario]
     if len(observed)!=1:self.send_error(400);return
     query=observed[0]['query']
     if scenario!='preparedUnregister'and query.get('action_id')!=[body['recoveryOriginalActionID']]:self.send_error(409);return
     if scenario in ('registrationUnknown','enrolled')and query.get('input_sha256')!=[body['recoveryOriginalRequestSha256']]:self.send_error(409);return
    report['results'][scenario]=body;report['status']='PASS'if len(report['results'])==8 else 'RUNNING';save();self.send(200,{'accepted':True});return
   auth=self.authorization()
   prefix='Bearer SDK.SYNTHETIC.B691.'
   if not auth.startswith(prefix):self.send_error(403);return
   scenario=auth[len(prefix):]
   if scenario not in SCENARIOS:self.send_error(403);return
   report['requests'].append({'method':'POST','path':path,'scenario':scenario,'body':body});save()
   if path=='/v4/cleanup-devices':
    self.send(200,{'version':'CLEANUP-DEVICE@4','binding_id':'binding-b691-'+scenario,'device_id':body['device_id'],'state_ref':body['state_ref'],'scope_digest':'a'*64,'device_token':'DEVICE.SYNTHETIC.B691.'+scenario,'server_time':1000,'business_access':'not_granted'})
   elif path=='/v1/account-cleanup-operations':
    self.send(200,{'version':'CLEANUP-API@1','operation_id':'operation-b691-'+scenario,'phase':'prepared','registry_digest':'b'*64,'plan_digest':'c'*64,'binding_id':'binding-b691-'+scenario,'revision':0,'confirmation':'DELETE_ACCOUNT','progress_token':'PROGRESS.SYNTHETIC.B691.'+scenario})
   elif path=='/v1/account-cleanup-operations/operation-b691-confirmationDispatched/confirmation':
    self.send(503,{'error':{'code':'UNAVAILABLE','category':'dependency','message_en':'Unavailable','message_zh':'不可用','outcome':'unknown','recovery':'reconcile_original'}})
   else:self.send_error(404)
 server=ThreadingHTTPServer(('127.0.0.1',a.port),Server);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  endpoint='http://127.0.0.1:'+str(server.server_port)
  spec=importlib.util.spec_from_file_location('original_acceptance_builder',ROOT/'scripts/check_ios_trip_confirm.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  builder=object.__new__(module.XCTestDriver);builder.directory=output;builder.write_project(0)
  (output/'G2CControl.swift').write_text((HERE/'DemoCleanupRenewalUITests.swift').read_text().replace('__B691_LOCAL_ENDPOINT__',endpoint).replace('__B691_ROOT_MODE__','1'if a.root_lifecycle else '0').replace('__B691_REFUSAL_MODE__',a.refusal or '').replace('space.go2china.b691.acceptance',BUNDLE))
  project=output/'G2CAcceptance.xcodeproj';pbx=project/'project.pbxproj';text=pbx.read_text()
  source=json.dumps(str(ROOT/'ios/App/CJProbeApp.swift'))
  if text.count(source)!=1:raise ValueError('one actual app entry expected')
  original_entry=(ROOT/'ios/App/CJProbeApp.swift').read_text()
  marker='@main\nstruct CJProbeApp: App'
  if original_entry.count(marker)!=1:raise ValueError('one original app main annotation expected')
  combined=output/'B691CombinedFixture.swift'
  combined.write_text(original_entry.replace(marker,'struct CJProbeApp: App')+'\n'+(HERE/'DemoCleanupRenewalFixture.swift').read_text())
  text=text.replace(source,json.dumps(str(combined)))
  condition='SWIFT_ACTIVE_COMPILATION_CONDITIONS = "$(inherited) DEBUG G2C_LIO_APP";'
  if text.count(condition)!=1:raise ValueError('one Debug app compilation condition expected')
  text=text.replace(condition,condition.replace('DEBUG G2C_LIO_APP','DEBUG G2C_LIO_APP G2C_DEMO_BETA'))
  text=text.replace('space.go2china.foundation.local',BUNDLE).replace('space.go2china.foundation.control',BUNDLE+'.control')
  info=output/'B691.Info.plist';properties=plistlib.loads((ROOT/'ios/App/Info.plist').read_bytes())
  if a.root_lifecycle:properties.update(G2CDemoBeta=True)
  if a.root_lifecycle and a.refusal!='no-marker':properties.update(G2CB691LocalFixture=True)
  info.write_bytes(plistlib.dumps(properties));text=text.replace(json.dumps(str(ROOT/'ios/App/Info.plist')),json.dumps(str(info)))
  entitlement=output/'B691.entitlements';entitlement.write_bytes(plistlib.dumps({'application-identifier':BUNDLE,'keychain-access-groups':[BUNDLE]}))
  text=text.replace(json.dumps(str(ROOT/'ios/App/Development.entitlements')),json.dumps(str(entitlement)));pbx.write_text(text)
  print(json.dumps({'project':str(project),'scheme':'G2CControl','endpoint':endpoint,'report':str(output/'report.json')}),flush=True)
  if a.prepare_only:return
  if a.serve_only:
   threading.Event().wait();return
  if not a.simulator:p.error('--simulator required to run existing native harness')
  cmd=['xcodebuild','-project',str(project),'-scheme','G2CControl','-configuration','Debug','-destination','platform=iOS Simulator,id='+a.simulator,'-derivedDataPath',str(build),'-resultBundlePath',str(output/'b691.xcresult'),'-onlyUsePackageVersionsFromResolvedFile','-parallel-testing-enabled','NO','ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-','-only-testing:G2CControl/DemoCleanupRenewalUITests','test']
  with (output/'xcodebuild.log').open('w')as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
  if report['status']!='PASS':raise ValueError('complete actual Root results required'if a.root_lifecycle else 'eight actual coordinator results required')
 finally:server.shutdown();server.server_close()

if __name__=='__main__':main()
