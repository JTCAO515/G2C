"""CLEANUP-DEVICE@4: the two erasure journals actually provided by A480."""
from .device_v3 import DeviceActions as OriginalActions,TARGETS as V3_TARGETS

VERSION='CLEANUP-DEVICE@4'
TARGETS=V3_TARGETS+('device-cache/memory-erasure-pending','device-cache/memory-erasure-observations')


class DeviceActions(OriginalActions):
    version=VERSION
