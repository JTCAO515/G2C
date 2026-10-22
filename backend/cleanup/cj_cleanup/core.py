"""CJ-CLEANUP-INTERNAL@0.1.0-rc.1. Metadata-only, no destructive executor."""
from __future__ import annotations
from dataclasses import dataclass, replace, asdict
from hashlib import sha256
import json
import re
from threading import RLock
from cj_auth.interfaces import TrustedPrincipal

VERSION = 'CJ-CLEANUP-INTERNAL@0.1.0-rc.1'
BARRIERS = ('auth_revocation', 'tasks_stopped', 'restore_fence',
            'backup_retention', 'offline_devices', 'external_retention')
STATES = ('pending', 'in_progress', 'unknown', 'failed', 'confirmed')
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')

class Conflict(Exception): pass
class Denied(Exception): pass
class Invalid(Exception): pass

def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')

def digest(raw): return sha256(raw).hexdigest()

def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value): raise Invalid('invalid identifier')
    return value

def hash_value(value):
    if not isinstance(value, str) or not HEX.fullmatch(value): raise Invalid('invalid digest')
    return value

@dataclass(frozen=True, repr=False)
class Scope:
    environment: str
    issuer: str
    subject: str
    audience: str

    @classmethod
    def from_principal(cls, environment, principal):
        if not isinstance(principal, TrustedPrincipal): raise Denied('trusted AUTH principal required')
        identifier(environment)
        if not all(isinstance(v, str) and v for v in (principal.issuer, principal.subject, principal.audience)):
            raise Denied('invalid AUTH binding')
        return cls(environment, principal.issuer, principal.subject, principal.audience)

@dataclass(frozen=True)
class Entry:
    registry_id: str
    version: str
    hook_available: bool

@dataclass(frozen=True)
class Manifest:
    registry_version: str
    registry_digest: str
    entries: tuple[Entry, ...]
    gaps: tuple[str, ...]


def freeze_registry(raw: bytes, expected_ids: tuple[str, ...]) -> Manifest:
    """expected_ids is independent host inventory, never a request-supplied list."""
    try:
        data = json.loads(raw)
        version = identifier(data['version'])
        stores = data['stores']
        if not isinstance(stores, list) or not stores: raise Invalid('registry missing')
        expected = tuple(identifier(x) for x in expected_ids)
        if not expected or len(set(expected)) != len(expected): raise Invalid('inventory missing')
        entries = []
        def walk(node, prefix=''):
            if not isinstance(node, dict): raise Invalid('invalid registry')
            key = prefix + identifier(node['id'])
            # No callable path is consumed. Available only means explicit protocol registration.
            available = node.get('cleanup_protocol') == VERSION
            entries.append(Entry(key, digest(encode(node)), available))
            children = node.get('objects', [])
            if not isinstance(children, list): raise Invalid('invalid registry')
            for child in children:
                if isinstance(child, dict): walk(child, key + '/')
                elif not isinstance(child, str): raise Invalid('invalid registry')
        for store in stores: walk(store)
        ids = [e.registry_id for e in entries]
        if len(set(ids)) != len(ids): raise Invalid('duplicate registry ID')
        gaps = tuple(sorted('unregistered:' + x for x in set(expected) - set(ids)))
        return Manifest(version, digest(raw), tuple(sorted(entries, key=lambda e:e.registry_id)), gaps)
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise Invalid('invalid registry') from None

@dataclass(frozen=True)
class Step:
    target: str
    version: str
    available: bool
    state: str = 'pending'
    invocation: str | None = None
    receipt_bytes: bytes | None = None

@dataclass(frozen=True, repr=False)
class Operation:
    scope: Scope
    operation_id: str
    confirmation_digest: str
    manifest: Manifest
    steps: tuple[Step, ...]
    gaps: tuple[str, ...] = ()
    revision: int = 0

    @property
    def status(self):
        if self.gaps or self.manifest.gaps: return 'blocked'
        if any(s.state == 'unknown' for s in self.steps): return 'unknown'
        if any(s.state == 'failed' for s in self.steps): return 'failed'
        if all(s.state == 'confirmed' for s in self.steps): return 'complete'
        if not all(s.available for s in self.steps): return 'blocked'
        if self.steps[0].state != 'confirmed': return 'awaiting_revocation'
        return 'in_progress'


