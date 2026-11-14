"""Current native C Trip observation, not a lease or an isolation witness.

The B host selects the preparation MESSAGE. No E-selected owner/Trip/path is
accepted. Private source bytes stay inside the protected native callbacks.
"""
from hashlib import sha256

from cj_message.auth_boundary import AccessBlocked,IdentityChanged
from cj_run.core import Binding as RunBinding
from cj_trip.domain import Denied,Conflict
from cj_trip.operation import OperationWithheld
from runtime_adapter.contract import decode,encode,Unavailable

from .lio_trip_routes import _head
from .local_app import scope_for


class FixtureTripObserver:
    def __init__(self,authority,binding,pins,messages,trips,token_supplier,preparation_message_id):
        self.authority,self.binding,self.pins=authority,binding,pins
        self.messages,self.trips,self.token_supplier=messages,trips,token_supplier
        self.preparation_message_id=preparation_message_id

    def _guard(self,deadline):
        self.authority.require(binding=self.binding,pins_sha256=self.pins.key,
            purpose='query',deadline=deadline,read_only=True)
        # Historical original queries may retain old pins. A current fixture
        # qualification must instead match the actual current source.
        if self.authority.pins()!=self.pins.raw:
            raise Unavailable('FIXTURE_OBSERVER_CURRENT_SOURCE_CHANGED')

    def observe(self,*,deadline):
        self._guard(deadline)
        token=self.token_supplier()
        if sha256(token.encode()).hexdigest()!=self.binding.auth_session_id:
            raise Unavailable('FIXTURE_OBSERVER_SESSION_CHANGED')

        def source(context):
            if context.scope!=self.binding.scope:
                raise Unavailable('FIXTURE_OBSERVER_OWNER_CHANGED')
            saved=context.query_lio_message(self.preparation_message_id)
            if saved is None:raise Unavailable('FIXTURE_PREPARATION_MESSAGE_UNAVAILABLE')
            return saved

        def trip(context):
            principal=context.metadata.principal
            if scope_for(principal.issuer,principal.subject)!=self.binding.scope:
                raise Unavailable('FIXTURE_OBSERVER_OWNER_CHANGED')
            receipt=original.receipt
            native=RunBinding(self.binding.scope,receipt.conversation_id,receipt.generation,
                receipt.message_id,receipt.run_id,receipt.sequence)
            accepted=context.lio_plan_receipt(native)
            if accepted is None:raise Unavailable('FIXTURE_PREPARATION_NOT_ACCEPTED')
            head=_head(context,receipt.conversation_id)
            if head is None or head.trip_id!=accepted.trip_id:
                raise Unavailable('FIXTURE_CURRENT_TRIP_UNAVAILABLE')
            current,=context.lio_revisions(head.trip_id,limit=1)
            if (current.version!=head.version or sha256(current.content).hexdigest()!=head.content_sha256
                    or _head(context,receipt.conversation_id)!=head):
                raise Unavailable('FIXTURE_CURRENT_TRIP_CHANGED')
            return encode(dict(producer_binding_sha256=self.binding.key,
                preparation_message_id=receipt.message_id,preparation_run_id=receipt.run_id,
                preparation_input_sha256=receipt.input_sha256,
                baseline=dict(trip_id_sha256=sha256(head.trip_id.encode()).hexdigest(),
                    trip_version=head.version,content_sha256=head.content_sha256)))

        try:
            original=self.messages.with_history_context(token,source)
            result=decode(self.trips.with_operation(token,trip))
            if self.messages.with_history_context(token,source)!=original:
                raise Unavailable('FIXTURE_PREPARATION_SOURCE_CHANGED')
        except (AccessBlocked,IdentityChanged,Denied,Conflict,OperationWithheld):
            raise Unavailable('FIXTURE_NATIVE_OBSERVATION_WITHHELD')from None
        self._guard(deadline)
        return result
