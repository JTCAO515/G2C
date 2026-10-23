"""CJ021 read-only internal candidate. No withdrawal writer or authority issuer."""
from dataclasses import dataclass
from hashlib import sha256
import json

from cj_memory.domain import Conflict, InvalidInput, Receipt, Unavailable


def _id(value):
    if type(value) is not str or not value.strip() or len(value) > 4096:
        raise InvalidInput('invalid identifier')
    return value


def _version(value):
    if type(value) is not int or value < 1:
        raise InvalidInput('invalid version')
    return value


@dataclass(frozen=True, repr=False)
class Action:
    action_id: str
    operation: str
    item_id: str
    expected_version: int
    source_id: str
    expected_source_version: int
    raw: bytes

    @classmethod
    def parse(cls, raw):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise InvalidInput('duplicate field')
                result[key] = value
            return result
        if type(raw) is not bytes or len(raw) > 32768:
            raise InvalidInput('original UTF8 bytes required')
        try:
            obj = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
        except (ValueError, UnicodeError):
            raise InvalidInput('invalid JSON') from None
        if type(obj) is not dict or set(obj) != set(cls.__dataclass_fields__) - {'raw'}:
            raise InvalidInput('unsupported fields')
        for key in ('action_id', 'item_id', 'source_id'):
            _id(obj[key])
        if obj['operation'] != 'withdraw':
            raise InvalidInput('withdraw required; pause is a different action')
        _version(obj['expected_version'])
        _version(obj['expected_source_version'])
        return cls(**obj, raw=raw)


@dataclass(frozen=True, repr=False)
class SourceReference:
    source_id: str
    source_version: int
    # Complete same-scope reverse references must come from the original owner.
    item_ids: tuple[str, ...]


def check_history(action, history):
    """Shape/closure checks only. A tuple cannot certify history completeness.

    The producer must enumerate and lock full history/reverse references in the
    SAME canonical transaction. Missing/shared/ambiguous input is refused here.
    No source is withdrawn by this function.
    """
    if type(history) is not tuple or not 1 <= len(history) <= 1000:
        raise Unavailable('source history unavailable or exceeds candidate bound')
    seen = set()
    for ref in history:
        if type(ref) is not SourceReference:
            raise Unavailable('source history unavailable')
        _id(ref.source_id); _version(ref.source_version)
        if ref.source_id in seen:
            raise Unavailable('ambiguous source history')
        seen.add(ref.source_id)
        if type(ref.item_ids) is not tuple or ref.item_ids != (action.item_id,):
            raise Unavailable('shared or unresolved source references')
    if (action.source_id, action.expected_source_version) not in {
            (ref.source_id, ref.source_version) for ref in history}:
        raise Conflict('current source revision differs')


@dataclass(frozen=True, repr=False)
class OriginalAction:
    """Read observation from a future original ledger, NOT a durable receipt issuer.

    Constructing this dataclass grants no authority. Only synthetic fixtures can
    currently supply it: no accepted producer exists at the pinned input.
    """
    scope: str
    original_input: bytes
    receipt: Receipt
    epoch: int
    history: tuple[SourceReference, ...]

    def validate(self):
        _id(self.scope)
        action = Action.parse(self.original_input)
        r = self.receipt
        if (type(r) is not Receipt or r.operation_id != action.action_id
                or r.item_id != action.item_id or type(r.version) is not int
                or r.version != action.expected_version + 1 or r.status != 'withdrawn'
                or r.input_sha256 != sha256(self.original_input).hexdigest()):
            raise Unavailable('original withdrawal receipt mismatch')
        _version(self.epoch)
        check_history(action, self.history)
        return action

    def recover(self, scope, original_utf8):
        action = self.validate()
        if scope != self.scope:
            raise Unavailable('original action unavailable')
        requested = Action.parse(original_utf8)
        if requested.action_id != action.action_id or original_utf8 != self.original_input:
            raise Conflict('original action bytes differ')
        return self.receipt  # Historical; does not mutate or restart cleanup.


def check_candidate_references(original, scope, *, item_id, source_ids, observed_epoch):
    """Bounded NEGATIVE check for old summaries/rebuilds/in-flight provenance.

    Passing is not publication permission. Canonical require_current and the
    shared RUN transaction remain mandatory; raw retained-chat ingress must also
    carry complete provenance. Unknown provenance is refused, never inferred.
    """
    action = original.validate()
    if scope != original.scope:
        raise Unavailable('original action unavailable')
    _id(item_id)
    if type(observed_epoch) is not int or observed_epoch < original.epoch:
        raise Conflict('stale memory epoch')
    if type(source_ids) is not tuple or not 1 <= len(source_ids) <= 1000:
        raise Unavailable('complete provenance unavailable')
    for source_id in source_ids:
        _id(source_id)
    if len(set(source_ids)) != len(source_ids):
        raise InvalidInput('duplicate provenance')
    if item_id == action.item_id or set(source_ids) & {ref.source_id for ref in original.history}:
        raise Conflict('withdrawn item or source history')


def execute_withdrawal(*args, **kwargs):
    raise Unavailable('same-transaction source history/retombstone producer unavailable')


def public_factory(*args, **kwargs):
    raise Unavailable('public withdrawal activation disabled')
