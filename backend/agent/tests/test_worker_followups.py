"""W2-1 (#1727): the worker commits the layout before the text and fixed buttons after it."""
import os
from unittest.mock import patch

from cj_agent.worker import RunWorker
from cj_message.lio_context import FOLLOWUPS_EFFECT, LAYOUT_EFFECT, LioLayout, LioOriginal
from cj_run.core import Binding, Service
from cj_run.fixture import MemoryRepository
from test_worker_cancel import Drafts
from test_worker_safety_lines import Messages


class Tools:
    commits_layout = True

    def __init__(self, layout, text):
        self.layout, self.text = layout, text
    def answer(self, worker, binding, inputs, **kwargs):
        self.kwargs = kwargs
        if self.layout is not None:
            yield LioLayout(self.layout)
        yield self.text


def run(question, answer, layout, locale='zh'):
    runs = Service(MemoryRepository(), lambda _: True)
    worker = RunWorker(scope='scope', messages=Messages(question), runs=runs, provider=None, tools=Tools(layout, answer),
                       drafts=Drafts(), lio_original=lambda binding: LioOriginal(locale, None))
    outcome, = worker.process()
    return outcome.status, runs.snapshot(Binding('scope', 'chat', 'g', 'm', 'r', 1))


def test_split_answer_commits_layout_before_text_and_buttons_after():
    status, state = run('外国游客怎么用支付宝？', '先绑定国际银行卡。\n\n再出示付款码。', 'split')
    assert status == 'completed'
    assert state.effects[0] == LAYOUT_EFFECT + 'split'
    assert state.effects[1].startswith(FOLLOWUPS_EFFECT)
    assert '"tool":"payment-guide"' in state.effects[1] and '打开支付开通指南' in state.effects[1]


def test_single_answer_or_no_layout_carries_no_buttons():
    status, state = run('外国游客怎么用支付宝？', '先绑定国际银行卡。', 'single')
    assert status == 'completed' and state.effects == (LAYOUT_EFFECT + 'single',)
    status, state = run('外国游客怎么用支付宝？', '先绑定国际银行卡。', None)
    assert status == 'completed' and state.effects == ()


def test_split_answer_without_a_matching_topic_gets_a_layout_but_no_buttons():
    status, state = run('成都有什么好吃的', '火锅。\n\n再试试串串。', 'split')
    assert status == 'completed' and state.effects == (LAYOUT_EFFECT + 'split',)


def test_english_buttons_use_the_fixed_english_labels():
    status, state = run('How do I pay with Alipay?', 'Link your card.\n\nThen show the code.', 'split', locale='en')
    assert 'Payment setup guide' in state.effects[1]


def test_a_tools_object_that_does_not_declare_layout_is_never_given_the_argument():
    class Strict:
        def answer(self, worker, binding, inputs, *, lio_locale, lio_question_day):
            yield '好的。'
    runs = Service(MemoryRepository(), lambda _: True)
    worker = RunWorker(scope='scope', messages=Messages('你好'), runs=runs, provider=None, tools=Strict(),
                       drafts=Drafts(), lio_original=lambda binding: LioOriginal('zh', None))
    outcome, = worker.process()
    assert outcome.status == 'completed'
    tools = Tools('split', '好的。')
    worker = RunWorker(scope='scope', messages=Messages('你好'), runs=Service(MemoryRepository(), lambda _: True), provider=None,
                       tools=tools, drafts=Drafts(), lio_original=lambda binding: LioOriginal('zh', None))
    worker.process()
    assert tools.kwargs['lio_layout'] is True
