"""Compose Lio candidates with the host's existing synthetic Memory policy."""
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
from types import MappingProxyType

from psycopg import Error as DatabaseError

from cj_agent.provider import ProviderFailed, ProviderUnknown
from cj_memory.domain import CommitUnknown as MemoryCommitUnknown
from cj_memory.local import LocalMemoryProfile
from cj_memory.postgres import Repository
from cj_memory_jobs.codec import Conflict, Unavailable
from cj_memory_jobs.collection import CollectionService
from cj_memory_jobs.extraction import CollectionPolicy, CollectionUnavailable, InvalidExtraction
from cj_memory_jobs.lio_candidates import LioCandidates
from cj_memory_jobs.service import OperationWithheld
from cj_message.domain import CommitUnknown as MessageCommitUnknown
from cj_message.source import SourceQuery
from cj_usage.background_exit import ModelInput
from cj_usage.metered_exit import BudgetExceeded, BudgetUnknown
from .lio_memory_preferences import PREFERENCE_SLOTS, allows_pilot_preference_write, supported_preference


_LOGGER = logging.getLogger(__name__)


class _PilotMemoryProfile(LocalMemoryProfile):
    def content_allowed(self, command, original):
        return (super().content_allowed(command, original)
                and allows_pilot_preference_write(command))


def pilot_write_configuration(configuration, subjects):
    profiles = dict(configuration.collection.profiles)
    for subject in subjects:
        profile = profiles[subject]
        profiles[subject] = _PilotMemoryProfile(profile.subjects, profile.slots, profile.extents,
                                               profile.context_ids, profile.expires_at)
    collection = replace(configuration.collection, profiles=MappingProxyType(profiles))
    return replace(configuration, collection=collection)


def lio_candidates(database, boundary, subjects, configuration):
    def repository(principal, scope):
        if principal.subject not in subjects:
            raise Unavailable('Lio memory owner unavailable')
        return Repository(lambda: database.connect(scope), scope, typed_context=True,
                          transaction_binder=lambda connection, cursor: connection.bind_scope(cursor))

    def collection(principal):
        profile = configuration.collection.profiles[principal.subject]
        allowed_subjects = profile.subjects & {'self'}
        slots = frozenset(name for name, slot in profile.slots.items()
                          if name in PREFERENCE_SLOTS and slot.collection_allowed and slot.kind == 'preference')
        if not allowed_subjects or not slots or 'long_term' not in profile.extents or profile.expires_at <= datetime.now(timezone.utc):
            raise Unavailable('Lio memory collection unavailable')

        def allowed(entry):
            return entry.extent == 'long_term'

        # This channel produces candidates only. An explicit action is the sole
        # authority for promoting an item, even when the quote is verbatim.
        extraction = CollectionPolicy(allowed_subjects, slots, 4, 500, allowed, lambda entry, rows: False)
        return extraction, configuration.policy(principal.subject), lambda entry: (None, None)

    service = CollectionService(boundary, repository, collection)
    return LioCandidates(service, subjects, original_allows=supported_preference)


class LioMemoryExtraction:
    """One separately metered extraction on the admitted original Lio RUN."""

    def __init__(self, database, candidates, credential):
        self.database = database
        self.candidates = candidates
        self.credential = credential

    def extract(self, worker, binding):
        token = self.credential()
        coordinates = dict(message_id=binding.message_id, run_id=binding.run_id)
        options = dict(**coordinates, max_payload_bytes=32768)
        try:
            original = json.loads(self.candidates.prepare(token, **options))
        except (Conflict, Unavailable, OperationWithheld, MemoryCommitUnknown, MessageCommitUnknown, DatabaseError) as error:
            _record_hold('prepare', error)
            return None
        prepared = original['prepared_input_utf8']
        if prepared is None:
            # A consumed or uncertain original never yields model bytes again.
            return None
        prepared = prepared.encode('utf-8')
        digest = sha256(prepared).hexdigest()
        job, attempt = original['job_id'], original['attempt_id']
        source = SourceQuery(**original['source'])

        def hold(target):
            try:
                self._owned(token, lambda context: self.candidates.transition_original_in_context(
                    context, token, job, attempt, target, **coordinates))
            except (Conflict, Unavailable, OperationWithheld, MemoryCommitUnknown, MessageCommitUnknown, DatabaseError) as error:
                _record_hold('metadata', error)

        def source_bytes(context):
            policy = self.candidates.processing_policy(context, token, job, attempt, prepared, digest, **options)
            return context.with_enabled_source(source, policy, lambda snapshot: policy.with_input(snapshot, bytes))

        try:
            actual = self._owned(token, source_bytes)
            payload = ModelInput.parse(actual)
            messages = [dict(role=role, content=content) for role, content in payload.messages]
            output = ''.join(worker._registered_stream(binding, 'memory.lio_extract.0', 'memory.lio_extract.1',
                                                        (messages, payload.system, worker.provider))).encode('utf-8')
            deadline = worker.budget_exit.prepare_publication(binding)
        except (BudgetExceeded, ProviderFailed) as error:
            _record_hold('model', error)
            hold('failed')
            return None
        except (ProviderUnknown, BudgetUnknown, Unavailable, Conflict, OperationWithheld,
                MemoryCommitUnknown, MessageCommitUnknown, DatabaseError) as error:
            _record_hold('model', error)
            hold('unknown')
            return None

        def publish():
            # Completing the answer uses its original Memory snapshot. Candidate
            # writes advance the Memory epoch and therefore happen after that check.
            def check_answer():
                (answer, _), = self.database.run_repository(binding.scope).lio_timeline((binding,))
                if answer is None or answer.status != 'completed':
                    raise Conflict('original Lio answer was not completed')
                deadline()

            def write(context):
                policy = self.candidates.publication_policy(context, token, job, attempt, prepared, digest,
                    output, sha256(output).hexdigest(), before_commit=check_answer, **options)
                return context.with_enabled_source(source, policy, policy.apply_original_result)

            try:
                self._owned(token, write)
            except (BudgetExceeded, InvalidExtraction, CollectionUnavailable, Conflict, Unavailable,
                    OperationWithheld, MemoryCommitUnknown, MessageCommitUnknown, DatabaseError) as error:
                _record_hold('publication', error)
                try:
                    receipt = self._owned(token, lambda context: self.candidates.query_publication_in_context(
                        context, token, job, attempt, **coordinates))
                except (Conflict, Unavailable, OperationWithheld, MemoryCommitUnknown, MessageCommitUnknown, DatabaseError) as read_error:
                    _record_hold('receipt', read_error)
                    return
                if receipt == b'null':
                    hold('unknown')

        return publish

    def _owned(self, token, operation):
        return self.candidates.collection.boundary.with_history_context(token, operation)


def _record_hold(stage, error):
    _LOGGER.warning('lio_memory_withheld stage=%s error=%s', stage, type(error).__name__)
