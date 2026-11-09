"""At-most-once dialogue entry for the canonical C Trip adoption action."""
from dataclasses import dataclass

from cj_agent.draft import trip_scope_for
from cj_run.core import Binding
from cj_trip.domain import Conflict as TripConflict

from .demo_dialogue import PLANNING_VERSION, _identity
from .domain import CommitUnknown, InputConflict, SequenceConflict, Unavailable


@dataclass(frozen=True)
class Adoption:
    scope: str
    action_id: str
    original_message_id: str
    proposal_id: str
    candidate_hash: str
    digest: str

    @property
    def trip_action_id(self):
        return 'demo-adopt-'+_identity(self.scope,self.action_id)


def find(tx, action_id):
    row=tx.cur.execute('SELECT action_id,original_message_id,proposal_id,candidate_hash,input_sha256 '
        'FROM cj_demo_trip_adoption WHERE scope=%s AND action_id=%s',(tx.scope,action_id)).fetchone()
    return Adoption(tx.scope,*row) if row is not None else None


def _bound_original(tx, stored):
    if stored is None:
        raise Unavailable('original Trip dialogue unavailable')
    receipt=stored.receipt
    tx.chat(receipt.conversation_id,receipt.generation)
    return receipt


def _proposal_origin(tx, action):
    origin=tx.cur.execute('SELECT m.message_id FROM cj_trip_needs_basis b '
        'JOIN cj_message_receipt m ON (m.scope,m.run_id)=(b.message_scope,b.run_id) '
        'JOIN cj_run_record r ON (r.scope,r.run_id)=(m.scope,m.run_id) '
        'WHERE b.scope=%s AND b.message_scope=%s AND b.proposal_id=%s '
        'AND m.conversation_id=%s AND m.demo_dialogue_protocol=%s AND r.status=%s',
        (trip_scope_for(tx.scope),tx.scope,action.card,action.conversation,PLANNING_VERSION,'completed')).fetchone()
    if origin is None:
        raise Unavailable('dialogue Trip proposal unavailable')
    receipt=_bound_original(tx,tx.find(origin[0]))
    return Binding(tx.scope,receipt.conversation_id,receipt.generation,
                   receipt.message_id,receipt.run_id,receipt.sequence)


def _recovery(service, token, action_id, trip_cards, digest=None):
    with service.repository.transaction() as tx:
        record=find(tx,action_id)
        if record is None:
            return None,None
        if digest is not None and record.digest!=digest:
            raise InputConflict()
        origin=_bound_original(tx,tx.find(record.original_message_id))
    current=trip_cards.original_adoption(token,record)
    return record,_result(record,origin.conversation_id,current) if current is not None else None


def _result(intent, conversation, receipt):
    if (receipt['proposal_id'],receipt['candidate_hash'],receipt['kind'],receipt['committed_version']) != (
            intent.proposal_id,intent.candidate_hash,'accept',1):
        raise Unavailable('canonical Trip adoption receipt changed')
    return dict(action_id=intent.action_id,conversation_id=conversation,card_id=intent.proposal_id,
                version=1,operation='accept_trip',input_sha256=intent.digest,message_id=None,run_id=None,
                card=None,trip_id=receipt['trip_id'],committed_version=receipt['committed_version'])


def act(service, token, action, trip_cards):
    from .demo_needs_cards import _lookup

    record,receipt=_recovery(service,token,action.id,trip_cards,action.digest)
    if record is not None:
        if receipt is None:
            raise CommitUnknown('read the original Trip action')
        return receipt
    with service.repository.transaction() as tx:
        binding=_proposal_origin(tx,action)
    card,_=trip_cards.read(token,binding,action.card)
    intent=Adoption(binding.scope,action.id,binding.message_id,action.card,card['candidate_hash'],action.digest)
    with service.repository.transaction() as tx:
        tx.lock_scope()
        old=find(tx,action.id)
        if old is None:
            if _lookup(tx,action.id) is not None:
                raise InputConflict()
            if _proposal_origin(tx,action)!=binding:
                raise Unavailable('original dialogue Trip association changed')
            tx.cur.execute('INSERT INTO cj_demo_trip_adoption(scope,action_id,original_message_id,proposal_id,'
                'candidate_hash,input_sha256) VALUES(%s,%s,%s,%s,%s,%s)',
                (tx.scope,intent.action_id,intent.original_message_id,intent.proposal_id,
                 intent.candidate_hash,intent.digest))
    if old is not None:
        _,receipt=_recovery(service,token,action.id,trip_cards,action.digest)
        if receipt is None:
            raise CommitUnknown('read the original Trip action')
        return receipt
    try:
        receipt=trip_cards.adopt(token,intent)
    except TripConflict as exc:
        raise SequenceConflict('current Trip candidate changed') from exc
    return _result(intent,action.conversation,receipt)


def query(service,token,action_id,trip_cards):
    _,receipt=_recovery(service,token,action_id,trip_cards)
    return receipt
