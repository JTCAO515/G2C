#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
. ./scripts/env.sh
if [ "$#" != 2 ]; then echo 'Usage: scripts/check-aead-cursor.sh AUTH_GIT_REPOSITORY MESSAGE_GIT_REPOSITORY' >&2; exit 2; fi
uv run --locked python scripts/prepare-composition-deps.py --auth-repository "$1" --message-repository "$2"
export_key=$(uv run --locked python -c "import json; p=json.load(open('backend/cj_api/composition_pins.json')); print('-'.join(s['commit'] for s in p['sources']))")
export PYTHONPATH="$PWD/backend:$PWD/.local/composition-deps/$export_key/backend/auth:$PWD/.local/composition-deps/$export_key/backend/message:$PWD/backend/cj_api/tests"
PYTHONDONTWRITEBYTECODE=1 uv run --locked python -B -m unittest test_aead_cursor -v
