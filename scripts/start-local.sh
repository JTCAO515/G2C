#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
. ./scripts/env.sh
if [ "$#" != 1 ]; then echo 'Usage: scripts/start-local.sh PORT' >&2; exit 2; fi
case "$1" in ''|*[!0-9]*) echo 'PORT must be numeric' >&2; exit 2;; esac
if [ "${CJ_ENV:-}" != local ]; then echo 'CJ_ENV=local is required' >&2; exit 2; fi
exec uv run --locked uvicorn cj_api.app:create_app --factory --host 127.0.0.1 --port "$1" --no-access-log
