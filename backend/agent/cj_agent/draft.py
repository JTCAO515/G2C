"""Model text -> validated, immutable TRIP proposal (P2b, CJ-014 minimal).

Model output is untrusted: it must parse as one strict JSON object, every item is
stored as `pending` with no evidence (nothing the model says counts as verified),
and the canonical bytes are re-validated by cj_trip.domain.Proposal before the
trusted publish ingress. The client never sends proposal content.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import os
from datetime import datetime, timezone
import time

from cj_trip.domain import Proposal, packed

DRAFT_SYSTEM = (
    'You draft a Beijing itinerary for a foreign visitor. Reply with ONLY one JSON object, '
    'no prose, no code fence: {"title": string, "items": [string, ...]}. Use the language of '
    'the user. 3 to 12 items, each one concrete step such as "Day 1 morning: Forbidden City". '
    'Do not state opening hours, prices or tickets as facts.')
MAX_TITLE = 120
MAX_ITEM = 500
MAX_ITEMS = 20
PROPOSAL_TTL_SECONDS = 7 * 24 * 3600


class DraftRejected(ValueError):
    """Model output did not form a valid draft; nothing is published."""


def proposal_id_for(run_id):
    return 'p-' + run_id


def trip_scope_for(message_scope):
    # TRIP identifiers are restricted; derive a stable opaque scope from the server scope.
    return 't' + hashlib.sha256(message_scope.encode('utf-8')).hexdigest()[:40]


def _model_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise DraftRejected('duplicate JSON field')
        value[key] = item
    return value


def document_from_model(text):
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end < start:
        raise DraftRejected('no JSON object')
    try:
        value = json.loads(text[start:end + 1], object_pairs_hook=_model_object)
    except (ValueError, RecursionError):
        raise DraftRejected('invalid JSON') from None
    if type(value) is not dict or set(value) != {'title', 'items'}:
        raise DraftRejected('title and items required')
    title, items = value['title'], value['items']
    if type(title) is not str or not title.strip() or len(title) > MAX_TITLE:
        raise DraftRejected('invalid title')
    if type(items) is not list or not 1 <= len(items) <= MAX_ITEMS:
        raise DraftRejected('invalid item count')
    if any(type(item) is not str or not item.strip() or len(item) > MAX_ITEM for item in items):
        raise DraftRejected('invalid item')
    try:
        return packed({'title': title.strip(), 'items': [
            {'id': f'item-{n}', 'text': item.strip(), 'verification': 'pending', 'evidence': []}
            for n, item in enumerate(items, 1)]})
    except UnicodeError:
        raise DraftRejected('invalid Unicode') from None


@dataclass(frozen=True)
class Draft:
    proposal_id: str
    trip_id: str
    candidate_hash: str


class DraftPublisher:
    """Host-side ingress; `repository` is cj_trip.postgres.Repository bound to the TRIP scope."""

    def __init__(self, repository, clock=time.time, *, content_version=None,
                 source_reader=None, max_source_age_seconds=None):
        # Explicit local opt-in; absent configuration preserves every legacy host.
        version = content_version if content_version is not None else os.environ.get('CJ_DRAFT_CONTENT_VERSION', 'legacy')
        if version not in ('legacy', 'provenance.1'):
            raise ValueError('unsupported draft content version')
        if version == 'provenance.1' and os.environ.get('CJ_ENV') != 'local':
            raise ValueError('provenance draft activation requires local environment')
        if source_reader is not None and (version != 'provenance.1'
                or type(max_source_age_seconds) not in (int, float)
                or not math.isfinite(max_source_age_seconds) or max_source_age_seconds <= 0):
            raise ValueError('explicit source freshness budget required')
        self.repository, self.clock = repository, clock
        self.content_version, self.source_reader = version, source_reader
        self.max_source_age_seconds = max_source_age_seconds

    def sources_for(self, binding):
        # This callback belongs to the trusted host. There is no HTTP/model source
        # upload path. The worker reacquires its publication fence afterwards.
        from cj_draft.provenance import SourceObservationBatch
        return SourceObservationBatch(binding, ()) if self.source_reader is None else self.source_reader(binding)

    def publish_for_message(self, binding, original, current, model_text, observations, *, before_publish=None):
        from cj_draft.provenance import build_document
        if (self.content_version != 'provenance.1' or observations.binding != binding
                or current is None or current != original
                or (current.receipt.message_id, current.receipt.conversation_id,
                    current.receipt.generation, current.receipt.sequence, current.receipt.run_id)
                != (binding.message_id, binding.conversation_id, binding.generation,
                    binding.message_sequence, binding.run_id)
                or self.repository.scope != trip_scope_for(binding.scope)):
            raise DraftRejected('source binding changed or unavailable')
        content = document_from_model(model_text)
        now = self.clock()
        try:
            content = build_document(content, current, observations.results,
                                     now=datetime.fromtimestamp(now, timezone.utc),
                                     max_age_seconds=self.max_source_age_seconds)
            proposal = Proposal(proposal_id_for(binding.run_id), 'trip-' + binding.run_id, 0,
                                'run-' + binding.run_id, int(now) + PROPOSAL_TTL_SECONDS, content)
        except ValueError:
            raise DraftRejected('source document rejected') from None
        if before_publish is not None:
            before_publish()
        return Draft(proposal.proposal_id, proposal.trip_id, self.repository.publish(proposal))

    def publish(self, run_id, model_text, *, before_publish=None):
        if self.content_version != 'legacy':
            raise DraftRejected('provenance publication requires admitted original message')
        content = document_from_model(model_text)
        try:
            proposal = Proposal(proposal_id_for(run_id), 'trip-' + run_id, 0, 'run-' + run_id,
                                int(self.clock()) + PROPOSAL_TTL_SECONDS, content)
        except ValueError:
            raise DraftRejected('proposal validation failed') from None
        if before_publish is not None:
            before_publish()
        return Draft(proposal.proposal_id, proposal.trip_id, self.repository.publish(proposal))
