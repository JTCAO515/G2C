"""Compose Lio candidates with the host's existing synthetic Memory policy."""
from datetime import datetime, timezone

from cj_memory.postgres import Repository
from cj_memory_jobs.codec import Unavailable
from cj_memory_jobs.collection import CollectionService
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.lio_candidates import LioCandidates


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
                          if slot.collection_allowed and slot.kind in ('fact', 'preference'))
        if not allowed_subjects or not slots or 'long_term' not in profile.extents or profile.expires_at <= datetime.now(timezone.utc):
            raise Unavailable('Lio memory collection unavailable')

        def allowed(entry):
            return entry.extent == 'long_term' and entry.kind == profile.slots[entry.slot].kind

        # This channel produces candidates only. An explicit action is the sole
        # authority for promoting an item, even when the quote is verbatim.
        extraction = CollectionPolicy(allowed_subjects, slots, 4, 500, allowed, lambda entry, rows: False)
        return extraction, configuration.policy(principal.subject), lambda entry: (None, None)

    service = CollectionService(boundary, repository, collection)
    return LioCandidates(service, subjects)