def request(scope: Scope, operation_id: str, confirmation_digest: str,
            manifest: Manifest, capabilities: tuple[str, ...] = ()) -> Operation:
    """Host verified explicit confirmation; digest commits exact confirmation input bytes.

    capabilities names only existing trusted receipt importers. None are enabled by default.
    This function authorizes no actions and does not issue AUTH access.
    """
    identifier(operation_id); hash_value(confirmation_digest)
    if not isinstance(scope, Scope) or not isinstance(manifest, Manifest) or not manifest.entries:
        raise Invalid('binding or manifest missing')
    targets = [(b, VERSION, b in capabilities) for b in BARRIERS]
    targets += [('store:' + e.registry_id, e.version,
                 e.hook_available and ('store:' + e.registry_id) in capabilities) for e in manifest.entries]
    if set(capabilities) - {t[0] for t in targets}: raise Invalid('unregistered capability')
    return Operation(scope, operation_id, confirmation_digest, manifest,
                     tuple(Step(*t) for t in targets))


def intent(op: Operation, target: str, invocation: str) -> Operation:
    """Journal intent BEFORE a hypothetical trusted hook; no hook is called here."""
    identifier(invocation)
    index = next((i for i,s in enumerate(op.steps) if s.target == target), None)
    if index is None: raise Invalid('unknown target')
    step = op.steps[index]
    if step.invocation == invocation: return op  # never dispatch or imply retry
    if step.invocation is not None: raise Conflict('original invocation required')
    if op.gaps or op.manifest.gaps or not step.available: raise Denied('hook or coverage unavailable')
    if index > 0 and op.steps[0].state != 'confirmed': raise Denied('revocation unconfirmed')
    if index >= len(BARRIERS) and op.steps[1].state != 'confirmed': raise Denied('tasks not stopped')
    steps = list(op.steps); steps[index] = replace(step, invocation=invocation, state='in_progress')
    return replace(op, steps=tuple(steps), revision=op.revision+1)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise Invalid('duplicate receipt key')
        result[key] = value
    return result


def receipt(op: Operation, target: str, raw: bytes) -> Operation:
    """Only trusted host importer calls this. Metadata whitelist; no provider/body payload."""
    try:
        if not isinstance(raw, bytes) or len(raw) > 4096: raise Invalid('invalid receipt')
        # bytes auto-detection accepts UTF16/32; decode explicitly and keep raw intact.
        # object_pairs_hook rejects duplicates at every depth before consuming values.
        data = json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=_unique_object)
        if not isinstance(data, dict): raise Invalid('invalid receipt')
        if set(data) != {'protocol','scope_digest','operation_id','target','version','invocation','outcome'}:
            raise Invalid('invalid receipt fields')
        step = next(s for s in op.steps if s.target == target)
        if (data['protocol'] != VERSION or data['scope_digest'] != digest(encode(asdict(op.scope)))
            or data['operation_id'] != op.operation_id or data['target'] != target
            or data['version'] != step.version or step.invocation is None
            or data['invocation'] != step.invocation): raise Conflict('receipt binding mismatch')
        outcome = data['outcome']
        if outcome not in ('confirmed','unknown','failed'): raise Invalid('invalid outcome')
        if step.receipt_bytes == raw: return op
        if step.state in ('confirmed','failed'): raise Conflict('terminal receipt conflict')
        # Unknown may be reconciled only by the original receipt importer and invocation.
        steps = tuple(replace(s, state=outcome, receipt_bytes=raw) if s.target == target else s for s in op.steps)
        return replace(op, steps=steps, revision=op.revision+1)
    except (StopIteration, TypeError, ValueError, UnicodeError):
        raise Invalid('invalid receipt') from None


def restart(op: Operation) -> Operation:
    steps = tuple(replace(s, state='unknown') if s.state == 'in_progress' else s for s in op.steps)
    return replace(op, steps=steps, revision=op.revision + (steps != op.steps))


def audit_registry(op: Operation, current: Manifest) -> Operation:
    if current == op.manifest: return op
    gap = 'registry_changed_requires_review'
    if gap in op.gaps: return op
    return replace(op, gaps=op.gaps+(gap,), revision=op.revision+1)


def execute_destructive_action(*args, **kwargs):
    raise Denied('destructive execution disabled; no real hooks or revocation authority')


def public_query(*args, **kwargs):
    raise Denied('public progress credential contract not frozen')


