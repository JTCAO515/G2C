"""Short native source projection under existing release/M/Trip/Memory holders.

Never hold this boundary across a provider operation. It does not itself
publish a durable use or turn a callback's filesystem side effect into PASS.
"""
from dataclasses import asdict
from hashlib import sha256

from cj_agent.draft import trip_scope_for
from cj_memory.postgres import Repository as MemoryRepository
from cj_memory.domain import Unavailable as MemoryUnavailable,CommitUnknown as MemoryCommitUnknown
from cj_memory_jobs.postgres import Transaction as MemoryState
from cj_memory_jobs.codec import Unavailable as HistoryUnavailable
from cj_message.auth_boundary import AccessBlocked,IdentityChanged
from cj_message.domain import Unavailable as MessageUnavailable,CommitUnknown as MessageCommitUnknown
from cj_message.needs_binding import needs_scope_for
from cj_message.lio_plan_needs import lio_needs_id
from cj_run.core import Binding as RunBinding
from cj_trip.decision_lease import DecisionAuthority
from cj_trip.decision_source import DecisionQuery
from cj_trip.manual_origin import MAX_BYTES
from cj_trip.domain import Denied,Conflict,CommitUnknown as TripCommitUnknown
from cj_trip.operation import OperationWithheld
from runtime_adapter.contract import decode,encode,require,Unavailable

from .lio_trip_routes import _head
from .local_app import scope_for
from .runtime_release_witness import ReleaseWitness


VERSION='G2C-fixture-native-state.1'


