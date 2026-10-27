#!/bin/sh
# Local equivalent of CI: all non-PostgreSQL checks, then PostgreSQL suites if binaries exist.
set -eu
cd "$(dirname "$0")/.."
. ./scripts/env.sh
uv run --locked python -B scripts/test.py
if [ -n "${CJ_PG_BINDIR:-}" ] || command -v pg_config >/dev/null 2>&1; then
    uv run --locked python -B scripts/pg_suites.py
else
    echo 'SKIP PostgreSQL suites: set CJ_PG_BINDIR or install pg_config' >&2
fi
