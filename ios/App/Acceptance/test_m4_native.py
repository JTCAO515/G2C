"""Synthetic control/auth and cleanup failure tests; never reads an operator key."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ast
import copy
import http.client
import json
import shutil
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from m4_native import DeviceNative, authenticated_control


class ControlAuthorizationTests(unittest.TestCase):
    def test_rejected_requests_cannot_read_fixture_or_stage_input(self):
        observed = []
        class Base(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                observed.append('fixture')
                self.send_response(200); self.end_headers(); self.wfile.write(b'fixture')
        server = ThreadingHTTPServer(('127.0.0.1', 0), authenticated_control(
            Base, 'SYNTHETIC-CONTROL', lambda path: observed.append(path)))
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            for path in ('/config', '/offline', '/m4-stage-accounts', '/m4-stage-accounts?case=SYNTHETIC'):
                for value in ('', 'SYNTHETIC-WRONG', '\u00e9'):
                    connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
                    connection.request('GET', path, headers={'X-G2C-M4-Control': value})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 403)
                    self.assertNotIn(b'accounts', response.read()); connection.close()
            self.assertEqual(observed, [])
            for path in ('/config', '/m4-stage-accounts?case=SYNTHETIC'):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
                connection.request('GET', path, headers={'X-G2C-M4-Control': 'SYNTHETIC-CONTROL'})
                response = connection.getresponse(); self.assertEqual(response.status, 200)
                response.read(); connection.close()
            self.assertEqual(observed, ['fixture', '/m4-stage-accounts?case=SYNTHETIC'])
        finally:
            server.shutdown(); server.server_close(); thread.join()


class DeviceCleanupTests(unittest.TestCase):
    def make(self, directory):
        root = Path(directory)
        native = DeviceNative('SYNTHETIC-DEVICE', 'synthetic.bundle', root/'project',
            root/'config', root/'build', root, root/'exports', {'A': 'SYNTHETIC-JWT'},
            'SYNTHETIC-CONTROL', {})
        native.output.mkdir()
        native._staging_closed.clear()  # Fixture represents an executing native phase.
        self.addCleanup(lambda: shutil.rmtree(native.private))
        return native

    def test_copy_failure_still_requires_exact_device_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            native = self.make(directory)
            with patch('m4_native.copy_accounts', side_effect=OSError('synthetic interrupted copy')):
                with self.assertRaises(OSError): native.stage()
            self.assertTrue(native.staging_attempted)
            with patch('m4_native.discard_staged_accounts') as discard:
                native.cleanup_input()
                discard.assert_called_once_with('SYNTHETIC-DEVICE', 'synthetic.bundle')
            self.assertFalse(native.staging_attempted)

    def test_unavailable_cleanup_is_fail_and_preserves_pending_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            native = self.make(directory); native.staging_attempted = True
            with patch('m4_native.discard_staged_accounts', side_effect=RuntimeError('synthetic offline')):
                with self.assertRaises(RuntimeError): native.cleanup_input()
            self.assertTrue(native.staging_attempted)
            self.assertTrue(native.report['staged_credential_cleanup'].startswith('FAIL'))

    def test_release_cleanup_uses_debug_discard_before_container_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            native = self.make(directory)
            native.staging_attempted = True; native.configuration = 'Release'
            order = []
            with patch.object(native, 'install', side_effect=lambda value: order.append(value)), \
                 patch('m4_native.discard_staged_accounts', side_effect=lambda *args: order.append('discard')), \
                 patch('m4_native.staged_accounts_present', return_value=True), \
                 patch('m4_native.scan_app_container', side_effect=lambda *args: order.append('scan')):
                native.scan('Release')
            self.assertEqual(order, ['Debug', 'discard', 'scan'])
            self.assertFalse(native.staging_attempted)

    def test_rejected_or_interrupted_container_copy_never_enters_exports(self):
        for failure in (OSError, AssertionError, KeyboardInterrupt):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                native = self.make(directory)
                def copy_then_fail(device, bundle, destination, tokens):
                    destination.mkdir()
                    (destination/'opaque.bin').write_bytes(b'SYNTHETIC-JWT')
                    raise failure('synthetic copy or scan failure')
                with patch('m4_native.scan_app_container', side_effect=copy_then_fail):
                    with self.assertRaises(failure): native.scan('Debug')
                self.assertEqual(list(native.output.iterdir()), [])
                self.assertEqual((native.private/'Debug-app-data/opaque.bin').read_bytes(), b'SYNTHETIC-JWT')

    def test_app_consumption_and_operator_cleanup_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            native = self.make(directory); native.staging_attempted = True
            with patch('m4_native.staged_accounts_present', return_value=True), \
                 patch('m4_native.discard_staged_accounts'), \
                 patch('m4_native.scan_app_container'):
                with self.assertRaises(AssertionError): native.scan('Debug')
            self.assertTrue(native.report['app_staged_input_consumption'].startswith('FAIL'))
            self.assertTrue(native.report['staged_credential_cleanup'].startswith('PASS'))

    def test_late_case_cannot_stage_into_next_native_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            native=self.make(directory);native.case_id='testChineseLarge'
            with patch('m4_native.copy_accounts') as copy:
                with self.assertRaises(ValueError):native.stage(case='testEnglish')
                copy.assert_not_called()
                native.stage(case='testChineseLarge')
                self.assertEqual(copy.call_args.args[-1],{'A':'SYNTHETIC-JWT'})

    def test_cleanup_revokes_new_stages_and_waits_for_inflight_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            native=self.make(directory);entered=threading.Event();release=threading.Event()
            finished=threading.Event();file_present=[False];errors=[]
            def copy(*args):
                entered.set()
                if not release.wait(3):raise TimeoutError('test copy release missing')
                file_present[0]=True
            def discard(*args):file_present[0]=False
            def run(action):
                try:action()
                except BaseException as error:errors.append(error)
            def cleanup():native.cleanup_input();finished.set()
            with patch('m4_native.copy_accounts',side_effect=copy), patch('m4_native.discard_staged_accounts',side_effect=discard):
                worker=threading.Thread(target=lambda:run(native.stage));worker.start()
                self.assertTrue(entered.wait(1))
                closer=threading.Thread(target=lambda:run(cleanup));closer.start()
                self.assertTrue(native._staging_closed.wait(1))
                self.assertFalse(finished.is_set())
                release.set();worker.join(3);closer.join(3)
                self.assertFalse(worker.is_alive());self.assertFalse(closer.is_alive());self.assertEqual(errors,[])
                self.assertFalse(file_present[0]);self.assertFalse(native.staging_attempted)
                self.assertTrue(native.report['staged_credential_cleanup'].startswith('PASS'))
                with self.assertRaises(RuntimeError):native.stage()
                # The next native run explicitly reopens the gate (Debug→Release).
                native._staging_closed.clear();native.stage();self.assertTrue(file_present[0])
                native.cleanup_input();self.assertFalse(file_present[0])

    def test_each_owning_candidate_and_erasure_case_closes_before_replacement(self):
        for name in ('memory_candidate','memory_erasure'):
            with self.subTest(driver=name),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);output=root/'exports';output.mkdir()
                tree=ast.parse(Path(__file__).with_name('check_'+name+'.py').read_text())
                loop=copy.deepcopy(next(n for n in ast.walk(tree) if isinstance(n,ast.For)
                    and ast.unparse(n.target)=='(test, case)' and ast.unparse(n.iter)=='cases.items()'))
                instances=[];workers=[];releasers=[];release=threading.Event();entered=threading.Event();files={};errors=[]
                def stage_copy(device,bundle,destination,tokens):
                    if tokens['A']=='SYNTHETIC.OLD':
                        entered.set()
                        if not release.wait(3):raise TimeoutError('copy release missing')
                    files['input']=tokens['A']
                def fake_run(native,configuration,tests,env):
                    native.configuration=configuration;native._staging_closed.clear();instances.append(native)
                    if len(instances)==1:
                        def stage():
                            try:native.stage(case=native.case_id)
                            except BaseException as error:errors.append(error)
                        worker=threading.Thread(target=stage);workers.append(worker);worker.start()
                        if not entered.wait(1):raise TimeoutError('copy never started')
                        def unblock():
                            if native._staging_closed.wait(2):release.set()
                        releaser=threading.Thread(target=unblock);releasers.append(releaser);releaser.start()
                    return dict(passedTests=1,failedTests=0,skippedTests=0)
                scope=dict(cases={'method1':'first','method2':'second'},report=dict(cases={}),save=lambda:None,
                    tls=True,active={'case':None},args=SimpleNamespace(device='SYNTHETIC',prepare_only=False),
                    output=output,BUNDLE='synthetic.bundle',project=root/'project',configuration_file=root/'config',
                    build=root/'build',ROOT=root,tokens={'first':{'A':'SYNTHETIC.OLD'},'second':{'A':'SYNTHETIC.NEW'}},
                    control_token='SYNTHETIC-CONTROL',DeviceNative=DeviceNative,env={},
                    proof_for=lambda _:dict(action_count=1,other_item_unchanged=True,candidate_files=['synthetic'],item_http_status=200),
                    local_proof=lambda _:dict(item_journals=[],erasure_post_count=1,other_journals=['synthetic'],erasure_originals=['synthetic']))
                try:
                    with patch.object(DeviceNative,'build_for_testing'),patch.object(DeviceNative,'run',fake_run), \
                         patch('m4_native.copy_accounts',side_effect=stage_copy), \
                         patch('m4_native.staged_accounts_present',return_value=False), \
                         patch('m4_native.discard_staged_accounts',side_effect=lambda *args:files.pop('input',None)), \
                         patch('m4_native.scan_app_container'):
                        module=ast.fix_missing_locations(ast.Module(body=[loop],type_ignores=[]))
                        exec(compile(module,'<owning multi-case loop>','exec'),scope)
                        self.assertEqual(scope['report']['cases'],{'method1':'PASS','method2':'PASS'})
                        self.assertEqual(len(instances),2)
                        self.assertTrue(all(n._staging_closed.is_set() for n in instances))
                        self.assertTrue(all(not n.staging_attempted for n in instances))
                        self.assertNotIn('input',files)
                        self.assertTrue(all(row['status']=='PASS' for row in scope['report']['device_native'].values()))
                finally:
                    release.set()
                    for worker in workers+releasers:worker.join(3)
                    for native in instances:shutil.rmtree(native.private)
                self.assertEqual(errors,[])


class OperatorCaseTests(unittest.TestCase):
    def test_prepared_beta_business_case_requires_explicit_operator_selection(self):
        import check_beta_device as beta
        import contextlib
        import io
        for method in ['testBilingualManualNeedsAndOriginalRecovery','testBilingualGeneralFeedbackAndOriginalRecovery']:
            with self.subTest(method=method),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);meta=root/'prepared.json'
                meta.write_text(json.dumps(dict(head='SYNTHETIC-HEAD',device='SYNTHETIC-DEVICE',
                    test='DevelopmentBetaUITests/'+method,work=str(root/'private'),build=str(root/'build'))))
                argv=['check_beta_device.py','--device','SYNTHETIC-DEVICE','--output',str(root/'exports'),
                    '--prepared',str(meta),'--accounts-file',str(root/'never-read.json')]
                def git(arguments,**kwargs):
                    return b'' if arguments[1]=='status' else 'SYNTHETIC-HEAD'
                with patch('sys.argv',argv),patch.object(beta.subprocess,'check_output',side_effect=git), \
                     patch.object(beta,'operator_accounts') as accounts,patch.object(beta,'DeviceNative') as native, \
                     contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:beta.main()
                self.assertEqual(raised.exception.code,2)
                accounts.assert_not_called();native.assert_not_called()
                self.assertEqual(json.loads((root/'exports/report.json').read_text())['status'],'FAIL')

    def test_authenticated_client_cannot_select_another_case(self):
        selected = ['testEnglish']; observed = []
        class Base(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                observed.append(self.path)
                self.send_response(200); self.end_headers()
        server = ThreadingHTTPServer(('127.0.0.1', 0), authenticated_control(
            Base, 'SYNTHETIC-CONTROL', observed.append, lambda: selected[0]))
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            for path in ('/prepare?case=testChineseLarge', '/fixture?case=testChineseLarge',
                         '/m4-stage-accounts?case=testChineseLarge', '/proof?case=testEnglish&case=testChineseLarge'):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
                connection.request('GET', path, headers={'X-G2C-M4-Control':'SYNTHETIC-CONTROL'})
                response = connection.getresponse(); self.assertEqual(response.status, 409)
                response.read(); connection.close()
            self.assertEqual(observed, [])
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
            connection.request('GET', '/prepare?case=testEnglish', headers={'X-G2C-M4-Control':'SYNTHETIC-CONTROL'})
            response = connection.getresponse(); self.assertEqual(response.status, 200)
            response.read(); connection.close()
            self.assertEqual(observed, ['/prepare?case=testEnglish'])
        finally:
            server.shutdown(); server.server_close(); thread.join()


class InterruptedReportTests(unittest.TestCase):
    def driver_try(self, name):
        source = Path(__file__).with_name('check_'+name+'.py').read_text()
        main = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        return copy.deepcopy(next(n for n in main.body if isinstance(n, ast.Try)))

    def execute(self, node, scope):
        module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
        exec(compile(module, '<owning driver failure injection>', 'exec'), scope)

    def test_cleanup_driver_interrupt_cannot_turn_running_case_into_pass(self):
        node = self.driver_try('account_cleanup_component')
        node.body = [ast.Raise(exc=ast.Call(func=ast.Name(id='KeyboardInterrupt',ctx=ast.Load()),args=[],keywords=[]))]
        report = dict(status='RUNNING', cases={'PROVIDED':'RUNNING'})
        snapshots = []
        scope = dict(report=report, args=SimpleNamespace(native_device=False,prepare_only=False),
            audits=[], control=None, servers=[], threads=[], tls=None,
            save=lambda: snapshots.append(json.loads(json.dumps(report))))
        with self.assertRaises(KeyboardInterrupt): self.execute(node, scope)
        self.assertEqual(report['status'], 'FAIL')
        self.assertFalse(any(row['status'] in ('PASS','PARTIAL_PASS') for row in snapshots))

    def test_beta_native_failure_is_preserved_after_cleanup_and_failed_scan(self):
        for failure,expected in [(None,'PASS'),(AssertionError('SYNTHETIC credential hit'),'FAIL'),
                                 (RuntimeError('SYNTHETIC device unavailable'),'UNRUN')]:
            with self.subTest(scan_status=expected):
                node=self.driver_try('beta_device')
                original=RuntimeError('SYNTHETIC native exit65')
                node.body=[ast.Raise(exc=ast.Name(id='original',ctx=ast.Load()))]
                report={'status':'RUNNING'};events=[];snapshots=[]
                def scan(configuration):
                    self.assertEqual(configuration,'Debug');events.append('scan')
                    if failure:raise failure
                native=SimpleNamespace(cleanup_input=lambda:events.append('cleanup'),scan=scan)
                scope=dict(original=original,report=report,native=native,server=None,thread=None,
                    native_run_incomplete=True,save=lambda:snapshots.append(copy.deepcopy(report)))
                with self.assertRaises(RuntimeError) as raised:self.execute(node,scope)
                self.assertIs(raised.exception,original)
                self.assertEqual(events,['cleanup','scan'])
                self.assertEqual(report['status'],'FAIL')
                self.assertEqual(report['failure_container_scan']['status'],expected)
                self.assertTrue(snapshots)
                self.assertFalse(any(row['status'] in ('PASS','PARTIAL_PASS') for row in snapshots))

    def test_final_scan_error_never_publishes_success(self):
        for name in ('memory_candidate','memory_erasure'):
            with self.subTest(driver=name), tempfile.TemporaryDirectory() as directory:
                node = self.driver_try(name); node.body = [ast.Pass()]
                report = dict(status='VERIFYING_CLEANUP', cases={'selected':'PASS'})
                snapshots = []
                output = SimpleNamespace(rglob=lambda _: (_ for _ in ()).throw(OSError('synthetic unreadable export')))
                scope = dict(report=report, observed={}, observations={}, control=None,server=None,thread=None,
                    tls=True,native=None,device_project_root=Path(directory),control_token='SYNTHETIC',
                    output=output,original_size=None,args=SimpleNamespace(prepare_only=False),suite_complete=True,
                    save=lambda: snapshots.append(json.loads(json.dumps(report))))
                with self.assertRaises(OSError): self.execute(node, scope)
                self.assertEqual(report['status'],'FAIL')
                self.assertFalse(any(row['status']=='PASS' for row in snapshots))


if __name__ == '__main__': unittest.main()
