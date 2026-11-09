"""Explicit internal Demo publication and original-message candidate reads."""
import json

from .codec import Conflict, Unavailable
from .collection import _candidate
from .extraction import ParsedEntry
from .model_v2 import origin_reference
from .policy_v2 import ProcessingSourcePolicyV2
from .policy_v3 import ResultSourcePolicyV3
from .postgres import encode
from .publication_result import VERSION_DEMO, is_demo_candidate, original_result
from .publication_store import PublicationTransaction


class _OriginalMessage:
    def __init__(self, *args, original, **kwargs):
        super().__init__(*args, **kwargs)
        self.original = original

    def _input(self, snapshot):
        messages = snapshot.messages
        if len(messages) != 1 or messages[0].receipt != self.original:
            raise Conflict('Demo extraction requires the exact original message')
        row = super()._input(snapshot)
        if row[5] != 'incremental':
            raise Conflict('Demo extraction requires an incremental original')
        return row


class _CandidateInput(_OriginalMessage, ProcessingSourcePolicyV2):
    pass


class _CandidateResult(_OriginalMessage, ResultSourcePolicyV3):
    result_version = VERSION_DEMO

    def _entries(self, raw, messages, policy):
        return tuple(ParsedEntry(parsed.entry, False) for parsed in super()._entries(raw, messages, policy)
                     if is_demo_candidate(parsed.entry))

    def encode_result(self, status, receipts):
        if any(row['status'] != 'candidate' for row in receipts):
            raise Conflict('Demo extraction cannot publish an active memory')
        return super().encode_result(status, receipts)


class DemoCandidates:
    """Use only from the trusted internal assembly with an explicit subject roster."""
    job_batch_version = None

    def __init__(self, collection, selected_subjects):
        if not isinstance(selected_subjects, frozenset) or not selected_subjects:
            raise ValueError('explicit internal Demo subjects required')
        self.collection = collection
        self.selected_subjects = selected_subjects

    def _lookup(self, context, message_id, run_id):
        if context.principal.subject not in self.selected_subjects:
            raise Unavailable('Demo candidate scope unavailable')
        stored = self._query_message(context, message_id)
        if stored is None or stored.receipt.run_id != run_id:
            raise Unavailable('original Demo message unavailable')
        head = context.send_status(stored.receipt.conversation_id).head
        if head is None or head.generation != stored.receipt.generation:
            raise Unavailable('original Demo conversation unavailable')
        return stored, head

    def _query_message(self, context, message_id):
        return context.query_message(message_id)

    def _binding(self, context, token, message_id, run_id):
        stored, _ = self._lookup(context, message_id, run_id)
        return stored, self.collection._binding(context, token)

    def _projection_available(self, tx):
        tx.require_live()
        return True

    def processing_policy(self, context, token, job_id, attempt_id, original_input,
                          prepared_input_sha256, *, message_id, run_id, max_payload_bytes):
        stored, (repository, principal, guard) = self._binding(context, token, message_id, run_id)
        extraction, _, _ = self.collection.resolve_collection(principal)
        return _CandidateInput(repository, principal, guard, job_id, attempt_id, original_input,
            prepared_input_sha256, extraction, max_payload_bytes=max_payload_bytes, original=stored.receipt)

    def publication_policy(self, context, token, job_id, attempt_id, original_input,
                           prepared_input_sha256, model_output, model_output_sha256, *,
                           message_id, run_id, max_payload_bytes, before_commit):
        stored, (repository, principal, guard) = self._binding(context, token, message_id, run_id)
        extraction, memory, _ = self.collection.resolve_collection(principal)
        return _CandidateResult(repository, principal, guard, job_id, attempt_id, original_input,
            prepared_input_sha256, extraction, max_payload_bytes=max_payload_bytes,
            model_output=model_output, model_output_sha256=model_output_sha256,
            memory_policy=memory, before_commit=before_commit, original=stored.receipt)

    def query_publication_in_context(self, context, token, job_id, attempt_id, *, message_id, run_id):
        stored, (repository, _, guard) = self._binding(context, token, message_id, run_id)
        with repository.transaction() as memory:
            tx = PublicationTransaction(memory)
            if not self._projection_available(tx):
                guard('demo_publication_absent')
                return b'null'
            row, _ = tx.output(job_id, attempt_id)
            if (len(row[4]) != 1 or row[4][0].receipt != stored.receipt
                    or self.job_batch_version is not None and json.loads(row[2])['version'] != self.job_batch_version):
                raise Unavailable('original Demo publication message differs')
            result = original_result(tx, job_id, attempt_id, expected_version=VERSION_DEMO)
            guard('demo_publication_receipt')
            return result if result is not None else b'null'

    def current(self, context, token, message_id, run_id, after_candidate_id=''):
        """Only the current candidates from this protected original MESSAGE/RUN."""
        stored, (repository, _, guard) = self._binding(context, token, message_id, run_id)
        with repository.transaction() as memory:
            tx = PublicationTransaction(memory)
            if not self._projection_available(tx):
                guard('demo_candidates_absent')
                return None
            tx.cur.execute('''SELECT i.item_id,o.job_id,o.attempt_id FROM cj_memory_item i
                JOIN cj_memory_history_origin o ON (o.scope,o.source_id,o.item_id)=(i.scope,i.source_id,i.item_id)
                JOIN cj_memory_source s ON (s.scope,s.source_id,s.version)=(i.scope,i.source_id,i.source_version)
                WHERE i.scope=%s AND i.status='candidate' AND i.extent='long_term'
                AND i.item_id>%s AND o.origin_refs = %s::jsonb
                AND s.authorized AND s.active AND NOT s.confirmed AND s.expires_at>clock_timestamp()
                AND (%s::text IS NULL OR EXISTS(
                    SELECT 1 FROM cj_memory_history_job j WHERE (j.scope,j.job_id,j.attempt_id)=(o.scope,o.job_id,o.attempt_id)
                    AND convert_from(j.batch,'UTF8')::jsonb->>'version'=%s))
                ORDER BY i.item_id LIMIT 51''',
                (tx.scope, after_candidate_id, json.dumps([origin_reference(stored)]),
                 self.job_batch_version, self.job_batch_version))
            rows = tx.cur.fetchall()
            values = []
            for item_id, job_id, attempt_id in rows[:50]:
                item = memory.detail(item_id)
                value = _candidate(item)
                if value['kind'] not in ('fact', 'preference'):
                    continue
                value['review'] = dict(job_id=job_id, attempt_id=attempt_id)
                values.append(value)
            data = encode(dict(memory_epoch=tx.epoch, candidates=values,
                next_after_candidate_id=rows[49][0] if len(rows) > 50 else None))
            if len(data) > 524288:
                raise Unavailable('Demo candidate projection exceeds bound')
            guard('demo_candidate_projection')
            return data
