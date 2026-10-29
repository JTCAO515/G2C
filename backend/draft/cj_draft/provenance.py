"""Host-owned provenance snapshots; model text never supplies source records.

Only an admitted host may call this builder, within the original MESSAGE/RUN
publication fence. PLACE observations are parsed adapter results acquired for
that same invocation, never client/model dictionaries or authorization tokens.
"""
from base64 import b64encode
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json

from cj_message.domain import Stored
from cj_place import FieldState, Outcome, Result
from cj_trip.domain import packed
from cj_run.core import Binding


CONTENT_VERSION = 'provenance.1'


@dataclass(frozen=True)
class SourceObservationBatch:
    """Host correlation for one original run, never an authorization token.

    The callback is trusted host code, not a client/model source upload. Current
    MESSAGE/RUN admission is checked again at publication; equality alone grants
    no access to a query or permission to publish.
    """
    binding: Binding
    results: tuple[Result, ...]


def _snapshot_value(value):
    if isinstance(value, datetime):
        return {'iso8601': value.isoformat(), 'fold': value.fold,
                'zone': getattr(value.tzinfo, 'key', None)}
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _snapshot_value(asdict(value))
    if isinstance(value, dict):
        return {key: _snapshot_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_snapshot_value(item) for item in value]
    return value


def _source(number, kind, reference, text, record, evidence):
    snapshot = packed({'display_text': text, 'record': _snapshot_value(record)})
    return {'id': f'source-{number}', 'kind': kind, 'reference': reference, 'text': text,
            'snapshot_utf8_base64': b64encode(snapshot).decode('ascii'),
            'snapshot_sha256': hashlib.sha256(snapshot).hexdigest(), 'evidence_level': evidence}


def build_document(legacy_document: bytes, message: Stored, place_results: tuple[Result, ...],
                   *, now: datetime, max_age_seconds: float | None):
    """Preserve generated text as unknown; attach exact admitted source displays.

    No free-text date parsing, fabricated NEEDS or provider truth declaration.
    An explicitly supplied unusable query result fails the whole new candidate;
    an absent query is genuinely absent and does not create a queried item.
    """
    document = json.loads(legacy_document)
    original = json.loads(message.raw)
    sources = [_source(1, 'message', message.receipt.message_id, original['text'],
                       {'receipt': asdict(message.receipt),
                        'original_utf8_base64': b64encode(message.raw).decode('ascii')}, 'user_statement')]
    for result in place_results:
        if max_age_seconds is None:
            raise ValueError('source freshness budget missing')
        source = result.source
        if result.outcome is not Outcome.OK or source is None:
            raise ValueError('query result unavailable')
        age = (now.astimezone(timezone.utc) - source.query_started_at.astimezone(timezone.utc)).total_seconds()
        if not 0 <= age <= max_age_seconds:
            raise ValueError('query observation stale')
        for place in result.places:
            # Original provider name only: no model summary is attributed to it.
            sources.append(_source(len(sources) + 1, 'place', source.request_ref, place.name_zh,
                                   {'source': source, 'query': result.query, 'place': place}, source.evidence))
        for route in result.routes:
            for field in ('distance', 'duration'):
                observation = getattr(route, field)
                if observation.state is FieldState.PRESENT:
                    quantity = observation.value
                    # Unit text is locale-neutral and retains the provider's raw number.
                    text = f'{quantity.raw} {quantity.unit}'
                    sources.append(_source(len(sources) + 1, 'route_estimate', source.request_ref, text,
                                           {'source': source, 'query': result.query, 'route': route,
                                            'field': field}, source.evidence))
    categories = {'message': 'user_provided', 'place': 'queried', 'route_estimate': 'estimated'}
    items = [{'id': f'source-item-{index}', 'text': source['text'], 'verification': 'pending',
              'evidence': [], 'source_category': categories[source['kind']], 'source_refs': [source['id']]}
             for index, source in enumerate(sources, 1)]
    items.extend({**item, 'source_category': 'unknown', 'source_refs': []} for item in document['items'])
    return packed({'content_version': CONTENT_VERSION, 'title': document['title'],
                   'items': items, 'sources': sources,
                   'decisions': {'travel_dates': 'unknown', 'prompt': 'decide_travel_dates'}})
