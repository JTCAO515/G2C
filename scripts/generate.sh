#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
. ./scripts/env.sh
mkdir -p .local
output=$(mktemp -d "$PWD/.local/generate.XXXXXX")
trap 'rm -rf "$output"' EXIT
uv run --locked datamodel-codegen --input contracts/api/openapi.json --input-file-type openapi --output "$output/generated.py" --output-model-type pydantic_v2.BaseModel --target-python-version 3.12 --disable-timestamp --formatters black isort
./scripts/swift.sh run swift-openapi-generator generate contracts/api/openapi.json --config contracts/api/swift-generator.yaml --output-directory "$output/swift"
if [ "${1:-}" = "--check" ]; then
    cmp "$output/generated.py" backend/cj_api/generated.py
    diff -ru ios/Sources/CJAPI/Generated "$output/swift"
else
    cp "$output/generated.py" backend/cj_api/generated.py
    mkdir -p ios/Sources/CJAPI/Generated
    cp "$output/swift/"*.swift ios/Sources/CJAPI/Generated/
fi
