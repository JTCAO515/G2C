"""Explicit LIO3 planning and date conversion through C's original signed commit."""
from datetime import date
import json
import re

from cj_agent.draft import DraftRejected
from cj_agent.provider import ProviderUnknown
from cj_draft.grouped_plan import LioGroupedCalendarPublisher
from cj_draft.rich_schema import GENERATION_PROFILES as RICH_GENERATION_PROFILES
from cj_message.lio_plan_needs import lio_needs_id, original_needs
from cj_message.needs_binding import needs_scope_for
from cj_trip.domain import packed
from cj_trip.lio_history import TripHead
from cj_trip.planning_context import read_current
from cj_trip.postgres import Repository
from cj_usage.local_provider_exit import BudgetExceeded

from .local_lio_calendar_source import LioCalendarSource, LioDateEvidence
from .local_lio_edit import _bind_current
from .lio_plan_pace import saved_summary
from .lio_national_intake import LITERAL_DATE, _MONTH_DAY, _RELATIVE_DAY, _WEEK_SOURCE, _BARE_WEEK


DATE_ATTEMPT = 'lio_calendar_date_attempt'
_DATE_PREFIX = re.compile(r'^(?:(?:从|就|那就|定在|出发日期(?:定在|是)|开始日期(?:定在|是)|行程从)\s*|'
    r'(?:(?:please )?(?:start(?: (?:the )?trip)?(?: on)?|from|set (?:the )?start date to))\s+)',re.I)


def date_completion(text):
    value=_DATE_PREFIX.sub('',text.strip().rstrip('。.!！').strip(),count=1)
    value=re.sub(r'\s*(?:开始|出发)$','',value).strip()
    # Reuse the sourced intake's date grammar; this only selects the operation.
    # Its original quote/question_day and exact numeric value are still checked
    # by data8 before conversion. Bare numeric month/day remains unselected.
    if LITERAL_DATE.fullmatch(value) or _RELATIVE_DAY.fullmatch(value) or _BARE_WEEK.fullmatch(value):
        return True
    week=_WEEK_SOURCE.fullmatch(value)
    if week is not None:
        return any(week[key] is not None for key in ('zh_day','en_before','en_day','next_day'))
    month=_MONTH_DAY.fullmatch(value)
    return month is not None and month['slash_month'] is None


