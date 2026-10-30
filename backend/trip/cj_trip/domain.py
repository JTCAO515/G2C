"""Internal TRIP candidate v0.1; no HTTP schema or caller authorization."""
from dataclasses import dataclass
import base64
import hashlib
import json
import re

class Conflict(Exception): pass
class Denied(Exception): pass
class CommitUnknown(Exception): pass


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value):
        raise ValueError('invalid identifier')
    return value


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def validate_source_records(records):
    if type(records) is not list or len(records) > 40:
        raise ValueError('invalid sources')
    sources = {}
    for source in records:
        if (type(source) is not dict or set(source) != {
                'id', 'kind', 'reference', 'text', 'snapshot_utf8_base64',
                'snapshot_sha256', 'evidence_level'}):
            raise ValueError('invalid source shape')
        identifier(source['id'])
        if source['id'] in sources:
            raise ValueError('duplicate source')
        if (source['kind'] not in ('message', 'place', 'route_estimate')
                or type(source['reference']) is not str or not source['reference']
                or type(source['text']) is not str or not source['text'].strip()
                or source['evidence_level'] not in ('user_statement', 'synthetic', 'unverified_bytes')):
            raise ValueError('invalid source metadata')
        if (source['kind'] == 'message') != (source['evidence_level'] == 'user_statement'):
            raise ValueError('source evidence mismatch')
        try:
            raw = base64.b64decode(source['snapshot_utf8_base64'], validate=True)
            if not raw or base64.b64encode(raw).decode('ascii') != source['snapshot_utf8_base64']:
                raise ValueError('canonical snapshot encoding required')
            snapshot = json.loads(raw.decode('utf-8'))
            if type(snapshot) is not dict or packed(snapshot) != raw:
                raise ValueError('canonical snapshot required')
        except (TypeError, UnicodeError, ValueError, RecursionError) as error:
            raise ValueError('invalid source snapshot') from error
        if hashlib.sha256(raw).hexdigest() != source['snapshot_sha256']:
            raise ValueError('source snapshot digest mismatch')
        # The displayed source is bound to the persisted snapshot, not a separate
        # model-authored claim. Host acquisition still must prove its provenance.
        if set(snapshot) != {'display_text', 'record'} or snapshot['display_text'] != source['text']:
            raise ValueError('source display mismatch')
        record = snapshot['record']
        if type(record) is not dict:
            raise ValueError('source record required')
        try:
            if source['kind'] == 'message':
                from cj_message.domain import Command
                if set(record) != {'receipt', 'original_utf8_base64'}:
                    raise ValueError('message source record')
                original = base64.b64decode(record['original_utf8_base64'], validate=True)
                command = Command.parse_stored(original)
                value = json.loads(command.raw)
                receipt = record['receipt']
                if (set(receipt) != {'message_id', 'conversation_id', 'generation', 'sequence', 'run_id', 'input_sha256'}
                        or receipt['input_sha256'] != hashlib.sha256(original).hexdigest()
                        or receipt['message_id'] != command.message_id
                        or receipt['conversation_id'] != command.conversation_id
                        or source['reference'] != command.message_id or source['text'] != value['text']):
                    raise ValueError('message source mismatch')
            else:
                original_source = record['source']
                if (source['reference'] != original_source['request_ref']
                        or source['evidence_level'] != original_source['evidence']):
                    raise ValueError('query source mismatch')
                if source['kind'] == 'place':
                    if set(record) != {'source', 'query', 'place'} or record['place']['name_zh'] != source['text']:
                        raise ValueError('queried field mismatch')
                else:
                    field = record['field']
                    if set(record) != {'source', 'query', 'route', 'field'} or field not in ('duration', 'distance'):
                        raise ValueError('estimated field required')
                    observed = record['route'][field]
                    quantity = observed['value']
                    if (observed['state'] != 'present'
                            or quantity['unit'] != {'duration': 's', 'distance': 'm'}[field]
                            or source['text'] != quantity['raw'] + ' ' + quantity['unit']
                            or record['route']['time_semantics'] != 'provider_estimate_at_query_time'
                            or record['route']['future_guaranteed'] is not False):
                        raise ValueError('estimate semantics mismatch')
        except (KeyError, TypeError, UnicodeError, ValueError) as error:
            raise ValueError('invalid source record binding') from error
        sources[source['id']] = source
    return sources


