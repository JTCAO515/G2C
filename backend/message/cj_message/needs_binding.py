"""Trusted local original-message NEEDS binding; no client scope/version input."""
import hashlib
import json
from cj_needs.domain import decode, validate_fields, identifier, InvalidInput
from .domain import Unavailable


def needs_scope_for(message_scope):
    return 'n' + hashlib.sha256(message_scope.encode('utf-8')).hexdigest()


def capture(cursor, message_scope, stored):
    """Called only on first insert inside the original receipt/outbox transaction.

    The caller already validated original MESSAGE bytes and holds the MESSAGE scope
    lock. Local selection writers must take that same lock. No implicit binding is
    added to existing messages or to plain non-trip messages.
    """
    if json.loads(stored.raw)['creation_intent'] != 'consider_trip':
        return
    r = stored.receipt
    needs_scope = needs_scope_for(message_scope)
    cursor.execute('SELECT needs_scope,needs_id FROM cj_message_needs_selection '
                   'WHERE message_scope=%s AND conversation_id=%s AND generation=%s',
                   (message_scope,r.conversation_id,r.generation))
    selected = cursor.fetchone()
    if selected is None or selected[0] != needs_scope:
        raise Unavailable('required NEEDS selection unavailable')
    try: needs_id = identifier(selected[1])
    except InvalidInput: raise Unavailable('invalid NEEDS selection') from None
    cursor.execute('SELECT pg_advisory_xact_lock_shared(public.cj_needs_fence_key(%s))',(needs_scope,))
    cursor.execute('SELECT n.version,n.content,h.content,h.source_kind FROM cj_needs_record n '
                   'JOIN cj_needs_revision h ON (h.scope,h.needs_id,h.version)=(n.scope,n.needs_id,n.version) '
                   'WHERE n.scope=%s AND n.needs_id=%s',(needs_scope,needs_id))
    row = cursor.fetchone()
    if row is None or type(row[0]) is not int or row[0] < 1 or row[3] != 'user_provided':
        raise Unavailable('NEEDS original revision unavailable')
    content = bytes(row[1])
    if content != bytes(row[2]): raise Unavailable('NEEDS revision mismatch')
    try: validate_fields(decode(content), complete=True)
    except (ValueError, TypeError, UnicodeError):
        raise Unavailable('invalid NEEDS content') from None
    cursor.execute('INSERT INTO cj_message_needs_binding '
                   '(message_scope,message_id,run_id,needs_scope,needs_id,needs_version,content_sha256) '
                   'VALUES (%s,%s,%s,%s,%s,%s,%s)',
                   (message_scope,r.message_id,r.run_id,needs_scope,needs_id,row[0],hashlib.sha256(content).hexdigest()))