class LioCalendar:
    def __init__(self, database, context_publisher, confirmation):
        self.database, self.context_publisher, self.confirmation = database, context_publisher, confirmation
        self.repository = Repository(context_publisher.repository.connect, context_publisher.repository.scope,
                                     confirmation, structured=True, calendar=True)

    def current(self, binding):
        return read_current(self.repository, needs_scope_for(binding.scope),
                            lio_needs_id(binding.scope, binding.conversation_id))

    def _publisher(self, worker, binding, original, context, source,*,pace=None):
        expected = None if context is None else TripHead.from_trip(context.trip)

        def check_original(candidate, stored, head):
            return (candidate == binding and stored == original and head == expected
                    and worker.message_context.active_original(binding) == original)

        if pace is not None:
            from cj_draft.rich_first import LioRichFirstCalendarPublisher
            return LioRichFirstCalendarPublisher(self.context_publisher,self.confirmation,original_needs,
                check_original,source,LioDateEvidence(),pace=pace)
        return LioGroupedCalendarPublisher(self.context_publisher, self.confirmation, original_needs,
                                          check_original, source, LioDateEvidence())

    def plan(self, worker, binding, state, details, locale, *, day_count, start_date):
        original = worker.messages.query(binding.message_id)
        context = self.current(binding)
        if context is not None and json.loads(context.trip.content)['content_version'] != 'structured.3':
            return self._answer(worker, binding, state, locale,
                '这个对话已有旧版行程，请新开对话来保存按天排列的行程。想保留原行程继续讨论吗？',
                'This chat has an older itinerary. Start a new chat to save a day-by-day itinerary. Shall we keep discussing the original here?')
        source = LioCalendarSource(self.database, worker.message_context, day_count=day_count,
            start_date=start_date, references=details.references)
        rich_first=(context is None and details.fields.get('fixed_items')==[]
                    and details.pace is not None and details.pace.value is not None)
        publisher = self._publisher(worker, binding, original, context, source,
                                    pace=details.pace.value if rich_first else None)
        previous = worker.drafts
        worker.drafts = publisher
        try:
            state, committed = worker._draft(binding, state, json.loads(original.raw)['text'], original)
        finally:
            worker.drafts = previous
        if committed is not None:
            state = worker._event(binding,state,'text_delta',saved_summary(locale,day_count,
                details.pace,dated=start_date is not None,retained=context is not None,
                rich_applied=rich_first and publisher.generation_used in RICH_GENERATION_PROFILES))
        return worker._event(binding, state, 'completed')

    def convert(self, worker, binding, state, intake, original, turns, references):
        if (intake.publication_hold or intake.intent == 'cancel' or not date_completion(turns[-1].text)
                or intake.start_date is None or intake.start_date['state'] != 'known'):
            return None
        context = self.current(binding)
        if context is None:
            return None
        document = json.loads(context.trip.content)
        if document['content_version'] != 'structured.3' or document['calendar']['state'] != 'undated':
            return None
        evidence = intake.sources.get('start_date', ())
        quotes = {ref['quote'] for ref in evidence if ref['source_index'] == len(turns)-1}
        if len(quotes) != 1 or any(ref['source_index'] != len(turns)-1 for ref in evidence):
            return None
        quote, = quotes
        stored = worker.messages.query(binding.message_id)
        state = _bind_current(worker, binding, state)
        state = worker._event(binding, state, 'effect_committed', DATE_ATTEMPT)
        source = LioCalendarSource(self.database, worker.message_context, day_count=len(document['days']),
            start_date=intake.start_date['value'], references=references, date_quote=quote)
        publisher = self._publisher(worker, binding, stored, context, source)
        previous = worker.drafts
        worker.drafts = publisher
        try:
            _, capture = worker._step(binding, lambda: publisher.sources_for(binding), draft=True)
            root = json.loads(capture.basis.fixed_bindings)['reference']
            request = packed(dict(version='TRIP-date-convert.1', action_id='lio-date-'+binding.run_id,
                trip_id=context.trip.trip_id, expected_version=context.trip.version,
                original_hash=TripHead.from_trip(context.trip).content_sha256,
                start_date=intake.start_date['value'], date_source=dict(reference=root, quote=quote,
                    question_day=original.question_day.isoformat())))
            worker._model_history(binding, publisher.model_messages(binding, turns[-1].text, capture, []), None)

            def publish():
                return publisher.convert_for_message(binding, stored,
                    worker.message_context.active_original(binding), request, capture,
                    before_publish=worker._publication_check)

            state, receipt = worker._step(binding, publish, lambda value: 'lio_calendar_date_result', draft=True)
            if receipt['committed'] is None:
                raise ProviderUnknown('original date conversion outcome unknown; query only')
        except DraftRejected:
            state = worker._event(binding, worker.runs.snapshot(binding), 'draft_outcome', 'validation_failed')
            return self._answer(worker, binding, state, original.locale,
                '这次没能补上日期，原行程保留。你想从哪一天开始？',
                'I could not add the dates; the original itinerary is kept. What start date would you like?')
        except BudgetExceeded:
            return worker._event(binding, worker._budget_rejection(binding, 'draft'), 'completed')
        finally:
            worker.drafts = previous
        if not receipt['committed']:
            return self._answer(worker, binding, state, original.locale,
                '这个出发日与已确定的安排冲突，原行程保留。想保留固定安排，还是换个出发日？',
                'That start date conflicts with a confirmed arrangement, so I kept the itinerary. Would you like to keep the fixed arrangement or choose another date?')
        return self._answer(worker, binding, state, original.locale,
            '日期已补上，并保存为行程的新版本；天气和当天开放情况尚未确认。想先看哪一天？',
            'The dates are added in a new itinerary version. Weather and opening information remain unverified. Which day would you like to look at?')

    @staticmethod
    def _answer(worker, binding, state, locale, zh, en):
        state = worker._event(binding, state, 'text_delta', zh if locale == 'zh' else en)
        return worker._event(binding, state, 'completed')
