#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
. ./scripts/env.sh
if [ "$#" != 1 ]; then
  echo 'Usage: scripts/check-verified-session-wire.sh AUTH_GIT_REPOSITORY' >&2
  exit 2
fi
fixed_export=$(uv run --locked python -B scripts/prepare-session-auth-deps.py --auth-repository "$1")
export PYTHONPATH="$PWD/backend:$fixed_export/backend/auth:$PWD/backend/cj_api/tests"
PYTHONDONTWRITEBYTECODE=1 uv run --locked python -B -m unittest verified_session_wire_checks.SessionWireChecks -v
