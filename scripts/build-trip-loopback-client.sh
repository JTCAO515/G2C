#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
. ./scripts/env.sh
./scripts/swift.sh build --target CJAPI
xcrun swiftc -swift-version 6 -parse-as-library -target arm64-apple-macos14.0 \
  -module-cache-path "$PWD/.local/receipt-consumer-module-cache" -I ios/.build/debug \
  backend/cj_api/tests/trip_loopback_client.swift \
  ios/.build/debug/CJAPI.o ios/.build/debug/OpenAPIRuntime.o ios/.build/debug/OpenAPIURLSession.o \
  ios/.build/debug/HTTPTypes.o ios/.build/debug/DequeModule.o \
  ios/.build/debug/InternalCollectionsUtilities.o ios/.build/debug/SpanPreview.o \
  -o .local/trip-loopback-client
