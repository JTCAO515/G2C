#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
. ./scripts/env.sh
if [ "$#" != 2 ]; then
  echo 'Usage: scripts/run-loopback-pg.sh AUTH_GIT_REPOSITORY MESSAGE_GIT_REPOSITORY' >&2
  exit 2
fi
if [ -e .local-cj005-pg ] || [ -L .local-cj005-pg ]; then
  echo 'Refusing existing CJ005 PG directory; preserve data and use an explicitly authorized fresh checkout.' >&2
  exit 2
fi
./scripts/build-loopback-client.sh
exec .venv/bin/python -B backend/cj_api/tests/loopback_postgres.py \
  --auth-repository "$1" --message-repository "$2"