def validate_provenance_document(doc):
    """Structural validation of the independently versioned source document.

    This does not authenticate source records or verify their factual truth.
    The trusted publisher owns source acquisition; the model cannot supply these
    objects. Original V1 grammar and original content hashes remain unchanged.
    """
    if (type(doc) is not dict
            or set(doc) != {'content_version', 'title', 'items', 'sources', 'decisions'}
            or doc['content_version'] != 'provenance.1'
            or type(doc['title']) is not str or not doc['title'].strip()):
        raise ValueError('invalid provenance document')
    if doc['decisions'] not in (
            {'travel_dates': 'unknown', 'prompt': 'decide_travel_dates'},
            {'travel_dates': 'undecided', 'prompt': 'decide_travel_dates'}):
        raise ValueError('explicit pending date decision required')
    sources = validate_source_records(doc['sources'])
    if type(doc['items']) is not list or not 1 <= len(doc['items']) <= 60:
        raise ValueError('invalid item count')
    seen, used = set(), set()
    for item in doc['items']:
        if (type(item) is not dict or set(item) != {
                'id', 'text', 'verification', 'evidence', 'source_category', 'source_refs'}):
            raise ValueError('invalid provenance item')
        identifier(item['id'])
        if item['id'] in seen:
            raise ValueError('duplicate item')
        seen.add(item['id'])
        if type(item['text']) is not str or not item['text'].strip():
            raise ValueError('empty text')
        if item['verification'] != 'pending' or item['evidence'] != []:
            raise ValueError('source association is not verification')
        category, refs = item['source_category'], item['source_refs']
        if category == 'unknown':
            if refs != []:
                raise ValueError('unknown item cannot borrow sources')
        elif category in ('user_provided', 'queried', 'estimated'):
            if type(refs) is not list or len(refs) != 1 or type(refs[0]) is not str or refs[0] not in sources:
                raise ValueError('one recorded source required')
            source = sources[refs[0]]
            expected = {'user_provided': 'message', 'queried': 'place', 'estimated': 'route_estimate'}[category]
            if source['kind'] != expected or item['text'] != source['text']:
                raise ValueError('item must display its actual source field')
            used.add(refs[0])
        else:
            raise ValueError('invalid source category')
    if used != set(sources):
        raise ValueError('unreferenced source')


def validate_legacy_document(doc):
    if set(doc) != {'title', 'items'} or not isinstance(doc['title'], str) or not doc['title'].strip():
        raise ValueError('title and items required')
    if not isinstance(doc['items'], list) or not doc['items']:
        raise ValueError('empty trip rejected')
    seen = set()
    for item in doc['items']:
        if not isinstance(item, dict) or set(item) != {'id', 'text', 'verification', 'evidence'}:
            raise ValueError('explicit fact state required')
        identifier(item['id'])
        if item['id'] in seen: raise ValueError('duplicate item')
        seen.add(item['id'])
        if not isinstance(item['text'], str) or not item['text'].strip(): raise ValueError('empty text')
        if item['verification'] not in ('pending', 'verified'): raise ValueError('unknown fact state')
        if not isinstance(item['evidence'], list) or not all(isinstance(x, str) and x for x in item['evidence']): raise ValueError('invalid evidence')
        if item['verification'] == 'verified' and not item['evidence']: raise ValueError('verified needs evidence')


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    trip_id: str
    expected_version: int
    basis_version: str
    expires_at: int
    content: bytes

    def __post_init__(self):
        for v in (self.proposal_id, self.trip_id, self.basis_version): identifier(v)
        if type(self.expected_version) is not int or self.expected_version < 0:
            raise ValueError('expected version required; zero means new trip')
        if type(self.expires_at) is not int or self.expires_at <= 0:
            raise ValueError('expiry required')
        if type(self.content) is not bytes or not 0 < len(self.content) <= 1_000_000:
            raise ValueError('immutable UTF-8 content required')
        # Minimal internal document, not the future PLACE/FACT or wire schema.
        doc = json.loads(self.content)
        if type(doc) is dict and doc.get('content_version') == 'structured.2':
            from .structured_v2 import validate_document
            validate_document(doc)
            if packed(doc) != self.content: raise ValueError('canonical content required')
            return
        if type(doc) is dict and doc.get('content_version') == 'structured.1':
            from .structured import validate_document
            validate_document(doc)
            if packed(doc) != self.content: raise ValueError('canonical content required')
            return
        if type(doc) is dict and doc.get('content_version') == 'provenance.1':
            validate_provenance_document(doc)
            if packed(doc) != self.content: raise ValueError('canonical content required')
            return
        validate_legacy_document(doc)
        # Reject duplicate JSON keys / alternate encodings: preserve accepted original bytes.
        if packed(doc) != self.content: raise ValueError('canonical content required')

    def digest(self, scope):
        return hashlib.sha256(packed([scope, self.proposal_id, self.trip_id, self.expected_version,
                                     self.basis_version, self.expires_at, self.content.decode('utf-8')])).hexdigest()


@dataclass(frozen=True)
class Action:
    action_id: str
    kind: str
    proposal_id: str
    candidate_hash: str
    confirmation_ref: str

    def __post_init__(self):
        for v in (self.action_id, self.proposal_id, self.confirmation_ref): identifier(v)
        if self.kind not in ('accept', 'reject'): raise ValueError('invalid action')
        if not isinstance(self.candidate_hash, str) or not re.fullmatch('[0-9a-f]{64}', self.candidate_hash): raise ValueError('hash required')

    def raw(self): return packed([self.action_id, self.kind, self.proposal_id, self.candidate_hash, self.confirmation_ref])


@dataclass(frozen=True)
class Receipt:
    action_id: str
    kind: str
    proposal_id: str
    candidate_hash: str
    trip_id: str
    committed_version: int | None


@dataclass(frozen=True)
class Trip:
    trip_id: str
    version: int
    content: bytes


@dataclass(frozen=True)
class ProposalDetail:
    proposal: Proposal
    candidate_hash: str
    status: str
