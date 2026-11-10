"""Save a scoped Lio replacement through C's original Travel-run publisher."""
from base64 import b64decode
from datetime import date, datetime, time
import json
from zoneinfo import ZoneInfo

from psycopg import Error as DatabaseError

from cj_agent.draft import DraftRejected
from cj_agent.provider import ProviderUnknown
from cj_draft.lio_plan import LioPlanPublisher
from cj_feasibility.solver import Limits
from cj_message.domain import Unavailable
from cj_message.lio_plan_needs import EDIT_BOUND_EFFECT, attach_existing, lio_needs_id, original_needs
from cj_message.needs_binding import needs_scope_for
from cj_needs.contract_v1 import decode_snapshot
from cj_run.postgres import CommitUnknown
from cj_trip.domain import Denied
from cj_trip.lio_history import TripHead
from cj_trip.planning_context import read_current
from cj_usage.local_provider_exit import BudgetExceeded

from .lio_edit_selection import match_edit, select_lio_edit
from .lio_planning_grounding import planning_withdrawn


class LioEdit:
    matches = staticmethod(match_edit)

    def __init__(self, context_publisher, confirmation):
        self.context_publisher = context_publisher
        self.confirmation = confirmation

    def execute(self, worker, binding, state, original, text, locale, deadline):
        if planning_withdrawn(text):
            return _answer(worker, binding, state, locale, '好，先不改行程。', "Okay, I won't change the itinerary.")
        needs_scope = needs_scope_for(binding.scope)
        needs_id = lio_needs_id(binding.scope, binding.conversation_id)
        try:
            context = read_current(self.context_publisher.repository, needs_scope, needs_id)
        except (Denied, DatabaseError) as error:
            raise ProviderUnknown('original Lio itinerary unavailable') from error
        if context is None:
            return _answer(worker, binding, state, locale, '请先让我帮你安排一个行程。', 'Ask me to plan an itinerary first.')
        try:
            source = json.loads(context.needs_source)
            snapshot = decode_snapshot(b64decode(source['snapshot'], validate=True))
            arrival = snapshot.fields.get('arrival', {}).get('date')
            starts_on = date.fromisoformat(arrival['value']) if arrival and arrival['state'] == 'known' else None
        except (KeyError, ValueError) as error:
            raise ProviderUnknown('original Lio itinerary calendar unavailable') from error
        selection = select_lio_edit(context.trip, text, locale, 'lio-edit-' + binding.run_id, starts_on=starts_on)
        if selection.status == 'protected':
            return _answer(worker, binding, state, locale, '这项安排暂时不能改。', "I can't change this stop.")
        if selection.candidate is None:
            return _answer(worker, binding, state, locale,
                           '请给出具体日期或原地点名，并用引号注明要换成的一个地点。',
                           'Please use the exact date or original stop name, and put one replacement place in quotes.')

        state = _bind_current(worker, binding, state)
        head = TripHead.from_trip(context.trip)
        draft = selection.candidate

        def check_original(candidate, stored, expected):
            return (candidate == binding and expected == head and stored == original
                    and worker.message_context.active_original(binding) == original)

        publisher = LioPlanPublisher(self.context_publisher, self.confirmation, original_needs, check_original)
        previous = worker.drafts
        worker.drafts = publisher
        try:
            _, capture = worker._step(binding, lambda: publisher.sources_for(binding), draft=True)
            # Register the exact Trip decision and its original Memory fence even
            # though this explicit replacement requires no model outflow.
            worker._model_history(binding, publisher.model_messages(binding, text, capture, []), None)

            def publish():
                return publisher.publish_edit_for_message(
                    binding, original, worker.message_context.active_original(binding),
                    draft.scope.request.raw, draft.candidate.edit.raw, capture,
                    limits=_limits(capture), before_publish=worker._publication_check)

            state, _ = worker._step(binding, publish, lambda receipt: 'trip_proposal:' + receipt.proposal_id,
                                    draft=True, publication_deadline=deadline)
        except DraftRejected:
            state = worker._event(binding, worker.runs.snapshot(binding), 'draft_outcome', 'validation_failed')
            return _answer(worker, binding, state, locale, '这次没能更新行程。', "I couldn't update the itinerary.")
        except BudgetExceeded:
            state = worker._budget_rejection(binding, 'draft')
            return worker._event(binding, state, 'completed')
        finally:
            worker.drafts = previous
        return _answer(worker, binding, state, locale, '行程已经更新好了。', 'I updated your itinerary.')


def _bind_current(worker, binding, state):
    def mutation(cursor):
        attach_existing(cursor, binding, worker.message_context.active_original(binding))

    try:
        return worker._event(binding, state, 'effect_committed', EDIT_BOUND_EFFECT, mutation=mutation)
    except CommitUnknown as error:
        current = worker.runs.snapshot(binding)
        if EDIT_BOUND_EFFECT in current.effects and current.status == 'running':
            return current
        raise ProviderUnknown('original Lio edit binding unavailable') from error
    except (Unavailable, DatabaseError) as error:
        raise ProviderUnknown('original Lio edit binding unavailable') from error


def _limits(capture):
    snapshot, _ = capture.records()
    arrival = date.fromisoformat(snapshot.fields['arrival']['date']['value'])
    epoch = datetime.combine(arrival, time.min, tzinfo=ZoneInfo('Asia/Shanghai'))
    return Limits(epoch, 7 * 86400, 1, 10_000_000, 60, 120, 128, .05, .05, 100)


def _answer(worker, binding, state, locale, zh, en):
    state = worker._event(binding, state, 'text_delta', zh if locale == 'zh' else en)
    return worker._event(binding, state, 'completed')
