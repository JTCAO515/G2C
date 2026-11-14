"""Calendar compiler data backed by genuine current and historical MESSAGE leases."""
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json

from cj_draft.calendar_source import CalendarBasis
from cj_message.lio_wire import original_protocol
from cj_message.travel_reference import MessageContextAuthority
from cj_needs.domain import InvalidInput
from cj_needs.revision_lease import LeaseUnavailable
from cj_run.core import Binding
from cj_trip.domain import packed

from .lio_calendar_ordinals import fixed_ordinals


@dataclass(frozen=True)
class Original:
    binding: Binding
    stored: object
    reference: bytes
    question_day: date


class LioCalendarSource:
    """One worker compilation, not a public DTO or an independent save grant.

    day_count/start_date/date_quote have passed the original sourced intake
    compiler. Every source is reread through real scoped MESSAGE authority;
    publication reacquires all those leases before C acquires NEEDS.
    """
    sidecar_version='LIO-fixed-day-bindings.1'

    def _basis(self,day_count,start_date,sidecar):
        return CalendarBasis(day_count,start_date,sidecar)

    def _protocol(self,cursor,binding,stored):
        return original_protocol(cursor,binding,stored)

    def __init__(self, database, message_context, *, day_count, start_date, references,
                 date_quote=None, selection=None):
        self.database, self.message_context = database, message_context
        self.day_count, self.start_date = day_count, start_date
        self.references = references
        self.date_quote, self.selection = date_quote, selection
        self.originals = ()
        self.mappings = {}

    def _read(self, binding, mid):
        with self.database.connect(binding.scope) as connection:
            row = connection.execute(
                'SELECT run_id,sequence,input_sha256,demo_question_day FROM cj_message_receipt '
                'WHERE scope=%s AND conversation_id=%s AND generation=%s AND message_id=%s',
                (binding.scope, binding.conversation_id, binding.generation, mid)).fetchone()
        if row is None or row[3] is None:
            raise LeaseUnavailable('original calendar source unavailable')
        run_id, sequence, digest, question_day = row
        if sequence > binding.message_sequence:
            raise LeaseUnavailable('calendar source cannot refer to a future message')
        source = Binding(binding.scope, binding.conversation_id, binding.generation, mid, run_id, sequence)
        authority = MessageContextAuthority(self.database.message_repository(binding.scope), self.message_context.admit)
        with authority.hold_for_effect(source) as lease:
            stored = lease.original_message()
            if stored.receipt.input_sha256 != digest:
                raise LeaseUnavailable('original calendar source bytes differ')
            with self.database.connect(binding.scope) as connection:
                protocol = self._protocol(connection.cursor(), source, stored)
            reference = lease.reference.public_value()
            result = {key: reference[key] for key in ('conversation_id', 'generation', 'message_id',
                'run_id', 'sequence', 'input_sha256', 'message_version')}
            result['lio_protocol'] = protocol
        return Original(source, stored, packed(result), question_day)

    def capture(self, binding, message, needs):
        message.check(binding)
        snapshot, revisions = needs.records()
        references = list(self.references)
        for revision in revisions:
            command = json.loads(revision.original_input)
            source = command['source']['text']
            prefix = 'Original Lio sources '
            if not source.startswith(prefix):
                raise LeaseUnavailable('original Lio calendar lineage unavailable')
            references.extend(json.loads(source.removeprefix(prefix)))
        sources = {}
        for reference in references:
            source = sources.get(reference['message_id'])
            if source is None:source = self._read(binding, reference['message_id'])
            if (source.binding.conversation_id, source.binding.generation,
                    source.stored.receipt.input_sha256, source.binding.message_sequence) != (
                    reference['conversation_id'], reference['generation'],
                    reference['input_sha256'], reference['sequence']):
                raise LeaseUnavailable('compiled calendar source changed')
            sources[source.binding.message_id] = source
        current = self._read(binding, binding.message_id)
        if current.stored != message.original_message():
            raise LeaseUnavailable('calendar compiler original MESSAGE changed')
        sources[binding.message_id] = current
        self.originals = tuple(sources.values())
        entries = []
        mappings = {}
        for fixed in snapshot.fields.get('fixed_items', ()):
            quote = fixed['description']
            matches = [source for source in self.originals
                       if quote in json.loads(source.stored.raw)['text']]
            if len(matches) != 1:
                raise LeaseUnavailable('fixed day needs a unique original source')
            source = matches[0]
            try:pair = fixed_ordinals(quote, self.day_count)
            except InvalidInput:
                if self.start_date is None:
                    raise LeaseUnavailable('fixed arrangement has no original day mapping') from None
                indices=[]
                for edge in ('start','end'):
                    observed=fixed[edge]['date']
                    if observed['state']!='known' or observed['value'] not in quote:
                        raise LeaseUnavailable('fixed date mapping needs its original literal date') from None
                    indices.append((date.fromisoformat(observed['value'])-date.fromisoformat(self.start_date)).days+1)
                if not 1<=indices[0]<=indices[1]<=self.day_count:
                    raise LeaseUnavailable('fixed date lies outside original calendar') from None
                pair=tuple(indices)
            entry = dict(item_id=fixed['item_id'], day_index=pair[0], end_day_index=pair[1],
                         quote=quote, source_reference=json.loads(source.reference))
            entries.append(entry)
            mappings[(fixed['item_id'], source.reference, quote)] = pair
        self.mappings = mappings
        sidecar = packed(dict(version=self.sidecar_version, needs_id=snapshot.needs_id,
            needs_version=snapshot.version, needs_content_sha256=sha256(snapshot.content).hexdigest(),
            reference=json.loads(current.reference), bindings=entries))
        basis = self._basis(self.day_count, self.start_date, sidecar)
        self.basis = basis
        message.check(binding)
        return basis

    @contextmanager
    def hold(self, binding, basis, message):
        if basis is not self.basis:
            raise LeaseUnavailable('issued calendar compiler basis required')
        with ExitStack() as stack:
            leases = []
            for source in sorted(self.originals, key=lambda item: item.binding.message_sequence):
                if source.binding == binding:
                    lease = message
                else:
                    authority = MessageContextAuthority(self.database.message_repository(binding.scope),
                                                        self.message_context.admit)
                    lease = stack.enter_context(authority.hold_for_effect(source.binding))
                if lease.original_message() != source.stored:
                    raise LeaseUnavailable('captured calendar original changed')
                leases.append((source.binding, lease))
            held = HeldCalendar(self, tuple(leases))
            held.check()
            yield held
            held.check()


