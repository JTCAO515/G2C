"""The publication reader must reject ambiguous local release content."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import io

SPEC = importlib.util.spec_from_file_location('export_lio_updates', Path(__file__).with_name('export_lio_build_updates.py'))
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)
CURRENT_BUILD = 51
PREVIOUS_BUILD = 50


class ExportBuildUpdatesTests(unittest.TestCase):
    def test_testflight_body_matches_normal_export_and_fits_with_issue_heading(self):
        def export(build, *args):
            output = io.StringIO()
            with patch('sys.argv', ['export', '--build', str(build), *args]), contextlib.redirect_stdout(output):
                EXPORT.main()
            return output.getvalue()
        for build in (CURRENT_BUILD, PREVIOUS_BUILD):
            with self.subTest(build=build):
                body = export(build, '--testflight')
                self.assertEqual(body, export(build))
                issue = export(build, '--source-commit', 'a' * 40)
                self.assertTrue(issue.endswith(body))
                self.assertLessEqual(len(issue.encode('utf-16-le')) // 2, 4000)

    def test_testflight_rejects_heading_and_oversize_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'notes.txt'
            for build in (CURRENT_BUILD, PREVIOUS_BUILD):
                book = EXPORT.load_book(EXPORT.RESOURCE)
                release = next(release for release in book['releases'] if release['build'] == build)
                release['sections'][0]['items']['en'] = ['😀' * 2001]
                cases = [(['--source-commit', 'a' * 40], None), ([], book)]
                for args, oversized in cases:
                    with self.subTest(build=build, args=args), patch('sys.argv', ['export', '--build', str(build), '--testflight', '--output', str(output), *args]), contextlib.redirect_stderr(io.StringIO()):
                        with patch.object(EXPORT, 'load_book', return_value=oversized) if oversized else contextlib.nullcontext():
                            with self.assertRaises(SystemExit):
                                EXPORT.main()
                        self.assertFalse(output.exists())

    def test_duplicate_fields_and_nonfinite_values_are_rejected(self):
        for raw in ['{"schema":1,"schema":1}', '{"title":{"en":"One","en":"Two"}}', '{"schema":NaN}']:
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'notes.json'; path.write_text(raw)
                with self.assertRaises(ValueError):
                    EXPORT.load_book(path)

    def test_export_uses_packaged_current_and_previous_content(self):
        book = EXPORT.load_book(EXPORT.RESOURCE)
        self.assertEqual(book['currentBuild'], CURRENT_BUILD)
        self.assertEqual([release['build'] for release in book['releases']], [CURRENT_BUILD, PREVIOUS_BUILD])
        for release in book['releases']:
            for language in ['en','zh']:
                rendered = EXPORT.render(release, language)
                self.assertEqual(len(release['sections']), 5)
                for section in release['sections']:
                    self.assertIn(section['title'][language], rendered)
                    for item in section['items'][language]:
                        self.assertIn(item, rendered)


if __name__ == '__main__':
    unittest.main()
