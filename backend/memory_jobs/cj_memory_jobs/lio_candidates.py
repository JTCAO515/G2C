"""The internal Lio roster can collect one original turn as Pub4 candidates."""
from dataclasses import asdict
import json

from cj_memory.domain import CommitUnknown as MemoryCommitUnknown
from cj_message.auth_boundary import AccessBlocked, IdentityChanged
from cj_message.domain import CommitUnknown as MessageCommitUnknown
from cj_message.source import SourceQuery

from . import lio_batch, model_v2
from .codec import Conflict, SourceV2
from .demo_candidates import DemoCandidates, _CandidateInput, _CandidateResult
from .postgres import encode
from .publication_store import PublicationTransaction
from .service import OperationWithheld
from .source_policy import SourcePolicy


class _LioSource:
    _encode_batch = staticmethod(lio_batch.encode_batch)

    def __init__(self, *args, lio_query, **kwargs):
        super().__init__(*args, **kwargs)
        self.lio_query = lio_query

    def _require_source(self, tx, query):
        if query != self.lio_query:
            raise Conflict('original Lio source range differs')


class _Intake(_LioSource, SourcePolicy):
    transaction_type = PublicationTransaction
    initialize = True


class _Input(_LioSource, _CandidateInput):
    pass


class _Result(_LioSource, _CandidateResult):
    pass


class LioCandidates(DemoCandidates):
    """Explicit deployment wiring only; no consent for broader history."""
    job_batch_version = lio_batch.VERSION

    def _query_message(self, context, message_id):
        return context.query_lio_message(message_id)

    def _projection_available(self, tx):
        tx.cur.execute('SELECT erased FROM cj_memory_history_fence WHERE scope_digest=%s',
                       (tx.scope_digest,))
        if tx.cur.fetchone() is None:
            return False
        return super()._projection_available(tx)

    def _source(self, context, token, message_id, run_id):
        stored, head = self._lookup(context, message_id, run_id)
        receipt = stored.receipt
        query = SourceQuery(receipt.conversation_id, receipt.generation, head.epoch,
                            receipt.sequence - 1, receipt.sequence, 1, 1)
        repository, principal, guard = self.collection._binding(context, token)
        return stored, query, repository, principal, guard

    def prepare(self, token, message_id, run_id, *, max_payload_bytes):
        """Register once and return the original input for B's metered dispatch."""
        policy = identities = None

        def operation(context):
            nonlocal policy, identities
            stored, query, repository, principal, guard = self._source(context, token, message_id, run_id)
            extraction, _, _ = self.collection.resolve_collection(principal)
            policy = _Intake(repository, principal, guard, lio_query=query)

            def stage(snapshot):
                if len(snapshot.messages) != 1 or snapshot.messages[0].receipt != stored.receipt:
                    raise Conflict('original Lio turn differs')
                source = SourceV2(snapshot.cursor, snapshot.source_version, snapshot.withdrawal_epoch)
                message = snapshot.messages[0]
                identities = lio_batch.job_ids(source, message)
                tx = policy.transaction
                status = tx.enqueue_lio(source, message)
                prepared = None
                if status.state == 'pending':
                    raw, count = model_v2.prepared(tx, snapshot, extraction, query.mode,
                                                   max_payload_bytes=max_payload_bytes)
                    if not count:
                        status = tx.transition(*identities, 'cancelled')
                    else:
                        status = tx.transition(*identities, 'inflight')
                        prepared = raw.decode('utf-8')
                return encode(dict(job_id=status.job_id, attempt_id=status.attempt_id,
                                   state=status.state, source=asdict(query), prepared_input_utf8=prepared))

            return context.with_enabled_source(query, policy, stage)

        try:
            return self.collection.boundary.with_history_context(token, operation)
        except (MemoryCommitUnknown, MessageCommitUnknown, AccessBlocked, IdentityChanged) as error:
            if policy is not None and policy.commit_attempted:
                raise OperationWithheld(*identities) from error
            raise

    def processing_policy(self, context, token, job_id, attempt_id, original_input,
                          prepared_input_sha256, *, message_id, run_id, max_payload_bytes):
        stored, query, repository, principal, guard = self._source(context, token, message_id, run_id)
        extraction, _, _ = self.collection.resolve_collection(principal)
        return _Input(repository, principal, guard, job_id, attempt_id, original_input,
                      prepared_input_sha256, extraction, max_payload_bytes=max_payload_bytes,
                      original=stored.receipt, lio_query=query)

    def publication_policy(self, context, token, job_id, attempt_id, original_input,
                           prepared_input_sha256, model_output, model_output_sha256, *,
                           message_id, run_id, max_payload_bytes, before_commit):
        stored, query, repository, principal, guard = self._source(context, token, message_id, run_id)
        extraction, memory, _ = self.collection.resolve_collection(principal)
        return _Result(repository, principal, guard, job_id, attempt_id, original_input,
                       prepared_input_sha256, extraction, max_payload_bytes=max_payload_bytes,
                       model_output=model_output, model_output_sha256=model_output_sha256,
                       memory_policy=memory, before_commit=before_commit,
                       original=stored.receipt, lio_query=query)

    def transition_original_in_context(self, context, token, job_id, attempt_id, target, *,
                                       message_id, run_id):
        """Stop original metadata only. No provider retry or source renewal."""
        if target not in ('cancelled', 'failed', 'unknown'):
            raise ValueError('nonproductive original Lio transition required')
        stored, (repository, _, guard) = self._binding(context, token, message_id, run_id)
        with repository.transaction() as memory:
            tx = PublicationTransaction(memory)
            tx.require_live()
            row = tx.job(job_id, attempt_id)
            if (json.loads(row[2])['version'] != lio_batch.VERSION
                    or row[4][0].receipt != stored.receipt):
                raise Conflict('original Lio job differs')
            result = tx.transition(job_id, attempt_id, target).encode()
            guard('lio_original_transition')
            return result
