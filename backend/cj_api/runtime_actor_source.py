"""DUT observation from its current original M frame, before the actor RUN.

The canonical M lock remains outside all actor RUN transactions. No Memory
snapshot is reconstructed and no input can replace a missing original source.
"""
from dataclasses import dataclass
from hashlib import sha256

from cj_message.demo_dialogue import LIO_VERSION_V4
from cj_run.core import Binding
from cj_strict_json import compact
from runtime_adapter.contract import Unavailable

from .lio_dialogue_routes import _message
from .lio_exploration_routes import _presentation, merged_presentation


@dataclass(frozen=True)
class DutProjection:
    context: object
    page: object
    states: tuple
    history: tuple


class ActorDutSource:
    def __init__(self, boundary, database):
        self.boundary, self.database = boundary, database

    def use(self, token, message_id, history, operation):
        """Call operation(source_bytes, check) only inside the original M lease.

        This is a synchronous bounded actor step in an exclusive C window. It
        holds M before RUN, including provider send and result publication, so
        deletion cannot race a copied public-history cache into a new call.
        """
        if len(history) > 8:
            raise Unavailable('ACTOR_DUT_HISTORY_INCOMPLETE')
        def exact(source, check, projection):
            if list(projection.history) != history:
                raise Unavailable('ACTOR_DUT_HISTORY_CHANGED')
            return operation(source, check)
        return self.observe(token, message_id, exact)

    def observe(self, token, message_id, operation):
        """Project current native state only while its original M lease is held."""
        def read(context):
            def project():
                original = context.query_lio_message(message_id)
                if original is None:
                    raise Unavailable('ACTOR_DUT_ORIGINAL_UNAVAILABLE')
                receipt = original.receipt
                def snapshot():
                    context.require_lio_projection()
                    current = context.query_lio_message(message_id)
                    if current != original:
                        raise Unavailable('ACTOR_DUT_ORIGINAL_CHANGED')
                    page = context.lio_exploration_timeline(receipt.conversation_id, None)
                    if (page.generation != receipt.generation or page.next_before is not None
                            or not 1 <= len(page.messages) <= 5
                            or tuple(item.sequence for item in page.messages) != tuple(range(1, receipt.sequence+1))
                            or page.messages[-1].message_id != message_id):
                        raise Unavailable('ACTOR_DUT_HISTORY_INCOMPLETE')
                    bindings = [Binding(context.scope, page.conversation_id, page.generation,
                        item.message_id, item.run_id, item.sequence) for item in page.messages]
                    states = self.database.run_repository(context.scope).lio_timeline(bindings)
                    # A public transcript cache is not permission to recreate
                    # erased original model input in a fresh actor operation.
                    with self.database.connect(context.scope) as connection:
                        connection.execute('SET TRANSACTION READ ONLY')
                        erased = connection.execute('SELECT 1 FROM cj_run_metered_operation '
                            'WHERE scope=%s AND run_id=ANY(%s) AND input_bytes IS NULL LIMIT 1',
                            (context.scope, [binding.run_id for binding in bindings])).fetchone()
                    if erased is not None:
                        raise Unavailable('ACTOR_DUT_ORIGINAL_PAYLOAD_ERASED')
                    shown = []
                    for item, (state, expired) in zip(page.messages, states, strict=True):
                        if state is None or state.status != 'completed' or expired or state.draft_outcome is not None:
                            raise Unavailable('ACTOR_DUT_NOT_COMPLETED_CONSULTATION')
                        value = _message(item, state, identity=item.protocol != LIO_VERSION_V4)
                        if value['status'] != 'completed' or value['failure'] is not None or not value['answer']:
                            raise Unavailable('ACTOR_DUT_PRESENTATION_UNAVAILABLE')
                        if item.protocol == LIO_VERSION_V4:
                            sections = _presentation(state, item.locale)
                            if any(sections.values()) and merged_presentation(sections) != value['answer']:
                                raise Unavailable('ACTOR_DUT_PRESENTATION_CHANGED')
                        shown += [dict(speaker='user', text=item.text),
                                  dict(speaker='assistant', text=value['answer'])]
                    return DutProjection(context, page, tuple(states), tuple(shown))
                frozen = snapshot()
                history = list(frozen.history)
                source = dict(scope_sha256=sha256(context.scope.encode()).hexdigest(),
                    conversation_id=receipt.conversation_id, generation=receipt.generation,
                    message_id=message_id, run_id=receipt.run_id, input_sha256=receipt.input_sha256,
                    history_sha256=sha256(compact(history, sort_keys=True)).hexdigest(),
                    answer_sha256=sha256(history[-1]['text'].encode()).hexdigest())
                source['observer_ref'] = 'actor-dut-'+sha256(compact(source, sort_keys=True)).hexdigest()
                def check():
                    if snapshot() != frozen:
                        raise Unavailable('ACTOR_DUT_SNAPSHOT_CHANGED')
                result = operation(compact(source, sort_keys=True), check, frozen)
                check()
                return result
            return context.with_lio_timeline_projection(project)
        return self.boundary.with_history_context(token, read)
