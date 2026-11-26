"""W2-6 (#1733): the worker appends fixed safety lines after a Lio answer, behind a switch."""
import hashlib
import json
import os
from unittest.mock import patch

from cj_agent.worker import RunWorker
from cj_message.domain import Receipt, Stored
from cj_message.lio_context import LioOriginal
from cj_run.core import Binding, Service
from cj_run.fixture import MemoryRepository
from test_worker_cancel import Drafts


class Messages:
    def __init__(self, text):
        raw = json.dumps(dict(version='MESSAGE-send.1', conversation_id='chat', message_id='m', text=text,
                              trip_id=None, creation_intent='none', expected_generation='g',
                              expected_sequence=0)).encode()
        self.receipt = Receipt('m', 'chat', 'g', 1, 'r', hashlib.sha256(raw).hexdigest())
        self.stored = Stored(raw, self.receipt)
        self.acknowledged = []
    def pending(self, limit): return [] if self.acknowledged else [self.receipt]
    def query(self, mid): return self.stored if mid == 'm' else None
    def acknowledge(self, receipt): self.acknowledged.append(receipt)


class Answer:
    def __init__(self, text): self.text = text
    def stream(self, messages, system=None):
        yield self.text


def run(question, answer, *, switch, locale='zh'):
    runs = Service(MemoryRepository(), lambda _: True)
    worker = RunWorker(scope='scope', messages=Messages(question), runs=runs, provider=Answer(answer),
                       drafts=Drafts(), lio_original=lambda binding: LioOriginal(locale, None))
    with patch.dict(os.environ, {'CJ_LIO_SAFETY_LINES': switch}):
        outcome, = worker.process()
    return outcome.status, runs.snapshot(Binding('scope', 'chat', 'g', 'm', 'r', 1)).text


def test_switch_on_appends_missing_lost_passport_essentials_after_the_model_text():
    status, text = run('护照丢了怎么办', '别着急，先回想一下最后在哪里用过。', switch='1')
    assert status == 'completed'
    assert text.startswith('别着急，先回想一下最后在哪里用过。\n\n')
    assert '派出所' in text and '使馆' in text


def test_switch_off_or_complete_answers_leave_the_text_unchanged():
    assert run('护照丢了怎么办', '别着急。', switch='0') == ('completed', '别着急。')
    complete = '先去派出所报案，再联系驻华使馆。'
    assert run('护照丢了怎么办', complete, switch='1') == ('completed', complete)
    assert run('成都有什么好吃的', '火锅。', switch='1') == ('completed', '火锅。')
