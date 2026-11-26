"""Recent assistant replies in the answer context (W2-2, #1728).

The read-only answer path already gives the model the traveler's own recent
originals. Follow-ups such as "the second one" or "make it shorter" also need
what Lio said. With CJ_LIO_ASSISTANT_CONTEXT=1 the answer context interleaves
the visible reply of the most recent completed RUNs, each cut to a bounded
length, after the traveler message it answered.

Only replies to originals already in the context are read, so the source
references handed to the model-history fence stay exactly the same: a reply is
derived from its own original message. A reply is data the model wrote; it is
never a source for planning facts, saving or authority, and it is not added to
the planning or intake paths.

A reply may repeat saved Memory that was injected into its RUN. The erasure
fence only covers an item's source originals, so once this traveler has ever
paused, withdrawn or erased a Memory item, no earlier reply is added at all
(review of #1827; docs/memory.md: stopping use excludes later context). The
erasure fence rows are never deleted, so an erased-and-cleaned item still
counts. A read failure also adds no reply.
"""
from hashlib import sha256
import logging
import os

from psycopg import Error as DatabaseError

ASSISTANT_TURNS = 3
REPLY_CHARACTERS = 400
ELLIPSIS = '…'


def assistant_context_enabled():
    """Server switch; off unless explicitly set to 1."""
    value = os.environ.get('CJ_LIO_ASSISTANT_CONTEXT', '0')
    if value not in ('0', '1'):
        raise ValueError('explicit assistant context switch value required')
    return value == '1'


def shorten(text, limit=REPLY_CHARACTERS):
    text = text.strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + ELLIPSIS


def memory_ever_withdrawn(database, binding):
    """True when any Memory item of this scope was paused, withdrawn or erased, or the read fails."""
    try:
        with database.connect(binding.scope) as db:
            disabled, erased = db.execute(
                "SELECT EXISTS(SELECT 1 FROM cj_memory_item WHERE scope=%s AND status IN ('disabled','withdrawn')),"
                'EXISTS(SELECT 1 FROM cj_memory_erasure_fence WHERE scope_digest=%s)',
                (binding.scope, sha256(binding.scope.encode()).hexdigest())).fetchone()
        return bool(disabled or erased)
    except DatabaseError:
        logging.getLogger('cj_usage.audit').info('LIO_ASSISTANT_CONTEXT_SKIPPED reason=memory_state_unavailable')
        return True


def read_replies(database, binding, message_ids):
    """Visible text of completed RUNs answering these originals, in this conversation only."""
    if not message_ids or memory_ever_withdrawn(database, binding):
        return {}
    with database.connect(binding.scope) as db:
        rows = db.execute(
            'SELECT m.message_id,e.value FROM cj_message_receipt m JOIN cj_run_record r USING(scope,run_id) '
            'JOIN cj_run_event e USING(scope,run_id) WHERE m.scope=%s AND m.conversation_id=%s '
            "AND m.generation=%s AND m.sequence<%s AND m.message_id=ANY(%s) AND r.status='completed' "
            "AND e.kind='text_delta' ORDER BY m.sequence,e.sequence",
            (binding.scope, binding.conversation_id, binding.generation, binding.message_sequence,
             list(message_ids))).fetchall()
    replies = {}
    for message_id, value in rows:
        replies[message_id] = replies.get(message_id, '') + value
    return replies


def interleave(history, texts, refs, replies, *, turns=ASSISTANT_TURNS):
    """Prior traveler texts with the replies to the last few, then the current text.

    history: messages before the traveler's turns (for example a Memory system
    message); texts: prior originals oldest first plus the current text last;
    refs: the source references of the prior originals, aligned with texts[:-1].
    """
    prior, current = texts[:-1], texts[-1]
    if len(prior) != len(refs):
        raise ValueError('aligned original references required')
    recent = {ref['message_id'] for ref in refs[-turns:]} if turns else set()
    messages = list(history)
    for text, ref in zip(prior, refs):
        messages.append(dict(role='user', content=text))
        reply = replies.get(ref['message_id'])
        if ref['message_id'] in recent and reply and reply.strip():
            messages.append(dict(role='assistant', content=shorten(reply)))
    messages.append(dict(role='user', content=current))
    return messages
