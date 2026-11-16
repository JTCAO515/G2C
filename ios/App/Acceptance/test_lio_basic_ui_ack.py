import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import lio_basic_ui_driver as driver


class Running:
    def poll(self): return None


class NativeAckTests(unittest.TestCase):
    def test_malformed_ack_locks_controller_without_advancing_or_another_tap(self):
        for kind in ['tap', 'audit_all']:
            for malformed in ['missing_ok', 'invalid_json', 'wrong_kind', 'missing_clock']:
                with self.subTest(kind=kind, malformed=malformed), tempfile.TemporaryDirectory() as path:
                    native = object.__new__(driver.NativeUI)
                    native.failed, native.sequence = False, 0
                    native.process, native.bundle = Running(), 'synthetic-controller-only'
                    native.commands = Path(path)
                    original_write = driver.write

                    def reply(target, request):
                        original_write(target, request)
                        value = dict(id=request['id'], kind=kind, ok=True,
                                     started_uptime=1.0, finished_uptime=2.0)
                        if malformed == 'missing_ok': del value['ok']
                        elif malformed == 'wrong_kind': value['kind'] = 'snapshot'
                        elif malformed == 'missing_clock': del value['finished_uptime']
                        content = b'{' if malformed == 'invalid_json' else json.dumps(value).encode()
                        (native.commands / '00000.response.json').write_bytes(content)

                    with patch.object(driver, 'write', side_effect=reply):
                        with self.assertRaises(RuntimeError): native.command(kind, identifier='synthetic')
                        self.assertTrue(native.failed)
                        self.assertEqual(native.sequence, 0)
                        with self.assertRaises(RuntimeError): native.command(kind, identifier='synthetic')
                    self.assertFalse((native.commands / '00001.request.json').exists())


if __name__ == '__main__': unittest.main()
