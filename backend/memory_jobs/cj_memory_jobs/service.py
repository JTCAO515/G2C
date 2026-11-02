"""History consent/queue composition over the original protected MESSAGE boundary."""
from cj_auth.interfaces import AdmissionStatus
from cj_message.auth_boundary import AccessBlocked, IdentityChanged
from cj_message.domain import CommitUnknown as MessageCommitUnknown
from cj_memory.domain import CommitUnknown as MemoryCommitUnknown

from .codec import Conflict, SourceV2, Unavailable, encode_v2, job_identity, pg_identity
from .consent import ConsentAction, EnqueueCommand
from .postgres import Transaction, encode
from .source_policy import SourcePolicy


class OperationWithheld(Exception):
    def __init__(self, operation_id, attempt_id=None):
        super().__init__('history operation outcome unavailable')
        self.operation_id, self.attempt_id = operation_id, attempt_id
        self.commit_possible = True
        self.recovery = 'reconcile_original'


class Service:
    def __init__(self, boundary, resolve_repository):
        self.boundary, self.resolve_repository = boundary, resolve_repository

    def source_policy(self,context,token):
        """One fresh public composition binding, with no new Boundary/read grant."""
        repository,principal,guard=self._binding(context,token)
        return SourcePolicy(repository,principal,guard)

    def _invoke(self, token, operation, request_id, version):
        if request_id is None:
            return self.boundary.with_history_context(token,operation)
        import json
        def project(context):
            return encode(dict(version=version,request_id=request_id,
                               result=json.loads(operation(context))))
        return self.boundary.with_history_context(token,project)

    def _binding(self, context, token):
        principal, scope = context.principal, context.scope
        repository = self.resolve_repository(principal,scope)
        if repository.scope != scope:
            raise Unavailable('history binding unavailable')
        checker = self.boundary.checker

        def guard(stage):
            # Recheck the SAME canonical checker/identity, never resolve a new actor.
            current = checker.check(token)
            if current.status is not AdmissionStatus.ALLOWED:
                raise AccessBlocked(current,stage)
            if current.principal != principal or repository.scope != scope:
                raise IdentityChanged(stage)

        return repository, principal, guard

    def apply_consent(self, token, original, *, request_id=None):
        action = ConsentAction.parse(original)
        possible = False

        def apply(context):
            nonlocal possible
            repository, _, guard = self._binding(context,token)
            # Historical replay releases MEMORY before asking MESSAGE for a head.
            with repository.transaction() as memory:
                tx = Transaction(memory)
                old = tx.action(action.action_id)
                if old is not None:
                    tx.require_live()
                    old = tx.action(action.action_id)
                    if old is None:
                        raise Unavailable('original history action unavailable')
                    if old[0] != original:
                        raise Conflict('original history action differs')
                    possible = True
                    guard('consent_replay')
                    return old[1]
            head = context.send_status(action.conversation_id).head
            if head is None:
                raise Unavailable('history conversation unavailable')
            with repository.transaction() as memory:
                tx = Transaction(memory)
                tx.require_live(initialize=True)
                result = tx.apply_consent(action,head)
                guard('consent_precommit')
                possible = True
            return result

        try:
            return self._invoke(token,apply,request_id,'MEMORY-HISTORY-result@1')
        except (MemoryCommitUnknown,MessageCommitUnknown) as error:
            raise OperationWithheld(action.action_id) from error
        except (AccessBlocked,IdentityChanged) as error:
            if possible:
                raise OperationWithheld(action.action_id) from error
            raise

    def query_consent_action(self, token, action_id, *, request_id=None):
        pg_identity(action_id,4096)
        def query(context):
            repository, _, guard = self._binding(context,token)
            with repository.transaction() as memory:
                tx = Transaction(memory)
                tx.require_live()
                old = tx.action(action_id)
                guard('consent_query')
                # No absence-to-resend or automatic apply is provided.
                return old[1] if old is not None else b'null'
        return self._invoke(token,query,request_id,'MEMORY-HISTORY-result@1')

    def settings(self, token, conversation_id, *, request_id=None):
        pg_identity(conversation_id,256)
        def query(context):
            repository, _, guard = self._binding(context,token)
            head = context.send_status(conversation_id).head
            if head is None:
                raise Unavailable('history conversation unavailable')
            with repository.transaction() as memory:
                result = Transaction(memory).settings(conversation_id,head)
                guard('history_settings')
            return result
        return self._invoke(token,query,request_id,'MEMORY-HISTORY-result@1')

    def enqueue(self, token, original, *, request_id=None):
        command = EnqueueCommand.parse(original)
        return self._enqueue_command(token,command,request_id=request_id)

    def enqueue_serialized(self, token, original):
        """Trusted automatic intake; one current account basis at a time.

        The existing JOBS@1 HTTP path keeps its original per-stream contract.
        This adds no dispatcher, retry or permit to renew an original attempt.
        """
        return self._enqueue_command(token,EnqueueCommand.parse(original),request_id=None,serialized=True)

    def enqueue_ending(self, token, original, *, request_id=None):
        from .ending import EndingCommand
        return self._enqueue_command(token,EndingCommand.parse(original),request_id=request_id,ending=True)

    def _enqueue_command(self, token, command, *, request_id, ending=False,serialized=False):
        original=command.raw
        query,job_id,attempt_id = command.query,command.job_id,command.attempt_id
        policy = None

        def apply(context):
            nonlocal policy
            repository, principal, guard = self._binding(context,token)
            invalid_originals=set()
            if serialized:
                # Detached comparisons only; release MEMORY before public
                # MESSAGE reads and the normal MESSAGE -> MEMORY acquisition.
                with repository.transaction() as memory:
                    tx=Transaction(memory);tx.require_live()
                    originals=tx.current_unresolved()
                for row in originals:
                    cursor=row[3].cursor
                    head=context.send_status(cursor.conversation_id).head
                    if head is None or (head.generation,head.epoch)!=(cursor.generation,cursor.epoch):
                        invalid_originals.add(row[0].job_id)
            policy = SourcePolicy(repository,principal,guard)

            def persist(snapshot):
                if serialized and any(row[0].job_id!=job_id and row[0].job_id not in invalid_originals
                                      for row in policy.transaction.current_unresolved()):
                    raise Conflict('another original collection owns the current account basis')
                source = SourceV2(snapshot.cursor,snapshot.source_version,snapshot.withdrawal_epoch)
                return policy.transaction.enqueue(source,snapshot.messages,query.mode,
                    job_id,attempt_id,original).encode()

            if ending:
                from .ending_source import with_ending_source
                return with_ending_source(context,command.segment,policy,persist,
                    probe_policy=SourcePolicy(repository,principal,guard))
            return context.with_enabled_source(query,policy,persist)

        try:
            return self._invoke(token,apply,request_id,'MEMORY-JOBS-result@1')
        except (MemoryCommitUnknown,MessageCommitUnknown) as error:
            raise OperationWithheld(job_id,attempt_id) from error
        except (AccessBlocked,IdentityChanged) as error:
            if policy is not None and policy.commit_attempted:
                raise OperationWithheld(job_id,attempt_id) from error
            raise

    def query_original(self, token, job_id, attempt_id, *, request_id=None):
        """Fresh account-only status read; disabled/stale sources need no renewal."""
        job_identity(job_id); job_identity(attempt_id)
        def query(context):
            repository, _, guard = self._binding(context,token)
            with repository.transaction() as memory:
                tx = Transaction(memory)
                tx.require_live()
                result = tx.job(job_id,attempt_id)[0].encode()
                guard('history_query')
            return result
        return self._invoke(token,query,request_id,'MEMORY-JOBS-result@1')

    def transition(self, token, job_id, attempt_id, target, *, candidate=None):
        """Start/complete need a new current source lease; recovery never dispatches."""
        job_identity(job_id); job_identity(attempt_id)
        policy, possible = None, False

        def apply(context):
            nonlocal policy, possible
            repository, principal, guard = self._binding(context,token)
            # Detached original bytes are only comparison data. Release MEMORY
            # before the subsequent MESSAGE → MEMORY acquisition.
            with repository.transaction() as memory:
                tx = Transaction(memory)
                tx.require_live()
                row = tx.job(job_id,attempt_id)
                if target in ('unknown','cancelled','failed'):
                    result = tx.transition(job_id,attempt_id,target).encode()
                    guard('history_metadata_precommit')
                    possible = True
                    return result
            mode = row[5]
            policy = SourcePolicy(repository,principal,guard)

            def persist(snapshot):
                current = SourceV2(snapshot.cursor,snapshot.source_version,snapshot.withdrawal_epoch)
                if encode_v2(current,snapshot.messages,mode) != row[2]:
                    raise Conflict('original history source differs')
                return policy.transaction.transition(job_id,attempt_id,target,candidate=candidate).encode()

            from .ending import with_original_source
            return with_original_source(context,row,policy,persist,
                probe_policy=SourcePolicy(repository,principal,guard))

        try:
            return self.boundary.with_history_context(token,apply)
        except (MemoryCommitUnknown,MessageCommitUnknown) as error:
            raise OperationWithheld(job_id,attempt_id) from error
        except (AccessBlocked,IdentityChanged) as error:
            if possible or (policy is not None and policy.commit_attempted):
                raise OperationWithheld(job_id,attempt_id) from error
            raise
