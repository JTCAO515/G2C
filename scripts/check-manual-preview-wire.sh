#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
. ./scripts/env.sh
if [ "$#" != 2 ]; then
    echo 'Usage: scripts/check-manual-preview-wire.sh AUTH_GIT_REPOSITORY MANUAL_EDIT_GIT_REPOSITORY' >&2
    exit 2
fi
fixed_export=$(uv run --locked python -B scripts/prepare-manual-preview-deps.py --auth-repository "$1" --source-repository "$2")
export PYTHONPATH="$PWD/backend:$fixed_export/backend/auth:$fixed_export/backend/trip:$fixed_export/backend/manual_edit:$PWD/backend/message:$PWD/backend/cj_api/tests"
PYTHONDONTWRITEBYTECODE=1 uv run --locked python -B -m unittest discover -s backend/cj_api/tests -p manual_preview_wire_checks.py -v
