"""Current API Memory/profile fence for rich undo; no historical value prefill.

The trusted host binds an actual Memory scope holder. Current profile identity
comes from native accepted events under the actual M/Memory locks. Neither
profile bytes nor an epoch DTO grant Trip write or historical PlanNow authority.
"""
from contextlib import contextmanager
import json

from .domain import Denied


class ApiRichUndoSources:
    def __init__(self, database, memory_holder):
        if memory_holder is None:
            raise Denied('actual API Memory holder required')
        self.database, self.memory_holder = database, memory_holder

    def _profile(self, message_context, origin):
        from cj_api.lio_exploration_profile import CONTEXT, decode_context
        message_context.check()
        if origin['message_scope'] != message_context.scope:
            raise Denied('current profile owner differs')
        basis = json.loads(origin['source'])
        reference = basis['calendar_basis']['fixed_bindings']['reference']
        with self.database.connect(message_context.scope) as db:
            row = db.execute('SELECT m.message_id,m.run_id,m.sequence,e.sequence,e.value '
                'FROM cj_message_receipt m JOIN cj_run_record r USING(scope,run_id) '
                'JOIN cj_run_event e USING(scope,run_id) WHERE m.scope=%s AND m.conversation_id=%s '
                "AND m.generation=%s AND r.status='completed' AND m.lio_wire_protocol='LIO-message.4' "
                "AND e.kind='effect_committed' AND e.value LIKE %s "
                'ORDER BY m.sequence DESC,e.sequence DESC LIMIT 1',
                (message_context.scope, reference['conversation_id'], reference['generation'], CONTEXT+'%')).fetchone()
        if row is None:
            raise Denied('current accepted planning profile unavailable')
        raw = row[4].removeprefix(CONTEXT)
        if len(raw.encode('utf8')) > 1_000_000:
            raise Denied('current planning profile exceeds its source byte bound')
        decode_context(raw)  # Persisted boundary shape; values never become undo permission.
        message_context.check()
        return row

    @contextmanager
    def hold(self, request, *, current, previous, active_origin, previous_origin, message_context):
        database, memory_holder = self.database, self.memory_holder
        message_context.check()
        with memory_holder.hold(message_context) as memory:
            profile = self._profile(message_context, active_origin)
            def check():
                if self.database is not database or self.memory_holder is not memory_holder:
                    raise Denied('current undo source binding changed')
                message_context.check()
                memory.check()
                if self._profile(message_context, active_origin) != profile:
                    raise Denied('current planning profile changed')
            check()
            yield check
            check()
