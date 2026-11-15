"""Join issued provider originals to the actual native4 calendar/profile lease.

This is a source-holder component, not a Source4 candidate compiler or writer.
The trusted L host supplies the registered producer's capture/hold interface.
It never supplies a list of records as collection or publication authority.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json
import threading

from cj_needs.revision_lease import LeaseUnavailable
from cj_trip.domain import packed
from .rich_calendar_source import RichCalendarContextSource

SOURCE = 'TRIP-RICH-PROVIDER-SOURCE.1'
_FACTORY = object()


@dataclass(frozen=True, repr=False, init=False)
class RichProviderCapture:
    calendar: object
    providers: object
    reader: object
    raw: bytes

    def __init__(self, calendar, providers, reader, raw, *, _factory=None):
        if _factory is not _FACTORY:
            raise TypeError('issued combined provider source required')
        for key, value in (('calendar', calendar), ('providers', providers), ('reader', reader), ('raw', raw)):
            object.__setattr__(self, key, value)

    @property
    def binding(self): return self.calendar.binding

    @property
    def basis(self): return self.calendar.basis

    @property
    def profile(self): return self.calendar.profile

    @property
    def provider_records(self): return json.loads(self.raw)['provider_records']

    def records(self): return self.calendar.records()


class RichProviderContextSource(RichCalendarContextSource):
    def __init__(self, *args, provider_reader, **kwargs):
        super().__init__(*args, **kwargs)
        if provider_reader is None:
            raise ValueError('actual registered provider source required')
        self.provider_reader = provider_reader
        self.provider_captures = {}
        self.provider_active = ContextVar('rich_provider_source_lease', default=None)

    def seal_providers(self, binding, calendar):
        """Materialize registered originals outside worker._step and RUN locks.

        Call after the actual provider operations settle, with no RUN, MESSAGE,
        Memory, NEEDS or Trip publication frame held. The producer may acquire
        RUN while checking original inputs here. No provider call or retry occurs.
        """
        if self._active.get() is not None or self.calendar_active.get() is not None:
            raise LeaseUnavailable('provider materialization cannot run inside publication locks')
        if (calendar is not self.calendar_captures.get(binding) or calendar.binding != binding
                or calendar.reader is not self.calendar_reader or calendar.profile_reader is not self.profile_reader):
            raise LeaseUnavailable('issued original calendar/profile capture required')
        reader = self.provider_reader
        providers = reader.capture(binding)
        value = json.loads(calendar.raw)
        value.update(version=SOURCE, provider_records=providers.records)
        raw = packed(value)
        if len(raw) > self.max_bytes:
            raise LeaseUnavailable('combined provider source exceeds original byte bound')
        capture = RichProviderCapture(calendar, providers, reader, raw, _factory=_FACTORY)
        self.provider_captures[binding] = capture
        return capture

    @contextmanager
    def hold_additional_sources(self, binding, needs, message):
        capture = self.provider_captures.get(binding)
        if (capture is None or capture.calendar is not self.calendar_captures.get(binding)
                or capture.reader is not self.provider_reader):
            raise LeaseUnavailable('sealed original provider source required')
        with super().hold_additional_sources(binding, needs, message), \
                capture.reader.hold(binding, capture.providers, message) as held:
            token = self.provider_active.set((capture, held, threading.get_ident()))
            try:
                held.check()
                yield
            finally:
                self.provider_active.reset(token)

    @contextmanager
    def hold_for_publication(self, binding):
        capture = self.provider_captures.get(binding)
        if capture is None:
            raise LeaseUnavailable('provider sealing must precede publication')
        with super().hold_for_publication(binding):
            self.check(binding, capture)
            yield lambda: self.check(binding, capture)
            self.check(binding, capture)

    def check(self, binding, capture):
        if type(capture) is not RichProviderCapture:
            return super().check(binding, capture)
        state = self.provider_active.get()
        if (state is None or state[0] is not capture or self.provider_captures.get(binding) is not capture
                or capture.reader is not self.provider_reader or state[2] != threading.get_ident()):
            raise LeaseUnavailable('actual active combined provider lease required')
        super().check(binding, capture.calendar)
        state[1].check()
        return True
