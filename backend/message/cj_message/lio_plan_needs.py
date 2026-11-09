"""Bind one planning revision to an admitted Lio message and its original RUN."""
import json

from cj_needs.domain import Command as NeedsCommand
from cj_needs.postgres import apply_on_cursor

from .demo_dialogue import LIO_VERSION, _identity, _json
from .domain import Unavailable
from .needs_binding import capture_revision, needs_scope_for


BOUND_EFFECT = 'lio_plan_needs_bound'
EDIT_BOUND_EFFECT = 'lio_edit_needs_bound'


def _origin_args(binding):
    return (binding.scope, binding.conversation_id, binding.generation, binding.message_id,
            binding.run_id, binding.message_sequence, LIO_VERSION)


def lio_needs_id(scope, conversation_id):
    return 'lio-' + _identity(scope, conversation_id)


def original_needs(cursor, binding):
    """Return (NEEDS id, version, digest) for a committed Lio planning registration."""
    return cursor.execute(
        'SELECT b.needs_id,b.needs_version,b.content_sha256 FROM cj_message_receipt m '
        'JOIN cj_message_needs_binding b ON (b.message_scope,b.message_id,b.run_id)='
        '(m.scope,m.message_id,m.run_id) '
        'WHERE m.scope=%s AND m.conversation_id=%s AND m.generation=%s AND m.message_id=%s '
        'AND m.run_id=%s AND m.sequence=%s AND m.demo_dialogue_protocol=%s '
        'AND b.needs_scope=%s AND b.needs_id=%s '
        'AND EXISTS(SELECT 1 FROM cj_run_event e WHERE (e.scope,e.run_id)=(m.scope,m.run_id) '
        'AND e.kind=%s AND e.value IN (%s,%s))',
        (*_origin_args(binding), needs_scope_for(binding.scope), lio_needs_id(binding.scope, binding.conversation_id),
         'effect_committed', BOUND_EFFECT, EDIT_BOUND_EFFECT)).fetchone()


def _require_original(cursor, binding, original):
    origin = cursor.execute(
        'SELECT input_sha256 FROM cj_message_receipt WHERE scope=%s AND conversation_id=%s '
        'AND generation=%s AND message_id=%s AND run_id=%s AND sequence=%s '
        'AND demo_dialogue_protocol=%s', _origin_args(binding)).fetchone()
    if origin != (original.receipt.input_sha256,):
        raise Unavailable('original Lio planning authority unavailable')


def attach_existing(cursor, binding, original):
    """Bind a replacement to the unchanged, current Lio NEEDS revision."""
    _require_original(cursor, binding, original)
    capture_revision(cursor, binding.scope, binding.message_id, binding.run_id,
                     lio_needs_id(binding.scope, binding.conversation_id), None)


def attach(cursor, binding, original, fields, references):
    """Write within the original RUN transaction while its MESSAGE lease is held."""
    _require_original(cursor, binding, original)
    scope = needs_scope_for(binding.scope)
    needs_id = lio_needs_id(binding.scope, binding.conversation_id)
    cursor.execute("SELECT set_config('cj.needs_runtime_abi','NEEDS-MANUAL-RUNTIME@1',true)")
    cursor.execute('SELECT pg_catalog.pg_advisory_xact_lock(public.cj_needs_fence_key(%s))', (scope,))
    cursor.execute('INSERT INTO cj_needs_scope(scope) VALUES(%s) ON CONFLICT DO NOTHING', (scope,))
    current = cursor.execute('SELECT version,content FROM cj_needs_record WHERE scope=%s AND needs_id=%s',
                             (scope, needs_id)).fetchone()
    if current is not None and 'fixed_items' in fields:
        previous = json.loads(bytes(current[1])).get('fixed_items', [])
        retained = {item['item_id'] for item in previous}
        fields = dict(fields, fixed_items=[*previous, *(item for item in fields['fixed_items']
                                                      if item['item_id'] not in retained)])
    source = [*references, dict(conversation_id=binding.conversation_id, generation=binding.generation,
        message_id=binding.message_id, sequence=binding.message_sequence,
        input_sha256=original.receipt.input_sha256)]
    command = NeedsCommand(_json(dict(
        action_id='lio-' + _identity(binding.scope, binding.run_id), needs_id=needs_id,
        expected_version=current[0] if current else 0,
        source=dict(kind='manual', text='Original Lio sources ' + _json(source).decode()),
        changes=fields)))
    revision = apply_on_cursor(cursor, scope, command)
    capture_revision(cursor, binding.scope, binding.message_id, binding.run_id,
                     revision.needs_id, revision.version)
