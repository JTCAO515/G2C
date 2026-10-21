#!/bin/sh
# Source from repository root; no global cache or interpreter installation.
export UV_CACHE_DIR="$PWD/.local/uv-cache"
export UV_PYTHON_INSTALL_DIR="$PWD/.local/python"
export PYTHONPATH="$PWD/backend"
export CLANG_MODULE_CACHE_PATH="$PWD/.local/clang-cache"
export SWIFTPM_MODULECACHE_OVERRIDE="$PWD/.local/swift-module-cache"
