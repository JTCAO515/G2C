"""Rich history/undo reuses original source leases, signatures and sole writer.

The host must bind a genuine current Memory/profile holder for rich undo. A
stored plan marker or a source DTO cannot supply that authority. No HTTP host is
enabled here; absent current holders fail closed. Legacy handlers are unchanged.
"""
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
import threading
from typing import Callable

from cj_auth.interfaces import TrustedPrincipal
from cj_message.lio_wire import exploration_original_protocol, original_protocol
from cj_message.travel_reference import MessageContextAuthority
from cj_run.core import Binding
from .domain import Conflict, Denied, packed
from .lio_history import _append_undo, _current_for_undo, _message_receipt, _revision, plan_action_id
from .needs_action_store import NeedsActions
from .needs_lineage import current_origin
from .structured_v4 import calendar_validation_view
from .place_selection import PLAN_SOURCE as SELECTION_PLAN_SOURCE, validate_basis as validate_selection_basis

PLAN_BASIS = 'lio-rich-plan.1'
UNDO_BASIS = 'lio-rich-undo.1'
_HISTORY_FACTORY = object()


@dataclass(frozen=True, repr=False, init=False)
class HeldHistory:
    """Actual historical M/T frame; copied handles share the same expiry check.

    The trusted host passes this to its current Memory/profile holder. It is
    never built from a public history projection, client principal or epoch.
    check() throws on withdrawal/expiry; it does not grant a Trip write.
    """
    principal: TrustedPrincipal
    scope: str
    _check: Callable[[], None]

    def __init__(self, principal, scope, check, *, _factory=None):
        if _factory is not _HISTORY_FACTORY:
            raise Denied('issued historical MESSAGE context required')
        object.__setattr__(self, 'principal', principal)
        object.__setattr__(self, 'scope', scope)
        object.__setattr__(self, '_check', check)

    def check(self): self._check()


def plan_receipt(repository, binding):
    if not repository.rich:
        raise Denied('explicit rich receipt consumer required')
    return _message_receipt(repository, binding, plan_action_id(binding.run_id), PLAN_BASIS,
                            content_version='structured.4')


def protect_fixed(current, previous):
    before, after = json.loads(current.content), json.loads(previous.content)
    versions = (before['content_version'], after['content_version'])
    if any(version not in ('structured.3', 'structured.4') for version in versions):
        raise Denied('explicit legacy calendar bridge required for rich undo')
    if versions[0] != versions[1]:
        before = calendar_validation_view(before) if versions[0] == 'structured.4' else before
        after = calendar_validation_view(after) if versions[1] == 'structured.4' else after
    items = {item['id']: item for item in after['items']}
    old_sources = {row['id']: row for row in before['sources']}
    new_sources = {row['id']: row for row in after['sources']}
    for item in before['items']:
        if item['fixed'] == {'state': 'known', 'value': True}:
            if items.get(item['id']) != item or any(new_sources.get(ref) != old_sources[ref] for ref in item['source_refs']):
                raise Conflict('rich undo would change an original fixed item/source')


