#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
. ./scripts/env.sh
if [ "$#" != 2 ]; then
  echo 'Usage: scripts/check-cleanup-progress-wire.sh AUTH_GIT_REPOSITORY FIXED_SOURCE_GIT_REPOSITORY' >&2
  exit 2
fi
fixed_export=$(uv run --locked python -B scripts/prepare-cleanup-progress-deps.py --auth-repository "$1" --source-repository "$2")
export PYTHONPATH="$PWD/backend:$fixed_export/backend/auth:$fixed_export/backend/cleanup:$PWD/backend/message:$PWD/backend/cj_api/tests"
PYTHONDONTWRITEBYTECODE=1 uv run --locked python -B -m unittest discover -s backend/cj_api/tests -p cleanup_progress_wire_checks.py -v
