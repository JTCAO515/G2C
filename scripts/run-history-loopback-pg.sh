#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
. ./scripts/env.sh
if [ "$#" != 3 ]; then echo 'Usage: scripts/run-history-loopback-pg.sh AUTH_GIT_REPOSITORY MESSAGE_GIT_REPOSITORY APPROVED_OFFLINE_DRIVER_DIR' >&2; exit 2; fi
if [ -e .local-cj005-history-pg ] || [ -L .local-cj005-history-pg ]; then echo 'Refusing existing history PG directory; preserve data, never auto-reuse.' >&2; exit 2; fi
./scripts/build-history-loopback-client.sh
exec .venv/bin/python -B backend/cj_api/tests/history_loopback_postgres.py \
  --auth-repository "$1" --message-repository "$2" --driver-source "$3"
