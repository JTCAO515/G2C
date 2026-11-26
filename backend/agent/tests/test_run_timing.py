"""W2-3 (#1729): one content-free timing line per executed RUN, joinable to API acceptance."""
import logging

from cj_agent.provider import FakeProvider
from cj_agent.run_timing import RunTiming, accepted, message_key
from cj_message.lio_context import TOOL_EFFECT
from cj_run.core import Binding
from test_worker_cancel import fixture


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now


def timing_lines(caplog):
    return [record.getMessage() for record in caplog.records if record.getMessage().startswith('LIO_TIMING')]


def test_milestones_are_first_occurrences_and_progress_includes_tool_effects(caplog):
    clock = Clock()
    timing = RunTiming(Binding('scope', 'chat', 'g', '旅客的消息 id', 'run-1', 1), clock=clock, wall=lambda: 1000)
    for at, kind, value in ((0.010, 'started', ''), (0.900, 'effect_committed', TOOL_EFFECT + '{"key":"weather"}'),
                            (2.500, 'text_delta', '第一段正文'), (3.000, 'text_delta', '第二段'),
                            (4.250, 'completed', ''), (5.000, 'failed', '')):
        clock.now = at
        timing.observe(kind, value)
    with caplog.at_level(logging.INFO, logger='cj_usage.audit'):
        timing.log('completed')
    assert timing_lines(caplog) == [
        f'LIO_TIMING message_key={message_key("旅客的消息 id")} run_id=run-1 picked_up_ms=1000 started_ms=10 '
        'first_progress_ms=900 first_text_ms=2500 terminal_ms=4250 terminal=completed status=completed']


def test_text_without_tool_progress_is_also_the_first_progress_and_other_effects_are_not(caplog):
    clock = Clock()
    timing = RunTiming(Binding('scope', 'chat', 'g', 'm', 'r', 1), clock=clock, wall=lambda: 5)
    clock.now = 0.2
    timing.observe('effect_committed', 'lio_source:{"key":"x"}')
    clock.now = 1.0
    timing.observe('text_delta', 'answer')
    with caplog.at_level(logging.INFO, logger='cj_usage.audit'):
        timing.log('unknown')
    line, = timing_lines(caplog)
    assert 'started_ms=- first_progress_ms=1000 first_text_ms=1000 terminal_ms=- terminal=- status=unknown' in line


def test_waiting_runs_are_not_logged_and_message_ids_are_never_written(caplog):
    secret = '我的护照号码 E12345678'
    with caplog.at_level(logging.INFO, logger='cj_usage.audit'):
        RunTiming(Binding('scope', 'chat', 'g', secret, 'r', 1)).log('waiting')
        accepted(secret)
    line, = timing_lines(caplog)
    assert line.startswith('LIO_TIMING_ACCEPTED message_key=' + message_key(secret) + ' accepted_ms=')
    assert secret not in line and 'E12345678' not in line


def test_worker_logs_one_line_per_executed_run_with_text_and_terminal(caplog):
    worker, runs, binding, provider, drafts = fixture(lambda runs, binding: FakeProvider())
    with caplog.at_level(logging.INFO, logger='cj_usage.audit'):
        outcome, = worker.process()
    assert outcome.status == 'completed'
    line, = timing_lines(caplog)
    assert line.startswith(f'LIO_TIMING message_key={message_key(binding.message_id)} run_id={binding.run_id} ')
    assert 'first_text_ms=-' not in line and 'terminal=completed status=completed' in line
    assert worker.run_timing is None  # timing lives on the per-RUN owned worker only
