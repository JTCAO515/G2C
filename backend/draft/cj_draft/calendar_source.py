"""Ordinal source data layered on the existing real MESSAGE/NEEDS leases.

The trusted L adapter supplies capture(binding,message,needs) and
hold(binding,basis,message), before NEEDS, reusing the issued MESSAGE lease.
Its held object must
expose original(reference)->(Stored, lio_protocol), fixed_day_indices(...),
day_count/start_date and check(). Data alone cannot create either active lease.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
import json
import threading

from cj_message.domain import Command
from cj_needs.revision_lease import LeaseUnavailable
from cj_trip.calendar_conversion import original_reference
from cj_trip.domain import identifier, packed
from cj_trip.structured import _date, _fields, _text
from .lio_plan import LioContextSource

_FACTORY = object()


@dataclass(frozen=True, repr=False)
class CalendarBasis:
    day_count: int
    start_date: str | None
    fixed_bindings: bytes

    def __post_init__(self):
        if type(self.day_count) is not int or not 1 <= self.day_count <= 1_000_000 // 16:
            raise ValueError('day count cannot exceed possible bounded content')
        if self.start_date is not None:
            _date(self.start_date)
        if type(self.fixed_bindings) is not bytes or not 0 < len(self.fixed_bindings) <= 1_000_000:
            raise ValueError('bounded original fixed binding bytes required')
        value = json.loads(self.fixed_bindings)
        _fields(value, {'version', 'needs_id', 'needs_version', 'needs_content_sha256', 'reference', 'bindings'},
                'fixed_bindings', 'exact fixed-day sidecar required')
        if value['version'] != 'LIO-fixed-day-bindings.1' or packed(value) != self.fixed_bindings:
            raise ValueError('canonical fixed-day sidecar required')
        identifier(value['needs_id'])
        if type(value['needs_version']) is not int or not 1 <= value['needs_version'] <= 2**63-1:
            raise ValueError('original NEEDS version required')
        original_reference(value['reference'])
        if type(value['bindings']) is not list or len(value['bindings']) > 60:
            raise ValueError('bounded fixed-day bindings required')
        seen = set()
        for binding in value['bindings']:
            _fields(binding, {'item_id', 'day_index', 'end_day_index', 'quote', 'source_reference'},
                    'fixed_binding', 'explicit endpoint ordinals and original source required')
            identifier(binding['item_id'])
            if binding['item_id'] in seen:
                raise ValueError('duplicate fixed mapping')
            seen.add(binding['item_id'])
            for name in ('day_index', 'end_day_index'):
                if type(binding[name]) is not int or not 1 <= binding[name] <= self.day_count:
                    raise ValueError('fixed ordinal outside original request')
            _text(binding['quote'], 12000)
            if len(binding['quote'].encode()) > 12000:
                raise ValueError('fixed quote exceeds original input bound')
            original_reference(binding['source_reference'])

    def metadata(self):
        return dict(version='TRIP-calendar-basis.1', day_count=self.day_count, start_date=self.start_date,
                    fixed_bindings=json.loads(self.fixed_bindings))

    def day_indices(self):
        value = json.loads(self.fixed_bindings)
        return {b['item_id']: (b['day_index'], b['end_day_index']) for b in value['bindings']}


@dataclass(frozen=True, repr=False, init=False)
class CalendarCapture:
    binding: object
    needs: object
    basis: CalendarBasis
    reader: object
    raw: bytes

    def __init__(self, binding, needs, basis, raw, *, reader=None, _factory=None):
        if _factory is not _FACTORY:
            raise TypeError('issued calendar source required')
        for name, value in (('binding', binding), ('needs', needs), ('basis', basis), ('reader', reader), ('raw', raw)):
            object.__setattr__(self, name, value)

    def records(self):
        return self.needs.records()


class CalendarContextSource(LioContextSource):
    def __init__(self, original, original_needs, calendar_reader, repository):
        super().__init__(original, original_needs)
        if calendar_reader is None:
            raise ValueError('original calendar source reader required')
        self.trip_repository = repository
        self.calendar_reader = calendar_reader
        self.calendar_captures = {}
        self.calendar_active = ContextVar('calendar_source_lease', default=None)

    def capture(self, binding):
        needs = super().capture(binding)
        reader = self.calendar_reader
        with self.message_context.hold_for_effect(binding) as message:
            basis = reader.capture(binding, message, needs)
            snapshot, _ = needs.records()
            sidecar = json.loads(basis.fixed_bindings)
            if ((sidecar['needs_id'], sidecar['needs_version'], sidecar['needs_content_sha256'])
                    != (snapshot.needs_id, snapshot.version, sha256(snapshot.content).hexdigest())):
                raise LeaseUnavailable('calendar source does not match original NEEDS')
            expected = message.reference.public_value()
            if any(sidecar['reference'][k] != expected[k] for k in (
                    'conversation_id', 'generation', 'message_id', 'run_id', 'sequence', 'input_sha256', 'message_version')):
                raise LeaseUnavailable('calendar source does not match original MESSAGE')
            if set(basis.day_indices()) != {i['item_id'] for i in snapshot.fields.get('fixed_items', ())}:
                raise LeaseUnavailable('calendar source omits or invents a fixed item')
            value = json.loads(needs.raw)
            value.update(version='TRIP-CALENDAR-SOURCE.1', calendar_basis=basis.metadata())
            raw = packed(value)
            if len(raw) > self.max_bytes:
                raise LeaseUnavailable('calendar source exceeds original byte bound')
        capture = CalendarCapture(binding, needs, basis, raw, reader=reader, _factory=_FACTORY)
        self.calendar_captures[binding] = capture
        return capture

    @staticmethod
    def _original(held, reference):
        stored, protocol = held.original(reference)
        command = Command.parse_original(stored.raw)
        receipt = stored.receipt
        actual = (receipt.conversation_id, receipt.generation, receipt.message_id, receipt.run_id, receipt.sequence,
                  sha256(stored.raw).hexdigest(), json.loads(command.raw)['version'], protocol)
        expected = tuple(reference[k] for k in ('conversation_id', 'generation', 'message_id', 'run_id', 'sequence',
                                               'input_sha256', 'message_version', 'lio_protocol'))
        if (actual != expected or receipt.input_sha256 != reference['input_sha256']
                or command.conversation_id != receipt.conversation_id or command.message_id != receipt.message_id
                or command.expected_generation is not None and command.expected_generation != receipt.generation
                or command.expected_sequence is not None and command.expected_sequence + 1 != receipt.sequence):
            raise LeaseUnavailable('calendar original MESSAGE bytes/receipt/protocol changed')
        return command

    def _check_originals(self, binding, capture, held):
        if held.day_count != capture.basis.day_count or held.start_date != capture.basis.start_date:
            raise LeaseUnavailable('protected compiled calendar changed')
        sidecar = json.loads(capture.basis.fixed_bindings)
        root = sidecar['reference']
        self._original(held, root)
        for entry in sidecar['bindings']:
            reference = entry['source_reference']
            if ((reference['conversation_id'], reference['generation']) != (binding.conversation_id, binding.generation)
                    or reference['sequence'] > root['sequence']):
                raise LeaseUnavailable('fixed source is foreign or from a future message')
            command = self._original(held, reference)
            if entry['quote'] not in json.loads(command.raw)['text']:
                raise LeaseUnavailable('fixed quote is absent from original source')
            if tuple(held.fixed_day_indices(entry['item_id'], reference, entry['quote'])) != (
                    entry['day_index'], entry['end_day_index']):
                raise LeaseUnavailable('ordinal is not the protected original compiler result')

    @contextmanager
    def hold_additional_sources(self, binding, needs, message):
        capture = self.calendar_captures.get(binding)
        if capture is None or capture.needs is not needs or self.calendar_reader is not capture.reader:
            raise LeaseUnavailable('issued calendar capture unavailable')
        with capture.reader.hold(binding, capture.basis, message) as held:
            token = self.calendar_active.set((capture, held, threading.get_ident()))
            try:
                held.check()
                yield
            finally:
                self.calendar_active.reset(token)

    @contextmanager
    def hold_for_publication(self, binding):
        capture = self.calendar_captures.get(binding)
        if capture is None:
            raise LeaseUnavailable('issued calendar capture unavailable')
        with super().hold_for_publication(binding):
            self.check(binding, capture)
            yield lambda: self.check(binding, capture)
            self.check(binding, capture)

    def check(self, binding, capture):
        if type(capture) is not CalendarCapture:
            return super().check(binding, capture)  # Original base lease's own enter/exit checks.
        state = self.calendar_active.get()
        if (state is None or state[0] is not capture or self.calendar_captures.get(binding) is not capture
                or self.calendar_reader is not capture.reader or state[2] != threading.get_ident()):
            raise LeaseUnavailable('actual active calendar source lease required')
        super().check(binding, capture.needs)
        state[1].check()
        self._check_originals(binding, capture, state[1])
        return True
