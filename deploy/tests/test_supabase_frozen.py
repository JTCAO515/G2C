"""The frozen Supabase source never receives a later migration (#1925 review, 58.1 gate)."""
from contextlib import contextmanager

import pytest


class Connection:
    pass


def _initialize(monkeypatch, tmp_path, applied, migrations):
    monkeypatch.setenv('CJ_ENV', 'local')
    from deploy.hk import entrypoint
    connection = Connection()
    calls = []

    @contextmanager
    def operator():
        yield connection, None

    monkeypatch.setattr(entrypoint, 'local_database_target', lambda: False)
    monkeypatch.setattr(entrypoint, 'control', lambda: tmp_path)
    monkeypatch.setattr(entrypoint.checkpoint, 'operator', operator)
    monkeypatch.setattr(entrypoint.checkpoint, 'versions', lambda: [item['version'] for item in migrations])
    monkeypatch.setattr(entrypoint.checkpoint, 'bootstrap', lambda control, seed: calls.append('bootstrap'))
    monkeypatch.setattr(entrypoint.migrate, 'load', lambda: migrations)
    monkeypatch.setattr(entrypoint.migrate, 'applied', lambda conn: list(applied))
    monkeypatch.setattr(entrypoint.migrate, 'up', lambda conn, items, target: calls.append(('up', target)))
    entrypoint.initialize(runtime=None)
    return calls


def _migrations(top):
    return [dict(version=number, name=f'{number:04d}') for number in range(1, top + 1)]


def test_supabase_target_with_a_pending_migration_fails_closed_before_migrating(monkeypatch, tmp_path):
    calls = []
    with pytest.raises(ValueError, match='supabase_source_frozen_pending_migrations'):
        calls = _initialize(monkeypatch, tmp_path, applied=range(1, 58), migrations=_migrations(58))
    assert calls == []


def test_supabase_target_with_nothing_pending_starts_unchanged(monkeypatch, tmp_path):
    calls = _initialize(monkeypatch, tmp_path, applied=range(1, 56), migrations=_migrations(55))
    assert calls == [('up', 55), 'bootstrap']


def test_supabase_target_with_a_gap_also_fails_closed(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match='supabase_source_frozen_pending_migrations'):
        _initialize(monkeypatch, tmp_path, applied=[1, 2, 4], migrations=_migrations(4))


def test_hk_local_target_never_consults_the_supabase_freeze(monkeypatch, tmp_path):
    monkeypatch.setenv('CJ_ENV', 'local')
    from deploy.hk import entrypoint
    released = []

    @contextmanager
    def operator():
        yield Connection(), None

    monkeypatch.setattr(entrypoint, 'local_database_target', lambda: True)
    monkeypatch.setattr(entrypoint, 'control', lambda: tmp_path)
    monkeypatch.setattr(entrypoint.checkpoint, 'operator', operator)
    monkeypatch.setattr(entrypoint.checkpoint, 'require_release', lambda conn, control: released.append(control))
    monkeypatch.setattr(entrypoint, 'require_frozen_supabase_schema',
                        lambda *args: pytest.fail('hk-local must not consult the Supabase freeze'))
    entrypoint.initialize(runtime=None)
    assert released == [tmp_path]