class HeldCalendar:
    def __init__(self, source, leases):
        self.source, self.leases = source, leases
        self.day_count, self.start_date = source.day_count, source.start_date

    def check(self):
        for binding, lease in self.leases:
            lease.check(binding)

    def _original(self, reference):
        key = packed(reference)
        for original in self.source.originals:
            if original.reference == key:
                return original
        raise LeaseUnavailable('calendar source was not captured and held')

    def original(self, reference):
        original = self._original(reference)
        return original.stored, json.loads(original.reference)['lio_protocol']

    def fixed_day_indices(self, item_id, reference, quote):
        return self.source.mappings[(item_id, packed(reference), quote)]

    def question_day(self, reference):
        return self._original(reference).question_day

    def compiled_date(self, reference, quote, question_day):
        original = self._original(reference)
        if (original.question_day != question_day or quote != self.source.date_quote
                or quote not in json.loads(original.stored.raw)['text'] or self.start_date is None):
            raise LeaseUnavailable('original compiled date source differs')
        return date.fromisoformat(self.start_date)

    def selected_item_ids(self, reference, request_bytes):
        self._original(reference)
        selection = self.source.selection
        if selection is None or selection.request.raw != request_bytes:
            raise LeaseUnavailable('original compiled item selection required')
        return selection.selected_ids


class LioDateEvidence:
    """This planning flow collects no date-specific weather/opening observations."""
    def read(self, binding, capture, document):
        return [dict(kind=kind, state='unknown', day_indices=[d['day_index'] for d in document['days']],
                     item_ids=[], reason='date_evidence_not_collected', evidence_refs=[])
                for kind in ('weather', 'day_opening')]
