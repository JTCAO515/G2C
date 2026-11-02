"""MESSAGE-SOURCE@1: committed intervals under canonical MESSAGE + consent locks."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import ContextManager, Protocol

from cj_auth.interfaces import TrustedPrincipal
from .domain import Command, Cursor, HistoryMessage, InvalidInput, Unavailable

VERSION = "MESSAGE-SOURCE@1"
CONVERSATION_TYPES = ("travel", "service")


def _identity(value):
    if type(value) is not str or not value.strip() or "\0" in value:
        raise InvalidInput("invalid source identity")
    try:
        if len(value.encode("utf-8")) > 1024:
            raise InvalidInput("invalid source identity")
    except UnicodeError:
        raise InvalidInput("invalid source identity") from None
    return value


def _integer(value, minimum=0):
    if type(value) is not int or not minimum <= value <= 2**63 - 1:
        raise InvalidInput("invalid source integer")
    return value


@dataclass(frozen=True)
class SourceQuery:
    conversation_id: str
    generation: str
    epoch: int
    after: int
    through: int
    source_version: int
    withdrawal_epoch: int
    mode: str = "incremental"

    def __post_init__(self):
        _identity(self.conversation_id); _identity(self.generation)
        for value in (self.epoch, self.after, self.through):
            _integer(value)
        _integer(self.source_version, 1); _integer(self.withdrawal_epoch, 1)
        if not 1 <= self.through - self.after <= 100 or self.mode not in ("incremental", "conversation_end"):
            raise InvalidInput("invalid source interval")


@dataclass(frozen=True)
class SourcePermit:
    """Issued by trusted C policy while holding its canonical consent/withdrawal lock.

    This value alone conveys no grant. The installed policy owns the authority.
    """
    cursor: Cursor
    source_version: int
    withdrawal_epoch: int


class SourcePolicy(Protocol):
    def hold(self, principal: TrustedPrincipal, scope: str, query: SourceQuery) -> ContextManager[SourcePermit]: ...


@dataclass(frozen=True)
class EndQuery:
    conversation_id: str
    generation: str
    epoch: int
    through: int

    def __post_init__(self):
        _identity(self.conversation_id); _identity(self.generation)
        _integer(self.epoch); _integer(self.through)


@dataclass(frozen=True)
class ConversationEnd:
    end_id: str
    conversation_id: str
    generation: str
    epoch: int
    through: int
    conversation_type: str = "travel"


@dataclass(frozen=True, repr=False)
class SourceSnapshot:
    scope: str
    cursor: Cursor
    source_version: int
    withdrawal_epoch: int
    messages: tuple[HistoryMessage, ...]
    end: ConversationEnd | None


def end_id(scope, query: EndQuery):
    raw = json.dumps([scope, query.conversation_id, query.generation, query.epoch, query.through],
                     ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return sha256(raw).hexdigest()


def _end(tx, query: EndQuery, *, create=False):
    chat = tx.chat(query.conversation_id, query.generation)
    if (chat.epoch, chat.last_sequence) != (query.epoch, query.through):
        raise Unavailable("source unavailable")
    cur = tx.cur
    cur.execute("SELECT conversation_type::text,end_id,end_generation,end_epoch,end_sequence "
                "FROM cj_message_chat WHERE scope=%s AND conversation_id=%s",
                (tx.scope, query.conversation_id))
    kind, eid, generation, epoch, through = cur.fetchone()
    if kind != "travel":
        raise Unavailable("source unavailable")
    wanted = end_id(tx.scope, query)
    if eid is None and create:
        cur.execute("UPDATE cj_message_chat SET end_id=%s,end_generation=%s,end_epoch=%s,end_sequence=%s "
                    "WHERE scope=%s AND conversation_id=%s AND end_id IS NULL",
                    (wanted, query.generation, query.epoch, query.through, tx.scope, query.conversation_id))
        return ConversationEnd(wanted, query.conversation_id, query.generation, query.epoch, query.through)
    if (eid, generation, epoch, through) != (wanted, query.generation, query.epoch, query.through):
        raise Unavailable("source unavailable")
    return ConversationEnd(eid, query.conversation_id, generation, epoch, through)


def finish(service, query: EndQuery):
    with service.repository.transaction() as tx:
        tx.lock_scope()
        value = _end(tx, query, create=True)
    return value


def with_source(service, principal, query: SourceQuery, policy: SourcePolicy, project):
    """Original V1 entry: MESSAGE then C consent/MEMORY, materialized bytes only."""
    if policy is None:raise Unavailable("source unavailable")
    with service.repository.transaction() as tx:
        tx.lock_scope()
        result=_with_locked_source(tx,principal,query,policy,project)
    return result


def _with_locked_source(tx,principal,query,policy,project):
    """B package helper. Caller holds the canonical MESSAGE scope lock."""
    chat = tx.chat(query.conversation_id, query.generation)
    if chat.epoch != query.epoch or query.through > chat.last_sequence:
        raise Unavailable("source unavailable")
    tx.cur.execute("SELECT conversation_type::text FROM cj_message_chat WHERE scope=%s AND conversation_id=%s",
                   (tx.scope, query.conversation_id))
    if tx.cur.fetchone() != ("travel",):
        raise Unavailable("source unavailable")
    # The trusted policy, not these comparison DTOs or request fields, grants collection.
    with policy.hold(principal, tx.scope, query) as permit:
        cursor = Cursor(tx.scope, query.conversation_id, query.generation, query.epoch, query.through, query.after)
        if (permit.cursor, permit.source_version, permit.withdrawal_epoch) != (cursor, query.source_version, query.withdrawal_epoch):
            raise Unavailable("source unavailable")
        stored = tx.history(query.conversation_id, query.generation, query.after, query.through, 100)
        if len(stored) != query.through - query.after:
            raise Unavailable("source unavailable")
        rows = []
        for sequence, item in enumerate(stored, query.after + 1):
            command = Command.parse_original(item.raw)
            r = item.receipt
            if ((r.conversation_id, r.generation, r.sequence, r.message_id, r.input_sha256) !=
                (query.conversation_id, query.generation, sequence, command.message_id, sha256(item.raw).hexdigest())
                or command.conversation_id != query.conversation_id):
                raise Unavailable("source unavailable")
            rows.append(HistoryMessage(r, item.raw, json.loads(item.raw)["text"]))
        end = _end(tx, EndQuery(query.conversation_id, query.generation, query.epoch, query.through)) if query.mode == "conversation_end" else None
        result = project(SourceSnapshot(tx.scope, cursor, permit.source_version, permit.withdrawal_epoch, tuple(rows), end))
        if type(result) is not bytes or len(result) > 524288:
            raise InvalidInput("bounded materialized source response required")
    return result