class Repository:
    """Atomic local candidate. Export/rebuild is explicit, NOT a production durable DB.

    Lock + expected revision provides per-operation CAS. No mutable state escapes.
    Every transform is computed under the lock; failure leaves original state intact.
    """
    def __init__(self):
        self._lock = RLock()
        self._operations = {}
        self._journal = []

    def create(self, op):
        with self._lock:
            key = (op.scope, op.operation_id)
            old = self._operations.get(key)
            if old:
                if (old.confirmation_digest, old.manifest) != (op.confirmation_digest, op.manifest):
                    raise Conflict('operation input conflict')
                return old
            if any(k[0] == op.scope for k in self._operations):
                raise Conflict('original scope operation must be recovered')
            self._operations[key] = op
            self._journal.append({"kind":"create", "scope":asdict(op.scope), "operation_id":op.operation_id,
                "confirmation_digest":op.confirmation_digest, "manifest":asdict(op.manifest),
                "capabilities":[s.target for s in op.steps if s.available]})
            return op

    def query(self, scope, operation_id):
        with self._lock:
            op = self._operations.get((scope, operation_id))
            if op is None: raise Denied('operation unavailable')
            return op

    def _update(self, scope, operation_id, expected_revision, transform, event):
        with self._lock:
            old = self.query(scope, operation_id)
            if old.revision != expected_revision: raise Conflict('revision conflict')
            new = transform(old)
            if (new.scope, new.operation_id, new.confirmation_digest, new.manifest) != (old.scope, old.operation_id, old.confirmation_digest, old.manifest):
                raise Conflict('immutable operation changed')
            if new.revision not in (old.revision, old.revision+1): raise Conflict('invalid revision')
            self._operations[(scope, operation_id)] = new
            self._journal.append(dict(event, scope=asdict(scope), operation_id=operation_id, revision=expected_revision))
            return new

    def intent(self, scope, operation_id, revision, target, invocation):
        return self._update(scope, operation_id, revision, lambda op:intent(op,target,invocation),
                            dict(kind='intent', target=target, invocation=invocation))

    def receipt(self, scope, operation_id, revision, target, raw):
        return self._update(scope, operation_id, revision, lambda op:receipt(op,target,raw),
                            dict(kind='receipt', target=target, raw=raw.hex()))

    def audit(self, scope, operation_id, revision, manifest):
        return self._update(scope, operation_id, revision, lambda op:audit_registry(op,manifest),
                            dict(kind='audit', manifest=asdict(manifest)))

    def recover(self, scope, operation_id, revision):
        return self._update(scope, operation_id, revision, restart, dict(kind='restart'))

    def journal(self):
        """Private metadata contains identity IDs; trusted storage only, never logs/HTTP."""
        with self._lock:
            return encode({'protocol':VERSION, 'events':self._journal})

    @classmethod
    def rebuild(cls, raw, *, recover_inflight=True):
        """Replay exact original metadata/receipt bytes. Truncated journal fails closed.

        Integrity/durability/ownership of the journal is the trusted host's duty.
        This is NOT an untrusted upload format or a signed capability.
        Durable adapters replay with recover_inflight=False, then journal explicit
        recover() under CAS after a lost writer, rather than silently rewriting history.
        """
        try:
            data = json.loads(raw)
            if data['protocol'] != VERSION: raise Invalid('journal version mismatch')
            repo = cls()
            for e in data['events']:
                scope = Scope(**e['scope'])
                oid = e['operation_id']
                kind = e['kind']
                if kind in ('create','audit'):
                    m = e['manifest']
                    manifest = Manifest(m['registry_version'], m['registry_digest'],
                                        tuple(Entry(**x) for x in m['entries']), tuple(m['gaps']))
                if kind == 'create':
                    repo.create(request(scope,oid,e['confirmation_digest'],manifest,tuple(e['capabilities'])))
                elif kind == 'intent': repo.intent(scope,oid,e['revision'],e['target'],e['invocation'])
                elif kind == 'receipt': repo.receipt(scope,oid,e['revision'],e['target'],bytes.fromhex(e['raw']))
                elif kind == 'audit': repo.audit(scope,oid,e['revision'],manifest)
                elif kind == 'restart': repo.recover(scope,oid,e['revision'])
                else: raise Invalid('unknown journal event')
            # Persisted dispatch intent without a result is uncertain after process loss.
            for op in tuple(repo._operations.values()):
                if recover_inflight and any(s.state == 'in_progress' for s in op.steps):
                    repo.recover(op.scope,op.operation_id,op.revision)
            return repo
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise Invalid('invalid journal') from None
