"""Protected committed-message snapshot, with no collection or dispatch grant."""
from cj_message.auth_boundary import Boundary

from .codec import Source, Unavailable, encode


def read_committed_batch(boundary: Boundary, token: str, source: Source, mode: str) -> bytes:
    """Materialize an exact bounded interval within MESSAGE's fresh AUTH checks.

    Source is a trusted host's comparison value, never decoded request authority.
    This read does not establish history consent, hold a publication lease, persist
    data, or enable production_queue. #403 supplies the collection authority.
    """
    cursor = source.cursor

    def materialize(context):
        if context.scope != cursor.scope:
            raise Unavailable('source unavailable')
        rows, _ = context.message_history(
            cursor.conversation_id, cursor,
            limit=cursor.through - cursor.after,
        )
        # Existing codec bounds the interval and verifies exact original bytes.
        # Encoding finishes before Boundary's final fresh admission check.
        return encode(source, tuple(rows), mode)

    return boundary.with_history_context(token, materialize)
