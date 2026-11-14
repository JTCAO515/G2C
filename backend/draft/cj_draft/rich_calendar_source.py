"""Additive native4 calendar/profile sources, before provider-source sealing.

This component is not a rich publisher. A complete Source4 publisher must also
capture and hold the actual eligible provider observations. In particular an
old calendar sidecar or a supplied profile dictionary cannot grant a rich save.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import threading

from cj_needs.revision_lease import LeaseUnavailable
from cj_trip.domain import identifier, packed
from cj_trip.structured import _date, _fields, _text

from .calendar_source import CalendarContextSource
from .lio_plan import LioContextSource

FIXED_BINDINGS = 'LIO-fixed-day-bindings.2'
CALENDAR_BASIS = 'TRIP-calendar-basis.2'
SOURCE = 'TRIP-RICH-CALENDAR-SOURCE.1'
_FACTORY = object()


def original_reference(value, *, current=False):
    """New reference grammar; the frozen calendar-v1 decoder is unchanged."""
    _fields(value, {'conversation_id', 'generation', 'message_id', 'run_id', 'sequence',
                   'input_sha256', 'message_version', 'lio_protocol'}, 'reference',
            'exact rich original reference required')
    for key in ('conversation_id', 'generation', 'message_id', 'run_id'):
        _text(value[key], 1024)
        if '\x00' in value[key]:
            raise ValueError('original reference cannot contain NUL')
    if type(value['sequence']) is not int or not 1 <= value['sequence'] <= 2**63-1:
        raise ValueError('explicit original sequence required')
    if type(value['input_sha256']) is not str or re.fullmatch('[0-9a-f]{64}', value['input_sha256']) is None:
        raise ValueError('canonical original MESSAGE digest required')
    if value['message_version'] not in ('MESSAGE-send.1', 'MESSAGE-send.2', 'MESSAGE-send.3', 'MESSAGE-send.4'):
        raise ValueError('canonical MESSAGE version required')
    protocols = ('LIO-message.4',) if current else ('LIO-message.1', 'LIO-message.2', 'LIO-message.3', 'LIO-message.4')
    if value['lio_protocol'] not in protocols:
        raise ValueError('actual native4 root and unchanged historical protocols required')


@dataclass(frozen=True, repr=False)
class RichCalendarBasis:
    day_count: int
    start_date: str | None
    fixed_bindings: bytes

    def __post_init__(self):
        if type(self.day_count) is not int or not 1 <= self.day_count <= 1_000_000 // 16:
            raise ValueError('day count must fit the content byte bound')
        if self.start_date is not None:
            _date(self.start_date)
        if type(self.fixed_bindings) is not bytes or not 0 < len(self.fixed_bindings) <= 1_000_000:
            raise ValueError('bounded original rich fixed bindings required')
        value = json.loads(self.fixed_bindings)
        _fields(value, {'version', 'needs_id', 'needs_version', 'needs_content_sha256', 'reference', 'bindings'},
                'fixed_bindings', 'exact rich fixed-day sidecar required')
        if value['version'] != FIXED_BINDINGS or packed(value) != self.fixed_bindings:
            raise ValueError('new canonical rich fixed binding version required')
        identifier(value['needs_id'])
        if type(value['needs_version']) is not int or not 1 <= value['needs_version'] <= 2**63-1:
            raise ValueError('positive original NEEDS version required')
        digest = value['needs_content_sha256']
        if type(digest) is not str or re.fullmatch('[0-9a-f]{64}', digest) is None:
            raise ValueError('canonical original NEEDS digest required')
        original_reference(value['reference'], current=True)
        if type(value['bindings']) is not list or len(value['bindings']) > 60:
            raise ValueError('bounded rich fixed-day bindings required')
        seen = set()
        for entry in value['bindings']:
            _fields(entry, {'item_id', 'day_index', 'end_day_index', 'quote', 'source_reference'},
                    'fixed_binding', 'original fixed item endpoints and quote required')
            identifier(entry['item_id'])
            if entry['item_id'] in seen:
                raise ValueError('duplicate rich fixed item mapping')
            seen.add(entry['item_id'])
            first, last = entry['day_index'], entry['end_day_index']
            if (type(first) is not int or type(last) is not int
                    or not 1 <= first <= last <= self.day_count):
                raise ValueError('ordered original fixed ordinals required')
            _text(entry['quote'], 12000)
            if len(entry['quote'].encode()) > 12000:
                raise ValueError('fixed quote exceeds original input bound')
            original_reference(entry['source_reference'])

    def metadata(self):
        return dict(version=CALENDAR_BASIS, day_count=self.day_count, start_date=self.start_date,
                    fixed_bindings=json.loads(self.fixed_bindings))

    def day_indices(self):
        return {entry['item_id']: (entry['day_index'], entry['end_day_index'])
                for entry in json.loads(self.fixed_bindings)['bindings']}


@dataclass(frozen=True, repr=False, init=False)
class RichCalendarCapture:
    binding: object
    needs: object
    basis: RichCalendarBasis
    profile: object
    reader: object
    profile_reader: object
    raw: bytes

    def __init__(self, binding, needs, basis, profile, reader, profile_reader, raw, *, _factory=None):
        if _factory is not _FACTORY:
            raise TypeError('issued rich calendar/profile source required')
        for key, value in (('binding', binding), ('needs', needs), ('basis', basis), ('profile', profile),
                           ('reader', reader), ('profile_reader', profile_reader), ('raw', raw)):
            object.__setattr__(self, key, value)

    def records(self):
        return self.needs.records()


class RichCalendarContextSource(CalendarContextSource):
    """Reuse actual M/NEEDS locks, with an explicit new calendar/profile reader.

    The L host supplies RichProfileSource and its actual accepted profile plus a
    calendar reader returning RichCalendarBasis. Capture and final publication
    both run in the existing worker Memory frame. No provider is invoked here.
    """
    def __init__(self, original, original_needs, calendar_reader, repository, *,
                 profile_reader, worker, expected_profile):
        super().__init__(original, original_needs, calendar_reader, repository)
        self.profile_reader = profile_reader
        self.worker = worker
        self.expected_profile = expected_profile

    def capture(self, binding):
        # Bypass only the old calendar-v1 codec, never the original M/NEEDS
        # capture. No native4 original is relabeled to pass the old codec.
        needs = LioContextSource.capture(self, binding)
        with self.message_context.hold_for_effect(binding) as message:
            basis = self.calendar_reader.capture(binding, message, needs)
            snapshot, _ = needs.records()
            sidecar = json.loads(basis.fixed_bindings)
            if ((sidecar['needs_id'], sidecar['needs_version'], sidecar['needs_content_sha256'])
                    != (snapshot.needs_id, snapshot.version, sha256(snapshot.content).hexdigest())):
                raise LeaseUnavailable('rich calendar differs from original NEEDS')
            expected = message.reference.public_value()
            root = sidecar['reference']
            if any(root[key] != expected[key] for key in ('conversation_id', 'generation', 'message_id',
                    'run_id', 'sequence', 'input_sha256', 'message_version')):
                raise LeaseUnavailable('rich calendar differs from original MESSAGE')
            if set(basis.day_indices()) != {item['item_id'] for item in snapshot.fields.get('fixed_items', ())}:
                raise LeaseUnavailable('rich calendar omits or invents a fixed item')
            profile = self.profile_reader.capture_for_plan(self.worker, binding, message,
                                                         expected_profile=self.expected_profile)
            original = profile.original
            if (original['protocol'], original['message_id'], original['run_id'], original['input_sha256']) != (
                    root['lio_protocol'], binding.message_id, binding.run_id, root['input_sha256']):
                raise LeaseUnavailable('rich calendar/profile original differs')
            value = json.loads(needs.raw)
            value.update(version=SOURCE, calendar_basis=basis.metadata(), planning_profile=dict(
                original=original, plan_now=profile.plan_now, policy=profile.policy,
                profile_states=profile.profile_states, profile=profile.profile))
            raw = packed(value)
            if len(raw) > self.max_bytes:
                raise LeaseUnavailable('rich calendar/profile source exceeds original bound')
            message.check(binding)
        capture = RichCalendarCapture(binding, needs, basis, profile, self.calendar_reader,
                                      self.profile_reader, raw, _factory=_FACTORY)
        self.calendar_captures[binding] = capture
        return capture

    @contextmanager
    def hold_additional_sources(self, binding, needs, message):
        capture = self.calendar_captures.get(binding)
        if (capture is None or capture.needs is not needs or capture.reader is not self.calendar_reader
                or capture.profile_reader is not self.profile_reader):
            raise LeaseUnavailable('issued rich calendar/profile capture unavailable')
        with capture.reader.hold(binding, capture.basis, message) as calendar, \
                capture.profile_reader.hold_for_plan(self.worker, binding, capture.profile, message) as profile:
            token = self.calendar_active.set((capture, calendar, threading.get_ident(), profile))
            try:
                calendar.check()
                profile.check()
                yield
            finally:
                self.calendar_active.reset(token)

    def check(self, binding, capture):
        if type(capture) is not RichCalendarCapture:
            return super().check(binding, capture)
        state = self.calendar_active.get()
        if (state is None or state[0] is not capture or self.calendar_captures.get(binding) is not capture
                or capture.reader is not self.calendar_reader or capture.profile_reader is not self.profile_reader
                or state[2] != threading.get_ident()):
            raise LeaseUnavailable('actual active rich calendar/profile lease required')
        LioContextSource.check(self, binding, capture.needs)
        state[1].check()
        state[3].check()
        self._check_originals(binding, capture, state[1])
        root = json.loads(capture.basis.fixed_bindings)['reference']
        if state[1].question_day(root).isoformat() != capture.profile.original['question_day']:
            raise LeaseUnavailable('rich calendar/profile original question clock differs')
        return True
