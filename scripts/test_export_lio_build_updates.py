"""The publication reader must reject ambiguous local release content."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('export_lio_updates', Path(__file__).with_name('export_lio_build_updates.py'))
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)


class ExportBuildUpdatesTests(unittest.TestCase):
    def test_duplicate_fields_and_nonfinite_values_are_rejected(self):
        for raw in ['{"schema":1,"schema":1}', '{"title":{"en":"One","en":"Two"}}', '{"schema":NaN}']:
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'notes.json'; path.write_text(raw)
                with self.assertRaises(ValueError):
                    EXPORT.load_book(path)

    def test_export_uses_packaged_current_and_previous_content(self):
        book = EXPORT.load_book(EXPORT.RESOURCE)
        self.assertEqual([release['build'] for release in book['releases']], [44,43])
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
