"""Model text -> validated, immutable TRIP proposal (P2b, CJ-014 minimal).

Model output is untrusted: it must parse as one strict JSON object, every item is
stored as `pending` with no evidence (nothing the model says counts as verified),
and the canonical bytes are re-validated by cj_trip.domain.Proposal before the
trusted publish ingress. The client never sends proposal content.
"""
from dataclasses import dataclass
import hashlib
import json
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


def document_from_model(text):
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end < start:
        raise DraftRejected('no JSON object')
    try:
        value = json.loads(text[start:end + 1])
    except ValueError:
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
    return packed({'title': title.strip(), 'items': [
        {'id': f'item-{n}', 'text': item.strip(), 'verification': 'pending', 'evidence': []}
        for n, item in enumerate(items, 1)]})


@dataclass(frozen=True)
class Draft:
    proposal_id: str
    trip_id: str
    candidate_hash: str


class DraftPublisher:
    """Host-side ingress; `repository` is cj_trip.postgres.Repository bound to the TRIP scope."""

    def __init__(self, repository, clock=time.time):
        self.repository, self.clock = repository, clock

    def publish(self, run_id, model_text):
        content = document_from_model(model_text)
        try:
            proposal = Proposal(proposal_id_for(run_id), 'trip-' + run_id, 0, 'run-' + run_id,
                                int(self.clock()) + PROPOSAL_TTL_SECONDS, content)
        except ValueError:
            raise DraftRejected('proposal validation failed') from None
        return Draft(proposal.proposal_id, proposal.trip_id, self.repository.publish(proposal))
