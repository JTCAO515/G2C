"""Explicit calendar undo with actual historical MESSAGE and current NEEDS leases."""
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json

from cj_api.local_app import scope_for
from cj_message.travel_reference import MessageContextAuthority
from cj_run.core import Binding
from .domain import Conflict, Denied, packed
from .lio_history import Undo, _append_undo, _current_for_undo, _revision
from .needs_action_store import NeedsActions
from .needs_lineage import current_origin


@dataclass(frozen=True, repr=False)
class CalendarUndo:
    raw: bytes
    action_id: str
    trip_id: str
    expected_version: int
    original_hash: str

    @classmethod
    def parse(cls, raw):
        if type(raw) is not bytes or not 0 < len(raw) <= 1024:
            raise ValueError('bounded original calendar undo required')
        value = json.loads(raw)
        if type(value) is not dict or value.get('version') != 'TRIP-lio-undo.2' or packed(value) != raw:
            raise ValueError('canonical calendar undo version required')
        old = Undo.parse(packed(dict(value, version='TRIP-lio-undo.1')))
        return cls(raw, old.action_id, old.trip_id, old.expected_version, old.original_hash)


def protect_fixed(current, previous):
    before, after = json.loads(current.content), json.loads(previous.content)
    if before['content_version'] != 'structured.3' or after['content_version'] != 'structured.3':
        raise Denied('calendar undo requires explicit calendar history')
    items = {i['id']: i for i in after['items']}
    sources = {s['id']: s for s in after['sources']}
    old_sources = {s['id']: s for s in before['sources']}
    for item in before['items']:
        if item['fixed'] == {'state': 'known', 'value': True}:
            if items.get(item['id']) != item or any(sources.get(r) != old_sources[r] for r in item['source_refs']):
                raise Conflict('calendar undo would change a fixed item/source')


@contextmanager
def history_sources(source, *origins):
    """Acquire genuine B M/T source leases before the current NEEDS lease."""
    principal = source.admit()
    owner = scope_for(principal.issuer, principal.subject)
    references = {}
    for origin in origins:
        raw = json.loads(origin['source'])
        if raw['version'] != 'TRIP-CALENDAR-SOURCE.1':
            raise Denied('retained calendar source unavailable')
        root = raw['reference']
        refs = [root] + [b['source_reference'] for b in raw['calendar_basis']['fixed_bindings']['bindings']]
        for reference in refs:
            identity = tuple(reference[k] for k in ('conversation_id', 'generation', 'message_id', 'run_id', 'sequence'))
            digest = reference['input_sha256']
            if identity in references and references[identity]['input_sha256'] != digest:
                raise Denied('retained source identity has inconsistent bytes')
            references[identity] = reference
    with ExitStack() as stack:
        checks = []
        for identity, reference in sorted(references.items()):
            authority = MessageContextAuthority(source.database.message_repository(owner), source.admit)
            binding = Binding(owner, *identity)
            lease = stack.enter_context(authority.hold_for_effect(binding))
            actual = lease.reference.public_value()
            for key in ('conversation_id', 'generation', 'message_id', 'run_id', 'sequence', 'input_sha256', 'message_version'):
                if actual[key] != reference[key]:
                    raise Denied('retained calendar original changed')
            if sha256(lease.original_message().raw).hexdigest() != reference['input_sha256']:
                raise Denied('retained calendar original bytes changed')
            checks.append((lease, binding))

        def check():
            if source.admit() != principal:
                raise Denied('calendar undo source principal changed')
            for lease, binding in checks:
                lease.check(binding)

        check()
        yield check
        check()


def undo(repository, request):
    if not repository.calendar or repository.needs_edits is None:
        raise Denied('explicit current-source calendar undo host required')
    source = repository.needs_edits.source
    with repository.transaction() as cursor:
        receipt = NeedsActions._previous(repository, cursor, request)
        if receipt is not None:
            return receipt
        current = _current_for_undo(repository, cursor, request)
        previous = _revision(repository, cursor, request.trip_id, current.version-1)
        protect_fixed(current, previous)
        active = current_origin(cursor, repository, current)
        prior = current_origin(cursor, repository, previous)
    captured = source.capture(active['needs_id'], active['needs_version'])
    committed = False
    try:
        with history_sources(source, active, prior) as check_history, source.hold(captured) as check_needs:
            def check():
                check_history()
                check_needs()

            receipt = _append_undo(repository, request, active, captured, check,
                protect_fixed=protect_fixed, basis_version='lio-calendar-undo.1')
            committed = True
            return receipt
    except BaseException as error:
        if committed:
            error.commit_possible = True
        raise
