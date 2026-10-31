"""Capture association for C scoped publisher; data only until original hold()."""
from contextvars import ContextVar
from dataclasses import dataclass,field
from hashlib import sha256
import base64
from cj_message.edit_protocol import MEMORY_ABI
from .runtime import RuntimeDenied
from .typed import packed


def snapshot_bytes(run):
    return packed(dict(epoch=run.snapshot.epoch,items=[dict(original=base64.b64encode(item.command.raw).decode(),
        version=item.version,status=item.status,recorded_at=item.recorded_at.isoformat()) for item in run.snapshot.items]))


class CaptureRegistry:
    def __init__(self):self.current=ContextVar('scoped_memory_capture',default=None)
    def captured(self,binding):
        value=self.current.get()
        if value is None or value.binding!=binding:raise RuntimeDenied('original actual memory capture required')
        return value


class TrackedMemory:
    def __init__(self,original,registry):self.original,self.registry=original,registry
    def capture(self,binding):
        value=self.original.capture(binding);self.registry.current.set(value);return value


@dataclass(frozen=True)
class ScopedMemoryConfiguration:
    original:object
    registry:CaptureRegistry=field(default_factory=CaptureRegistry,repr=False)
    abi:str=field(default=MEMORY_ABI,init=False)
    def bind(self,database,scope,identity,admit,*,message_context):
        return TrackedMemory(self.original.bind(database,scope,identity,admit,message_context=message_context),self.registry)

    def bind_readonly(self,database,scope,identity,admit,*,message_context):
        return TrackedMemory(self.original.bind_readonly(database,scope,identity,admit,message_context=message_context),self.registry)
