"""Frozen CLEANUP-DEVICE@2 target additions; V1 target bytes are unchanged."""
from .device_bridge import TARGETS as V1_TARGETS

VERSION='CLEANUP-DEVICE@2'
TARGETS=V1_TARGETS+('device-cache/memory-manual-pending',
    'device-cache/memory-lifecycle-pending','device-cache/memory-typed-pending',
    'device-cache/memory-key-keychain','device-cache/needs-pending','device-cache/needs-key-keychain')
