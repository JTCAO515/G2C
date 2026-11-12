"""One native Lio undo and protected original-action reconciliation, no model."""
from hashlib import sha256

from cj_trip.domain import packed
from cj_trip.lio_history import Undo
from runtime_adapter.contract import decode,encode,Unavailable

from .lio_trip_routes import _apply,_history,_receipt


class NativeUndo:
    def __init__(self,claims,message_boundary,trip_boundary,token_supplier):
        self.claims,self.messages,self.trips,self.token_supplier=claims,message_boundary,trip_boundary,token_supplier

    def conversation(self,request,*,deadline):
        if len(request['prior_step_ids'])!=3:raise Unavailable('NATIVE_UNDO_RECIPE_STEP_CHANGED')
        setup=decode(self.claims.read(request['prior_step_ids'][0],deadline=deadline))
        if setup['kind']!='task_setup' or setup['payload']['task_id']!='val-undo':
            raise Unavailable('NATIVE_UNDO_RECIPE_NOT_CONNECTED')
        def original(context):
            saved=self.claims.query(context,request['prior_step_ids'][-1])
            if saved is None:raise Unavailable('NATIVE_UNDO_SOURCE_UNAVAILABLE')
            return saved.receipt.conversation_id
        return self.messages.with_history_context(self.token_supplier(),original)

    def dispatch(self,request,*,deadline):
        cid=self.conversation(request,deadline=deadline)
        def apply(context):
            history=decode(_history(context,None,cid))
            if history['undo_target'] is None:raise Unavailable('NATIVE_UNDO_TARGET_UNAVAILABLE')
            from .lio_trip_routes import _undo
            return _apply(context,_undo(request['step_id'],history['undo_target']),cid)
        # Same public native operation, same original action ID and source
        # authority. A lost commit ACK is query-only, never a second application.
        return self.trips.with_operation(self.token_supplier(),apply)

    def proof(self,request,*,deadline):
        cid=self.conversation(request,deadline=deadline)
        def original(context):
            receipt=context.query_action(request['step_id'])
            committed=False
            if receipt is not None:
                if receipt.committed_version is None or receipt.committed_version<3:
                    raise Unavailable('NATIVE_UNDO_RECEIPT_CHANGED')
                previous=context.lio_revisions(receipt.trip_id,before=receipt.committed_version,limit=1)
                if len(previous)!=1 or previous[0].version!=receipt.committed_version-1:
                    raise Unavailable('NATIVE_UNDO_ORIGINAL_REVISION_UNAVAILABLE')
                # Reconstruct from the original committed receipt + retained
                # revision, not the now-changed current undo target. The native
                # original reader checks the exact persisted action bytes.
                action=Undo.parse(packed(dict(version='TRIP-lio-undo.1',action_id=request['step_id'],
                    trip_id=receipt.trip_id,expected_version=previous[0].version,
                    original_hash=sha256(previous[0].content).hexdigest())))
                committed=decode(_receipt(context,action,cid))['committed']
            return encode(dict(version='G2C-native-undo-original.1',action_id=request['step_id'],
                conversation_id=cid,committed=committed,status='PASS' if committed else 'UNKNOWN',
                history=decode(_history(context,None,cid))))
        return self.trips.with_operation(self.token_supplier(),original)