class FixtureSourceBoundary:
    def __init__(self,authority,binding,pins,messages,trips,token_supplier,preparation_message_id,
                 release,*,qualification_guard):
        self.authority,self.binding,self.pins=authority,binding,pins
        self.messages,self.trips,self.token_supplier=messages,trips,token_supplier
        self.mid,self.release=preparation_message_id,release
        self.database=release.database
        self.qualification_guard=qualification_guard
        def bind_memory(connection,cursor):
            cursor.execute("SET LOCAL lock_timeout='5s'")
            cursor.execute("SET LOCAL statement_timeout='10s'")
            connection.bind_scope(cursor)
        self.memories=MemoryRepository(lambda:self.database.connect(binding.scope),binding.scope,
            typed_context=True,transaction_binder=bind_memory)

    def _guard(self,deadline):
        self.authority.require(binding=self.binding,pins_sha256=self.pins.key,
            purpose='query',deadline=deadline,read_only=True)
        if self.authority.pins()!=self.pins.raw:raise Unavailable('FIXTURE_CURRENT_SOURCE_CHANGED')
        self.qualification_guard(deadline)

    def capture(self,*,deadline):
        self._guard(deadline)
        epoch=self.release.observe()
        return self._read(epoch,None,lambda state,private:encode(state),deadline)

    def with_current(self,expected,project,*,deadline):
        value=decode(expected)
        require(type(value)is dict and value.get('version')==VERSION and
            type(value.get('release'))is dict and set(value['release'])=={'instance','lineage'},
            'FIXTURE_NATIVE_EXPECTED_STATE')
        epoch=ReleaseWitness(**value['release'])
        return self._read(epoch,expected,project,deadline)

    def _trip_query(self,token,original):
        def read(context):
            principal=context.metadata.principal
            if scope_for(principal.issuer,principal.subject)!=self.binding.scope:
                raise Unavailable('FIXTURE_NATIVE_OWNER_CHANGED')
            r=original.receipt
            native=RunBinding(self.binding.scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
            accepted=context.lio_plan_receipt(native)
            head=_head(context,r.conversation_id)
            if accepted is None or head is None or accepted.trip_id!=head.trip_id:
                raise Unavailable('FIXTURE_NATIVE_PREPARATION_UNAVAILABLE')
            return encode(dict(trip_id=head.trip_id,expected_version=head.version,
                content_sha256=head.content_sha256))
        return DecisionQuery(**decode(self.trips.with_operation(token,read)))

    def _read(self,epoch,expected,project,deadline):
        self._guard(deadline)
        token=self.token_supplier()
        if sha256(token.encode()).hexdigest()!=self.binding.auth_session_id:
            raise Unavailable('FIXTURE_NATIVE_SESSION_CHANGED')
        def released(actual_release):
            def history(context):
                if context.scope!=self.binding.scope:raise Unavailable('FIXTURE_NATIVE_OWNER_CHANGED')
                def locked():
                    original=context.query_lio_message(self.mid)
                    if original is None:raise Unavailable('FIXTURE_NATIVE_PREPARATION_UNAVAILABLE')
                    r=original.receipt;head=context.send_status(r.conversation_id).head
                    if head is None or head.generation!=r.generation:
                        raise Unavailable('FIXTURE_NATIVE_MESSAGE_CHANGED')
                    query=self._trip_query(token,original)
                    with DecisionAuthority(self.trips,token).hold(context.principal,query,max_source_bytes=MAX_BYTES)as lease:
                        if lease.scope!=trip_scope_for(context.scope):raise Unavailable('FIXTURE_NATIVE_OWNER_CHANGED')
                        with self.memories.transaction()as memory:
                            state=MemoryState(memory);state.require_live()
                            selected=memory.cur.execute('SELECT trip_id,trip_version FROM cj_trip_needs_current '
                                'WHERE scope=%s AND needs_scope=%s AND needs_id=%s',
                                (lease.scope,needs_scope_for(context.scope),lio_needs_id(context.scope,r.conversation_id))).fetchone()
                            unfinished=memory.cur.execute("SELECT EXISTS(SELECT 1 FROM cj_run_record WHERE scope=%s "
                                "AND status IN ('queued','running')) OR EXISTS(SELECT 1 FROM cj_message_delivery "
                                "WHERE scope=%s AND NOT acknowledged)",(context.scope,context.scope)).fetchone()[0]
                            if selected!=(query.trip_id,query.expected_version)or unfinished:
                                raise Unavailable('FIXTURE_NATIVE_SOURCE_NOT_QUIESCENT')
                            consent=memory.cur.execute('SELECT generation,message_epoch,enabled,source_version,withdrawal_epoch '
                                'FROM cj_memory_history_consent WHERE scope=%s AND conversation_id=%s',
                                (context.scope,r.conversation_id)).fetchone()
                            actual=lease.decision
                            frame=dict(version=VERSION,binding_sha256=self.binding.key,release=asdict(actual_release),
                                preparation=dict(message_id=r.message_id,run_id=r.run_id,input_sha256=r.input_sha256),
                                message=dict(conversation_id=r.conversation_id,generation=head.generation,
                                    epoch=head.epoch,last_sequence=head.last_sequence),
                                trip=dict(trip_id_sha256=sha256(actual.trip_id.encode()).hexdigest(),
                                    version=actual.version,content_sha256=actual.content_sha256),
                                memory=dict(epoch=state.epoch,history_erased=False,consent=consent))
                            if expected is not None and encode(frame)!=expected:
                                raise Unavailable('FIXTURE_NATIVE_STATE_CHANGED')
                            self._guard(deadline)
                            result=project(frame,actual.content)
                            if type(result)is not bytes or len(result)>1_048_576:
                                raise Unavailable('BOUNDED_FIXTURE_PROJECTION_REQUIRED')
                            if context.query_lio_message(self.mid)!=original:
                                raise Unavailable('FIXTURE_NATIVE_PREPARATION_CHANGED')
                            self._guard(deadline);lease.check()
                            return result
                return context.with_lio_timeline_projection(locked)
            return self.messages.with_history_context(token,history)
        try:result=self.release.with_current(epoch,released)
        except (AccessBlocked,IdentityChanged,Denied,Conflict,OperationWithheld,MemoryUnavailable,
                HistoryUnavailable,MessageUnavailable,MessageCommitUnknown,MemoryCommitUnknown,TripCommitUnknown):
            raise Unavailable('FIXTURE_NATIVE_STATE_WITHHELD')from None
        self._guard(deadline)
        return result
