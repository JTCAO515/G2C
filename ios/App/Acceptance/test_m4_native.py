"""Synthetic control/auth and cleanup failure tests; never reads an operator key."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import shutil
from pathlib import Path
import tempfile
import threading
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
            Base, 'SYNTHETIC-CONTROL', lambda: observed.append('stage')))
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            for path in ('/config', '/offline', '/m4-stage-accounts'):
                for value in ('', 'SYNTHETIC-WRONG'):
                    connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
                    connection.request('GET', path, headers={'X-G2C-M4-Control': value})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 403)
                    self.assertNotIn(b'accounts', response.read()); connection.close()
            self.assertEqual(observed, [])
            for path in ('/config', '/m4-stage-accounts'):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
                connection.request('GET', path, headers={'X-G2C-M4-Control': 'SYNTHETIC-CONTROL'})
                response = connection.getresponse(); self.assertEqual(response.status, 200)
                response.read(); connection.close()
            self.assertEqual(observed, ['fixture', 'stage'])
        finally:
            server.shutdown(); server.server_close(); thread.join()


class DeviceCleanupTests(unittest.TestCase):
    def make(self, directory):
        root = Path(directory)
        native = DeviceNative('SYNTHETIC-DEVICE', 'synthetic.bundle', root/'project',
            root/'config', root/'build', root, root, {'A': 'SYNTHETIC-JWT'},
            'SYNTHETIC-CONTROL', {})
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
                 patch('m4_native.scan_app_container', side_effect=lambda *args: order.append('scan')):
                native.scan('Release')
            self.assertEqual(order, ['Debug', 'discard', 'scan'])
            self.assertFalse(native.staging_attempted)


if __name__ == '__main__': unittest.main()
