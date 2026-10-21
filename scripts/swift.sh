#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
. ./scripts/env.sh
command_name="$1"
shift
exec swift "$command_name" --package-path ios --cache-path "$PWD/.local/swift-cache" --config-path "$PWD/.local/swift-config" --security-path "$PWD/.local/swift-security" --disable-sandbox --disable-automatic-resolution "$@"
