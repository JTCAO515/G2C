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


class OperatorCaseTests(unittest.TestCase):
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
