"""CLEANUP@1.0 domain ABI. No executor, authority, role switching or SQL here."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Protocol

from cj_strict_json import reject_duplicates
from .core import Invalid, Conflict, encode, identifier, hash_value

VERSION = "CLEANUP@1.0"
MAX_INT = 2**63 - 1


def _decode(raw: bytes, limit: int) -> dict:
    try:
        if not isinstance(raw, bytes) or not 0 < len(raw) <= limit:
            raise Invalid("invalid cleanup bytes")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates(Invalid, "duplicate cleanup key"))
        if not isinstance(value, dict):
            raise Invalid("invalid cleanup object")
        return value
    except (ValueError, UnicodeError):
        raise Invalid("invalid cleanup JSON") from None


def _integer(value, minimum=1):
    if type(value) is not int or not minimum <= value <= MAX_INT:
        raise Invalid("invalid cleanup integer")
    return value


@dataclass(frozen=True)
class Selection:
    kind: str
    item_id: str | None = None
    item_version: int | None = None
    scope_epoch: int | None = None
    before_unix: int | None = None

    @classmethod
    def from_dict(cls, value: dict) -> Selection:
        if not isinstance(value, dict):
            raise Invalid("invalid cleanup selection")
        if value == {"kind": "account"}:
            return cls("account")
        if set(value) == {"kind", "item_id", "item_version", "scope_epoch"} and value["kind"] == "memory":
            return cls("memory", identifier(value["item_id"]), _integer(value["item_version"]), _integer(value["scope_epoch"]))
        if set(value) == {"kind", "before_unix"} and value["kind"] == "diagnostics":
            return cls("diagnostics", before_unix=_integer(value["before_unix"], 0))
        raise Invalid("invalid cleanup selection")

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True, repr=False)
class HookRequest:
    protocol = VERSION
    operation_id: str
    invocation_id: str
    subject_digest: str
    registry_digest: str
    entry_digest: str
    target: str
    domain_scope: str
    selection: Selection
    original_utf8: bytes

    @classmethod
    def from_bytes(cls, raw: bytes) -> HookRequest:
        value = _decode(raw, 16384)
        if set(value) != {"protocol", "operation_id", "invocation_id", "subject_digest", "registry_digest", "entry_digest", "target", "domain_scope", "selection"} or value["protocol"] != VERSION:
            raise Invalid("invalid cleanup request fields")
        scope = value["domain_scope"]
        if not isinstance(scope, str) or "\0" in scope:
            raise Invalid("invalid domain scope")
        try:
            if not 1 <= len(scope.encode("utf-8")) <= 4096:
                raise Invalid("invalid domain scope")
        except UnicodeError:
            raise Invalid("invalid domain scope") from None
        return cls(identifier(value["operation_id"]), identifier(value["invocation_id"]),
                   hash_value(value["subject_digest"]), hash_value(value["registry_digest"]),
                   hash_value(value["entry_digest"]), identifier(value["target"]), scope,
                   Selection.from_dict(value["selection"]), raw)

    @property
    def digest(self) -> str:
        return sha256(self.original_utf8).hexdigest()


@dataclass(frozen=True)
class HookReceipt:
    request_digest: str
    outcome: str
    original_utf8: bytes

    @classmethod
    def from_bytes(cls, raw: bytes, request: HookRequest) -> HookReceipt:
        return cls.from_digest(raw, request.digest)

    @classmethod
    def from_digest(cls, raw: bytes, original_request_digest: str) -> HookReceipt:
        """Trusted original-result storage importer; a digest is not authority."""
        value = _decode(raw, 4096)
        if set(value) != {"protocol", "request_digest", "outcome"} or value["protocol"] != VERSION:
            raise Invalid("invalid cleanup receipt fields")
        request_digest = hash_value(value["request_digest"])
        if request_digest != original_request_digest:
            raise Conflict("cleanup receipt binding mismatch")
        if value["outcome"] not in ("confirmed", "unknown", "failed"):
            raise Invalid("invalid cleanup outcome")
        return cls(request_digest, value["outcome"], raw)


def make_request(*, operation_id: str, invocation_id: str, subject_digest: str,
                 registry_digest: str, entry_digest: str, target: str,
                 domain_scope: str, selection: Selection) -> HookRequest:
    return HookRequest.from_bytes(encode(dict(protocol=VERSION, operation_id=operation_id,
        invocation_id=invocation_id, subject_digest=subject_digest, registry_digest=registry_digest,
        entry_digest=entry_digest, target=target, domain_scope=domain_scope, selection=selection.to_dict())))


def make_receipt(request: HookRequest, outcome: str) -> HookReceipt:
    return HookReceipt.from_bytes(encode(dict(protocol=VERSION, request_digest=request.digest, outcome=outcome)), request)


class DomainHook(Protocol):
    def execute(self, request: HookRequest) -> HookReceipt: ...
    def reconcile(self, request: HookRequest) -> HookReceipt: ...
