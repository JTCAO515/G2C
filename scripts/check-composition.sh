#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
. ./scripts/env.sh
if [ "$#" != 2 ]; then
    echo 'Usage: scripts/check-composition.sh AUTH_GIT_REPOSITORY MESSAGE_GIT_REPOSITORY' >&2
    exit 2
fi
uv run --locked python scripts/prepare-composition-deps.py --auth-repository "$1" --message-repository "$2"
# Only fixed Git exports are added for owner tests; no moving author tree imports.
export PYTHONPATH="$PWD/backend:$PWD/.local/composition-deps/backend/auth:$PWD/.local/composition-deps/backend/message"
PYTHONDONTWRITEBYTECODE=1 uv run --locked python -B -m unittest discover -s backend/cj_api/tests -v
