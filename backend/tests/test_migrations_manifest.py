"""Offline integrity of the registered migration chain; scripts/migrate.py verify runs it on PostgreSQL."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('migrate', ROOT / 'scripts/migrate.py')
migrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate)


def test_chain_is_contiguous_hashed_and_reversible():
    migrations = migrate.load()  # raises on gaps or sha256 mismatch
    assert [m['version'] for m in migrations][0] == 1
    for m in migrations:
        assert (ROOT / m['down']).read_text().strip(), m['down']


def test_every_domain_schema_file_is_registered():
    registered = {m['file'] for m in migrate.load()}
    on_disk = {str(p.relative_to(ROOT)) for p in (ROOT / 'backend').glob('*/sql/*.sql')}
    on_disk |= {str(p.relative_to(ROOT)) for p in (ROOT / 'backend').glob('*/schema.sql')}
    assert on_disk <= registered, sorted(on_disk - registered)
