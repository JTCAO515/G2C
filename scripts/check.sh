#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
. ./scripts/env.sh
uv run --locked python scripts/check_contract.py
uv run --locked pytest backend/tests -q