@contextmanager
def history_sources(source, *origins):
    """Historical M/T before current Memory/profile, NEEDS and Trip locks."""
    from cj_api.local_app import scope_for
    principal = source.admit()
    owner = scope_for(principal.issuer, principal.subject)
    references = {}
    profiles = []
    for origin in origins:
        if len(origin['source']) > 4_000_000:
            raise Denied('historical source exceeds the existing byte bound')
        raw = json.loads(origin['source'])
        if raw['version'] in ('TRIP-RICH-PLAN-SOURCE.1', SELECTION_PLAN_SOURCE):
            if raw['version'] == SELECTION_PLAN_SOURCE:
                try:
                    validate_selection_basis(raw)
                except (ValueError, KeyError) as error:
                    raise Denied('historical original place selection differs') from error
            sidecar = raw['calendar_basis']['fixed_bindings']
            root = sidecar['reference']
            original = raw['planning_profile']['original']
            if (root['lio_protocol'] != 'LIO-message.4'
                    or (original['protocol'], original['message_id'], original['run_id'], original['input_sha256']) !=
                       ('LIO-message.4', root['message_id'], root['run_id'], root['input_sha256'])
                    or packed(raw['rich_source']['original']) != packed(original)):
                raise Denied('original rich source binding differs')
            profiles.append((tuple(root[k] for k in ('conversation_id', 'generation', 'message_id', 'run_id', 'sequence')),
                             raw['planning_profile']['profile']))
        elif raw['version'] == 'TRIP-CALENDAR-SOURCE.1':
            sidecar = raw['calendar_basis']['fixed_bindings']
            root = raw['reference']
        else:
            raise Denied('explicit retained rich/calendar source required')
        if (origin['message_scope'] != owner or
                (sidecar['needs_id'], sidecar['needs_version']) != (origin['needs_id'], origin['needs_version'])):
            raise Denied('historical source owner or NEEDS version differs')
        for reference in [root, *(row['source_reference'] for row in sidecar['bindings'])]:
            identity = tuple(reference[k] for k in ('conversation_id', 'generation', 'message_id', 'run_id', 'sequence'))
            required = ('conversation_id', 'generation', 'message_id', 'run_id', 'sequence', 'input_sha256', 'message_version')
            previous = references.get(identity)
            if previous is not None and (any(previous[k] != reference[k] for k in required)
                    or previous.get('lio_protocol') is not None and reference.get('lio_protocol') is not None
                    and previous['lio_protocol'] != reference['lio_protocol']):
                raise Denied('inconsistent historical original source')
            if previous is None or reference.get('lio_protocol') is not None:
                references[identity] = reference
    with ExitStack() as stack:
        active = True
        thread = threading.get_ident()
        held = []
        leases = {}
        for identity, reference in sorted(references.items()):
            authority = MessageContextAuthority(source.database.message_repository(owner), source.admit)
            binding = Binding(owner, *identity)
            lease = stack.enter_context(authority.hold_for_effect(binding))
            actual, stored = lease.reference.public_value(), lease.original_message()
            if any(actual[k] != reference[k] for k in ('conversation_id', 'generation', 'message_id',
                    'run_id', 'sequence', 'input_sha256', 'message_version')) or sha256(stored.raw).hexdigest() != reference['input_sha256']:
                raise Denied('historical rich original differs')
            protocol = reference.get('lio_protocol')
            if protocol is not None:
                with source.database.connect(owner) as db:
                    read = exploration_original_protocol if protocol == 'LIO-message.4' else original_protocol
                    if read(db.cursor(), binding, stored) != protocol:
                        raise Denied('historical outer wire protocol differs')
            held.append((lease, binding))
            leases[identity] = lease
        # Protected user-factor quotes/default anchors may precede the fixed
        # items. Validate them in the already-held native MESSAGE2 transaction;
        # a historical profile/Trip projection is not a replacement original.
        for root, profile in profiles:
            message = leases[root]
            for factor in profile['factors']:
                for anchor in factor['sources']:
                    if anchor['kind'] not in ('message', 'default'):
                        continue  # Current Memory eligibility is held separately.
                    actual = message.source_original(anchor['message_id'])
                    text = json.loads(actual.stored.raw)['text']
                    if anchor['kind'] == 'message':
                        if (actual.stored.receipt.sequence != anchor['sequence'] or
                                text[anchor['offset']:anchor['offset']+len(anchor['quote'])] != anchor['quote']):
                            raise Denied('historical profile quote original differs')
                    elif text.strip().casefold() not in ('直接出方案', 'plan now'):
                        raise Denied('historical code default has no actual plan trigger')
        def check():
            if not active or threading.get_ident() != thread or source.admit() != principal:
                raise Denied('rich history source principal changed')
            for lease, binding in held: lease.check(binding)
        check()
        context = HeldHistory(principal, owner, check, _factory=_HISTORY_FACTORY)
        try:
            yield context
            check()
        finally:
            active = False


def undo_receipt(repository, request):
    if not repository.rich:
        raise Denied('explicit rich receipt consumer required')
    with repository.transaction() as cursor:
        return NeedsActions._previous(repository, cursor, request)


def undo(repository, request):
    if not repository.rich or repository.needs_edits is None:
        raise Denied('explicit current-source rich undo host required')
    with repository.transaction() as cursor:
        previous_receipt = NeedsActions._previous(repository, cursor, request)
        if previous_receipt is not None: return previous_receipt
        current = _current_for_undo(repository, cursor, request)
        if json.loads(current.content)['content_version'] != request.content_version:
            raise Conflict('undo target content version differs')
        previous = _revision(repository, cursor, request.trip_id, current.version-1)
        active = current_origin(cursor, repository, current)
        prior = current_origin(cursor, repository, previous)
    # Old formats retain their existing source and permission requirements.
    if request.content_version in ('structured.1', 'structured.2'):
        from .lio_history import undo as legacy_undo
        return legacy_undo(repository, request)
    if request.content_version == 'structured.3' and all(
            json.loads(origin['source'])['version'] == 'TRIP-CALENDAR-SOURCE.1' for origin in (active, prior)):
        from .calendar_history import undo as calendar_undo
        return calendar_undo(repository, request)
    extra = repository.rich_undo_sources
    if extra is None:
        raise Denied('actual current Memory/profile undo holder required')
    protect_fixed(current, previous)
    source = repository.needs_edits.source
    captured = source.capture(active['needs_id'], active['needs_version'])
    committed = False
    try:
        with history_sources(source, active, prior) as message_context, \
                extra.hold(request, current=current, previous=previous, active_origin=active,
                           previous_origin=prior, message_context=message_context) as check_extra, \
                source.hold(captured) as check_needs:
            def check():
                if repository.rich_undo_sources is not extra:
                    raise Denied('rich undo current holder changed')
                message_context.check()
                check_extra()
                check_needs()
            receipt = _append_undo(repository, request, active, captured, check,
                                   protect_fixed=protect_fixed, basis_version=UNDO_BASIS)
            committed = True
            return receipt
    except BaseException as error:
        if committed: error.commit_possible = True
        raise
