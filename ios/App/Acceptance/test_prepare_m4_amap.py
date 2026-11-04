"""Synthetic filesystem boundary checks. Never invokes Keychain or an SDK."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('prepare_m4_amap', Path(__file__).with_name('prepare_m4_amap.py'))
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class LocalKeyBoundaryTests(unittest.TestCase):
    def test_existing_directory_or_symlink_cannot_redirect_key_output(self):
        for directory_link in (False, True):
            with self.subTest(directory_link=directory_link), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root/'ios').mkdir()
                target = root/'tracked-placeholder.txt'
                target.write_text('SYNTHETIC-UNCHANGED')
                local = root/'ios/.local-amap-device'
                if directory_link:
                    destination = root/'previous-build'
                    destination.mkdir()
                    local.symlink_to(destination, target_is_directory=True)
                else:
                    local.mkdir()
                (local/'AMapLocalKey.plist').symlink_to(target)
                with patch.object(prepare, 'ROOT', root), \
                        patch.object(sys, 'argv', ['prepare', '--sdk-cache', str(root), '--inject-key']), \
                        patch.object(prepare.subprocess, 'run') as run:
                    with self.assertRaises(FileExistsError):
                        prepare.main()
                    self.assertEqual(run.call_count, 1)
                    self.assertEqual(run.call_args.args[0][:2], ['git', 'check-ignore'])
                self.assertEqual(target.read_text(), 'SYNTHETIC-UNCHANGED')

    def test_archive_pin_failure_precedes_any_key_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'ios').mkdir()
            (root/'map-11.3.100.zip').write_bytes(b'SYNTHETIC-BAD-ARCHIVE')
            with patch.object(prepare, 'ROOT', root), \
                    patch.object(sys, 'argv', ['prepare', '--sdk-cache', str(root), '--inject-key']), \
                    patch.object(prepare.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'archive pin mismatch'):
                    prepare.main()
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.args[0][:2], ['git', 'check-ignore'])
            self.assertFalse((root/'ios/.local-amap-device/AMapLocalKey.plist').exists())


if __name__ == '__main__':
    unittest.main()
