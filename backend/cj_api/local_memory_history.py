"""RUN-MEMORY-HISTORY@1: current original input plus genuine formal decisions.

The host collects coordinates, never client/model text as authority. The actual
C runtime keeps the original Memory/reference locks and checks at every effect.
"""
import json
from hashlib import sha256
from psycopg import Error as DatabaseError

from cj_memory.runtime import RuntimeDenied,RuntimeUnknown
from cj_message.domain import Command
from cj_trip.auth_boundary import Boundary as TripBoundary
from cj_trip.domain import Denied as TripDenied,Conflict as TripConflict,CommitUnknown
from cj_trip.operation import OperationWithheld
from cj_trip.decision_source import DecisionQuery
from cj_memory_jobs.decision_fence import read_original_digest
from cj_agent.draft import trip_scope_for
from cj_strict_json import reject_duplicates
from .local_account_admission_v2 import account_checker_for
from .local_app import scope_for

FENCE='MEMORY-HISTORY-ERASURE-FENCE@1'


class HistoryMemory:
    def __init__(self,memory,collect):
        self.memory,self.collect=memory,collect

    def capture(self,binding):
        messages,decisions=self.collect(binding)
        run=self.memory.capture_history(binding,messages,decision_source_sha256s=decisions)
        if run.erasure_protocol!=FENCE:raise RuntimeDenied('explicit original-history erasure fence required')
        return run

    def before_model(self,binding,original,messages,system):
        decisions=self.collect.model_decisions(binding,messages,system)
        return self.memory.with_history(original,[],decision_source_sha256s=decisions)


class OriginalHistory:
    def __init__(self,messages,decision_refs):
        self.messages,self.decision_refs=messages,decision_refs

    def _stored(self,binding):
        stored=self.messages.query(binding.message_id)
        if stored is None:raise RuntimeDenied('original model input unavailable')
        receipt=stored.receipt
        if (self.messages.repository.scope!=binding.scope or
            (receipt.message_id,receipt.conversation_id,receipt.generation,receipt.run_id,receipt.sequence)!=
            (binding.message_id,binding.conversation_id,binding.generation,binding.run_id,binding.message_sequence)):
            raise RuntimeDenied('original model history binding changed')
        return stored

    def __call__(self,binding):
        stored=self._stored(binding);receipt=stored.receipt
        refs=[dict(conversation_id=receipt.conversation_id,generation=receipt.generation,
                   sequence=receipt.sequence,message_id=receipt.message_id,input_sha256=receipt.input_sha256)]
        # MESSAGE1/2's answer prompt contains current input plus C Memory only.
        # Formal3/4 additionally contains genuine Trip bytes; its trusted host
        # must collect the corresponding C digest, never substitute an empty set.
        command=json.loads(stored.raw)
        decisions=self.decision_refs.original(binding,stored) if command.get('version') in ('MESSAGE-send.3','MESSAGE-send.4') else []
        return refs,decisions

    def model_decisions(self,binding,messages,system):
        return self.decision_refs.model(binding,self._stored(binding),messages,system)


class OriginalDecisions:
    def __init__(self,database,auth_dir,credential,principal,message_context):
        self.credential,self.principal,self.message_context=credential,principal,message_context
        def resolve(p):
            owner=scope_for(p.issuer,p.subject)
            return lambda:database.connect(owner),trip_scope_for(owner)
        self.boundary=TripBoundary(account_checker_for(auth_dir,database),resolve,structured=True)

    def _digest(self,binding,query):
        try:return read_original_digest(self.boundary,self.credential,self.principal(),binding.scope,query).decode('ascii')
        except (TripDenied,TripConflict,ValueError) as error:raise RuntimeDenied('original model decision unavailable') from error
        except (OperationWithheld,CommitUnknown,DatabaseError) as error:raise RuntimeUnknown('original model decision uncertain') from error

    def original(self,binding,stored):
        command=Command.parse_original(stored.raw)
        if command.trip_context is None:return []
        if self.message_context is None:raise RuntimeDenied('genuine formal source holder required')
        reference=self.message_context.read_original(binding)
        raw=reference.source
        return [self._digest(binding,DecisionQuery(command.trip_context.id,command.trip_context.expected_version,sha256(raw).hexdigest()))]

    def model(self,binding,stored,messages,system):
        command=Command.parse_original(stored.raw);digests=[]
        for message in messages:
            if message.get('role')!='system':continue
            raw=message.get('content')
            if type(raw) is not str or not raw.lstrip().startswith('{'):continue
            try:value=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate typed model source'))
            except (ValueError,RecursionError) as error:raise RuntimeDenied('typed model source unavailable') from error
            if type(value) is not dict:raise RuntimeDenied('typed model source object required')
            if value.get('version')!='TRIP-source-input.2':
                if 'current_trip' in value:raise RuntimeDenied('unknown formal model context version')
                continue
            if set(value)!={'version','needs_id','revision','fields','current_trip'} or command.needs_reference!=(value['needs_id'],value['revision']):
                raise RuntimeDenied('original NEEDS model source differs')
            trip=value['current_trip']
            if trip is None:continue
            if type(trip) is not dict or set(trip)!={'trip_id','version','content','proposed_fields'}:
                raise RuntimeDenied('bounded original Trip model source required')
            expected=self.principal()
            def read(context):
                if context.metadata.principal!=expected or context.metadata.scope!=trip_scope_for(binding.scope):
                    raise TripDenied('original Trip model owner differs')
                actual=context.detail(trip['trip_id'])
                if actual is None or actual.version!=trip['version'] or json.loads(actual.content)!=trip['content']:
                    raise TripDenied('original Trip model bytes differ')
                return sha256(actual.content).hexdigest().encode('ascii')
            try:content_sha=self.boundary.with_operation(self.credential,read).decode('ascii')
            except (TripDenied,TripConflict,ValueError) as error:raise RuntimeDenied('original Trip model context unavailable') from error
            except (OperationWithheld,CommitUnknown,DatabaseError) as error:raise RuntimeUnknown('original Trip model context uncertain') from error
            digests.append(self._digest(binding,DecisionQuery(trip['trip_id'],trip['version'],content_sha)))
        return digests
