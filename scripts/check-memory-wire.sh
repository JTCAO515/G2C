#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
. ./scripts/env.sh
if [ "$#" != 2 ]; then
    echo 'Usage: scripts/check-memory-wire.sh AUTH_GIT_REPOSITORY MEMORY_GIT_REPOSITORY' >&2
    exit 2
fi
fixed_export=$(uv run --locked python -B scripts/prepare-memory-deps.py --auth-repository "$1" --source-repository "$2")
export PYTHONPATH="$PYTHONPATH:$fixed_export/backend/memory:$fixed_export/backend/auth"
PYTHONDONTWRITEBYTECODE=1 uv run --locked python -B -m unittest discover -s backend/cj_api/tests -p memory_wire_checks.py -v
