"""Protected committed-message snapshot, with no collection or dispatch grant."""
from cj_message.auth_boundary import Boundary
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cj_message.source import SourcePolicy, SourceQuery

from .codec import Source, SourceV2, Unavailable, encode, encode_v2


def read_committed_batch(boundary: Boundary, token: str, source: Source, mode: str) -> bytes:
    """Materialize an exact bounded interval within MESSAGE's fresh AUTH checks.

    Source is a trusted host's comparison value, never decoded request authority.
    This read does not establish history consent, hold a publication lease, persist
    data, or enable production_queue. #403 supplies the collection authority.
    """
    return _read(boundary, token, source, mode, modern_messages=False)


def read_committed_batch_v2(boundary: Boundary, token: str, source: SourceV2, mode: str) -> bytes:
    """Explicit V2 batch for the public protected mixed-version MESSAGE reader.

    New MESSAGE versions keep their original bytes and typed references as data;
    parsing them grants no travel/Trip write, history consent or model permission.
    """
    return _read(boundary, token, source, mode, modern_messages=True)


def read_enabled_batch(boundary: Boundary, token: str, query: 'SourceQuery',
                       policy: 'SourcePolicy') -> bytes:
    """Consume MESSAGE-SOURCE@1; only the installed policy can grant collection.

    Reenter this public seam for each later enqueue/extraction/publication phase.
    Returned bytes and parsed source fields cannot replace its current lease.
    """
    def materialize(context):
        def project(snapshot):
            source = SourceV2(snapshot.cursor, snapshot.source_version,
                              snapshot.withdrawal_epoch)
            return encode_v2(source, snapshot.messages, query.mode)

        return context.with_enabled_source(query, policy, project)

    return boundary.with_history_context(token, materialize)


def _read(boundary, token, source, mode, *, modern_messages):
    cursor = source.cursor

    def materialize(context):
        if context.scope != cursor.scope:
            raise Unavailable('source unavailable')
        history = context.trip_message_history if modern_messages else context.message_history
        rows, _ = history(
            cursor.conversation_id, cursor,
            limit=cursor.through - cursor.after,
        )
        # Existing codec bounds the interval and verifies exact original bytes.
        # Encoding finishes before Boundary's final fresh admission check.
        encoder = encode_v2 if modern_messages else encode
        return encoder(source, tuple(rows), mode)

    return boundary.with_history_context(token, materialize)
