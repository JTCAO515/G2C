"""Controlled RUN pause after a real original model settles, never a resend."""
from dataclasses import dataclass
from threading import Event,Lock
from time import monotonic

from cj_usage.metered_exit import BudgetUnknown
from cj_usage.registered_exit import RegisteredExit
from runtime_adapter.contract import Unavailable


@dataclass
class Pause:
    binding: object
    deadline: float
    ready: Event
    release: Event


class ControlledGeneration:
    def __init__(self,*,clock=monotonic):
        self.clock=clock;self.pauses={};self.lock=Lock()

    def prepare(self,message_id,deadline):
        with self.lock:
            if message_id in self.pauses:raise Unavailable('ORIGINAL_CONTROL_ALREADY_EXISTS')
            self.pauses[message_id]=Pause(None,deadline,Event(),Event())

    def completed(self,operation):
        if operation.command.kind!='model':return
        with self.lock:
            pause=self.pauses.get(operation.binding.message_id)
            if pause is None or pause.ready.is_set():return
            pause.binding=operation.binding;pause.ready.set()
        # Called only after the original RegisteredExit's full stream/settlement
        # returned. No RUN row/source lease is held by this observer.
        if not pause.release.wait(max(0,pause.deadline-self.clock())):
            raise BudgetUnknown('original controlled generation expired; query only')

    def wait_started(self,message_id,deadline):
        with self.lock:pause=self.pauses.get(message_id)
        if pause is None or not pause.ready.wait(max(0,deadline-self.clock())):
            raise Unavailable('ORIGINAL_CONTROL_START_UNAVAILABLE')
        return pause.binding

    def release(self,message_id):
        with self.lock:pause=self.pauses.get(message_id)
        if pause is None:raise Unavailable('ORIGINAL_CONTROL_UNAVAILABLE')
        pause.release.set()


class ControlledRegisteredExit(RegisteredExit):
    """Same implementation/limits/account; observe only successful completion."""
    def __init__(self,*args,observer,**kwargs):
        super().__init__(*args,**kwargs);self.observer=observer

    def stream(self,prepared):
        yield from super().stream(prepared)
        self.observer.completed(prepared.step)
