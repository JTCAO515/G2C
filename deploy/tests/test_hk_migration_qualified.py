"""Migrations from 0049 on are applied in Hong Kong by deploy.hk.demo_schema through the operator session,
whose search_path is ``pg_catalog, public, pg_temp`` (supabase_test_database.discard_session). An unqualified
named CREATE there lands in pg_catalog and is refused, which stopped the first59 apply on 2026-11-27 (0056-0058).
demo_schema now applies migrations with ``public`` first, and every new object must still name its schema;
0056-0058 are exempt because their bytes were applied as-is in Hong Kong. Indexes, triggers and policies
follow their table and roles are global, so only schema-qualified object kinds are checked.
"""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FIRST_HK_OPERATOR_MIGRATION = 49
# Applied as-is in Hong Kong by the first59 resume (2026-11-28) with the Demo migration search_path
# (deploy.hk.demo_schema.MIGRATION_SEARCH_PATH); their bytes are frozen, so they stay unqualified.
FROZEN_UNQUALIFIED = {
    56: 'applied as-is to Hong Kong; content frozen',
    57: 'applied as-is to Hong Kong; content frozen',
    58: 'applied as-is to Hong Kong; content frozen',
}
NAMED = re.compile(
    r'(?is)\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:UNLOGGED\s+|TEMP(?:ORARY)?\s+)?'
    r'(TABLE|FUNCTION|PROCEDURE|VIEW|MATERIALIZED\s+VIEW|SEQUENCE|TYPE|DOMAIN|AGGREGATE)\s+'
    r'(?:IF\s+NOT\s+EXISTS\s+)?("?[A-Za-z_][\w$]*"?(?:\s*\.\s*"?[A-Za-z_][\w$]*"?)?)')


def unqualified(sql):
    text = re.sub(r'--[^\n]*', '', sql)
    return [(kind.upper(), name) for kind, name in NAMED.findall(text) if '.' not in name]


def test_detector_catches_the_first59_failure_and_accepts_qualified_names():
    assert unqualified('CREATE TABLE cj_service_request_scope (scope text);') == [('TABLE', 'cj_service_request_scope')]
    assert unqualified('create or replace function f() returns int') == [('FUNCTION', 'f')]
    assert unqualified('CREATE TABLE public.t (x int); CREATE FUNCTION public.f() RETURNS trigger') == []
    assert unqualified('CREATE INDEX i ON public.t(x); CREATE TRIGGER g BEFORE UPDATE ON public.t') == []
    assert unqualified('-- CREATE TABLE commented (x int)\nCREATE ROLE r NOLOGIN;') == []


def test_hk_operator_migrations_name_the_schema_of_every_created_object():
    manifest = json.loads((ROOT / 'backend/migrations/manifest.json').read_text())
    offenders = {}
    for migration in manifest['migrations']:
        if migration['version'] < FIRST_HK_OPERATOR_MIGRATION:
            continue
        found = unqualified((ROOT / migration['file']).read_text())
        if migration['version'] in FROZEN_UNQUALIFIED:
            assert found, f'{migration["file"]} is exempt only while it holds unqualified creates'
            continue
        if found:
            offenders[migration['file']] = found
    assert offenders == {}


def test_frozen_exemptions_are_exactly_the_migrations_already_applied_unqualified():
    assert sorted(FROZEN_UNQUALIFIED) == [56, 57, 58]


def test_demo_schema_applies_migrations_with_public_first():
    from deploy.hk import demo_schema
    assert demo_schema.MIGRATION_SEARCH_PATH == 'public, pg_catalog, pg_temp'
