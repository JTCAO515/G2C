"""Immutable original MESSAGE travel reference and final, same-connection leases."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
import threading
from psycopg import Error as DatabaseError

from cj_run.core import Denied
from cj_needs.revision_lease import LeaseUnavailable
from .domain import Command, CommitUnknown, InvalidInput, Unavailable, Stored
from .travel import ABI, PROFILE, Selection

_LEASE_FACTORY=object()


class ContextConflict(Exception):
    pass


@dataclass(frozen=True)
class OriginalMessageContextRef:
    owner_scope: str
    conversation_id: str
    generation: str
    message_id: str
    run_id: str
    sequence: int
    input_sha256: str
    message_version: str
    context_kind: str
    context_id: str | None
    context_version: int | None
    selection_epoch: int | None

    def public_value(self):
        return dict(version='MESSAGE-travel-reference.1', conversation_id=self.conversation_id,
            generation=self.generation, message_id=self.message_id, run_id=self.run_id,
            sequence=self.sequence, input_sha256=self.input_sha256, message_version=self.message_version,
            context_kind=self.context_kind, context_id=self.context_id,
            context_version=self.context_version, selection_epoch=self.selection_epoch)


@dataclass(frozen=True)
class OriginalTravelMessage:
    stored: Stored
    reference: OriginalMessageContextRef


def profile(cursor, scope):
    cursor.execute('SELECT version FROM cj_message_context_profile WHERE scope=%s', (scope,))
    row=cursor.fetchone()
    if row is not None and row != (PROFILE,):
        raise Unavailable('message context profile unavailable')
    return row is not None


def require_producer(tx, command):
    if (not tx.travel_mode or not tx.travel_metadata or not tx.registered_usage or not tx.bind_needs or tx.local_run_mode is not True
            or not profile(tx.cur,tx.scope)):
        raise Unavailable('explicit travel producer configuration required')
    tx.local_execution()
    if command.travel_context is not None:
        check_context(tx.cur,tx.scope,command.travel_context)


def check_context(cursor, scope, selection):
    cursor.execute('SELECT version,active FROM cj_travel_context WHERE scope=%s AND context_id=%s FOR SHARE',
                   (scope,selection.id))
    row=cursor.fetchone()
    if row is None:
        raise Unavailable('travel context unavailable')
    if row != (selection.expected_version,True):
        raise ContextConflict('travel context is not current')


def insert_reference(tx, stored, command):
    receipt=stored.receipt
    selection=command.travel_context
    tx.cur.execute('INSERT INTO cj_message_travel_reference '
        '(scope,message_id,run_id,conversation_id,generation,sequence,input_sha256,reference_version,'
        'message_version,reference_kind,context_id,context_version,selection_epoch) '
        'VALUES(%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s)',
        (tx.scope,receipt.message_id,receipt.run_id,receipt.conversation_id,receipt.generation,
         receipt.sequence,receipt.input_sha256,'MESSAGE-send.2','none' if selection is None else 'travel',
         None if selection is None else selection.id,
         None if selection is None else selection.expected_version,receipt.sequence))


def read_reference(tx, stored):
    """DB deserialization boundary: validate the original bytes and copied columns once."""
    receipt=stored.receipt
    try:
        wire_version=json.loads(stored.raw)['version']
        command=Command.parse_v2(stored.raw) if wire_version=='MESSAGE-send.2' else Command.parse_stored(stored.raw)
    except (InvalidInput,ValueError,KeyError,TypeError) as exc:
        raise Unavailable('original context message unavailable') from exc
    if (command.message_id!=receipt.message_id or command.conversation_id!=receipt.conversation_id
            or type(receipt.run_id) is not str or not receipt.run_id.strip()
            or type(receipt.generation) is not str or not receipt.generation.strip()
            or type(receipt.sequence) is not int or receipt.sequence<1
            or hashlib.sha256(stored.raw).hexdigest()!=receipt.input_sha256):
        raise Unavailable('original context association mismatch')
    tx.cur.execute('SELECT r.travel_reference_version,f.message_version,f.reference_kind,f.context_id,'
        'f.context_version,f.selection_epoch,f.run_id,f.conversation_id,f.generation,f.sequence,f.input_sha256 '
        'FROM cj_message_receipt r LEFT JOIN cj_message_travel_reference f '
        'ON (f.scope,f.message_id)=(r.scope,r.message_id) WHERE r.scope=%s AND r.message_id=%s',
        (tx.scope,receipt.message_id))
    row=tx.cur.fetchone()
    if row is None:
        raise Unavailable('original context receipt unavailable')
    if wire_version!='MESSAGE-send.2':
        if row[0] is not None or any(v is not None for v in row[1:]):
            raise Unavailable('legacy message has unexpected travel metadata')
        kind,cid,version,epoch='legacy',receipt.conversation_id,None,None
    else:
        selection=command.travel_context
        kind,cid,version=('none',None,None) if selection is None else ('travel',selection.id,selection.expected_version)
        if (row[:5]!=(1,wire_version,kind,cid,version)
                or type(row[5]) is not int or not 1<=row[5]<=receipt.sequence
                or row[6:]!=(receipt.run_id,receipt.conversation_id,receipt.generation,receipt.sequence,receipt.input_sha256)):
            raise Unavailable('immutable travel reference mismatch')
        epoch=row[5]
    return OriginalMessageContextRef(tx.scope,receipt.conversation_id,receipt.generation,receipt.message_id,
        receipt.run_id,receipt.sequence,receipt.input_sha256,wire_version,kind,cid,version,epoch)


class MessageContextLease:
    def __init__(self, authority, principal, binding, reference, stored, *, _factory=None):
        if _factory is not _LEASE_FACTORY:
            raise TypeError('message context lease must be issued by authority')
        self._authority,self._principal,self._binding=authority,principal,binding
        self._reference,self._stored=reference,stored
        self._active=True
        self._thread=threading.current_thread()

    def check(self,binding):
        if (not self._active or self._thread is not threading.current_thread()
                or self._authority._active.get() is not self or binding!=self._binding):
            raise LeaseUnavailable('message context lease expired')
        if self._authority.admit()!=self._principal:
            raise Denied('message context identity changed')
        return True

    def original_message(self):
        self.check(self._binding)
        return self._stored

    @property
    def reference(self):
        self.check(self._binding)
        return self._reference


class CurrentTravelLease:
    def __init__(self, authority, principal, selection, *, _factory=None):
        if _factory is not _LEASE_FACTORY:
            raise TypeError('current travel lease must be issued by authority')
        self._authority,self._principal,self._selection=authority,principal,selection
        self._active=True
        self._thread=threading.current_thread()

    def check(self):
        if not self._active or self._thread is not threading.current_thread():
            raise LeaseUnavailable('current travel lease expired')
        if self._authority.admit()!=self._principal:
            raise Denied('current travel identity changed')
        return True

    @property
    def context(self):
        self.check()
        return self._selection


class MessageContextAuthority:
    def __init__(self, repository, admit):
        self.repository,self.admit=repository,admit
        self._active=ContextVar('message_travel_lease',default=None)

    @contextmanager
    def _transaction(self):
        try:
            with self.repository.transaction() as tx:
                tx.cur.execute("SELECT set_config('cj.message_context_abi',%s,true)",(ABI,))
                tx.cur.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR SHARE',(tx.scope,))
                if tx.cur.fetchone() is None:
                    raise LeaseUnavailable('message context owner unavailable')
                yield tx
        except (Unavailable,CommitUnknown,DatabaseError):
            raise LeaseUnavailable('travel context storage unavailable') from None

    def _read(self,tx,binding):
        if binding.scope!=tx.scope:
            raise Denied('message context owner mismatch')
        stored=tx.find(binding.message_id)
        if stored is None:
            raise LeaseUnavailable('original message unavailable')
        ref=read_reference(tx,stored)
        if (ref.conversation_id,ref.generation,ref.message_id,ref.run_id,ref.sequence)!=(
                binding.conversation_id,binding.generation,binding.message_id,binding.run_id,binding.message_sequence):
            raise Denied('message context origin mismatch')
        return ref,stored

    def read_original(self,binding):
        principal=self.admit()
        with self._transaction() as tx:
            ref,_=self._read(tx,binding)
            if self.admit()!=principal:
                raise Denied('message context identity changed')
        if self.admit()!=principal:
            raise Denied('message context identity changed')
        return ref

    @contextmanager
    def hold_current(self,selection):
        """C typed manual-save entry: M/T before MEMORY, no message or fake Trip."""
        principal=self.admit()
        lease=None
        try:
            with self._transaction() as tx:
                try: check_context(tx.cur,tx.scope,selection)
                except ContextConflict as exc: raise Denied('current travel context changed') from exc
                lease=CurrentTravelLease(self,principal,selection,_factory=_LEASE_FACTORY)
                try:
                    lease.check()
                    yield lease
                    lease.check()
                finally:
                    lease._active=False
        finally:
            if lease is not None:
                lease._active=False

    @contextmanager
    def hold_for_effect(self,binding):
        active=self._active.get()
        if active is not None:
            active.check(binding)
            yield active
            active.check(binding)
            return
        principal=self.admit()
        lease=None
        try:
            with self._transaction() as tx:
                reference,stored=self._read(tx,binding)
                tx.local_execution(binding.message_id,binding.run_id)
                tx.cur.execute('SELECT generation,last_sequence FROM cj_message_chat '
                    'WHERE scope=%s AND conversation_id=%s AND active',(tx.scope,binding.conversation_id))
                chat=tx.cur.fetchone()
                if chat is None or chat[0]!=binding.generation or chat[1]<reference.sequence:
                    raise Denied('message context conversation invalid')
                enabled=profile(tx.cur,tx.scope)
                if reference.context_kind=='legacy':
                    if enabled:
                        raise Denied('legacy context cannot execute in upgraded scope')
                else:
                    if not enabled or not tx.travel_mode:
                        raise LeaseUnavailable('travel execution configuration unavailable')
                    tx.cur.execute('SELECT selection_epoch,sequence,message_id FROM cj_message_travel_reference '
                        'WHERE scope=%s AND conversation_id=%s AND generation=%s ORDER BY sequence DESC LIMIT 1',
                        (tx.scope,reference.conversation_id,reference.generation))
                    latest=tx.cur.fetchone()
                    if latest is None or latest[1]!=chat[1]:
                        raise LeaseUnavailable('current travel selection unavailable')
                    if latest[2]==reference.message_id:
                        current=reference
                    else:
                        latest_stored=tx.find(latest[2])
                        if latest_stored is None:
                            raise LeaseUnavailable('current original message unavailable')
                        current=read_reference(tx,latest_stored)
                    if current.selection_epoch!=latest[0] or current.sequence!=latest[1]:
                        raise LeaseUnavailable('current original selection mismatch')
                    if latest[0]!=reference.selection_epoch:
                        raise Denied('travel selection changed')
                    if (current.context_kind,current.context_id,current.context_version)!=(
                            reference.context_kind,reference.context_id,reference.context_version):
                        raise LeaseUnavailable('current travel segment mismatch')
                    if reference.context_kind=='travel':
                        try: check_context(tx.cur,tx.scope,Selection(reference.context_id,reference.context_version))
                        except ContextConflict as exc: raise Denied('travel context changed') from exc
                lease=MessageContextLease(self,principal,binding,reference,stored,_factory=_LEASE_FACTORY)
                token=self._active.set(lease)
                try:
                    lease.check(binding)
                    yield lease
                    lease.check(binding)
                finally:
                    self._active.reset(token)
        finally:
            if lease is not None:
                lease._active=False

    def valid(self,binding):
        try:
            with self.hold_for_effect(binding):
                return True
        except Denied:
            return False

    def active_original(self,binding):
        active=self._active.get()
        if active is None:
            raise LeaseUnavailable('active original message lease required')
        active.check(binding)
        return active._stored
