"""W2-3 (#1729): offline first-text baseline joins API and worker lines by message key."""
import logging

from cj_agent.run_timing import RunTiming, accepted
from cj_run.core import Binding
from eval.lio_timing_baseline import percentile, summarize


def worker_line(key, run, picked, first_progress, first_text, terminal, status='completed'):
    return (f'2026-12-01 INFO LIO_TIMING message_key={key} run_id={run} picked_up_ms={picked} started_ms=5 '
            f'first_progress_ms={first_progress} first_text_ms={first_text} terminal_ms={terminal} '
            f'terminal=completed status={status}')


def test_percentiles_are_nearest_rank():
    values = list(range(1, 101))
    assert percentile(values, 0.5) == 50 and percentile(values, 0.95) == 95 and percentile([7], 0.95) == 7


def test_measures_start_at_api_acceptance_and_unmatched_runs_are_left_out():
    lines = ['noise',
             'LIO_TIMING_ACCEPTED message_key=aaaaaaaaaaaaaaaa accepted_ms=1000',
             'LIO_TIMING_ACCEPTED message_key=aaaaaaaaaaaaaaaa accepted_ms=9999',
             worker_line('aaaaaaaaaaaaaaaa', 'r1', 1200, 300, 2800, 4000),
             'LIO_TIMING_ACCEPTED message_key=bbbbbbbbbbbbbbbb accepted_ms=2000',
             worker_line('bbbbbbbbbbbbbbbb', 'r2', 2100, '-', '-', 900, status='unknown'),
             worker_line('cccccccccccccccc', 'r3', 5000, 1, 2, 3)]
    report = summarize(lines)
    assert (report['runs'], report['counted'], report['unmatched']) == (3, 2, 1)
    assert report['queue'] == dict(count=2, p50_ms=100, p95_ms=200, max_ms=200)
    assert report['first_text'] == dict(count=1, p50_ms=3000, p95_ms=3000, max_ms=3000)
    assert report['terminal'] == dict(count=2, p50_ms=1000, p95_ms=4200, max_ms=4200)
    completed = summarize(lines, status='completed')
    assert completed['counted'] == 1 and completed['first_progress']['p50_ms'] == 500


def test_round_trip_with_the_real_log_lines(caplog):
    timing = RunTiming(Binding('scope', 'chat', 'g', 'msg-1', 'run-1', 1), clock=lambda: 0.0, wall=lambda: 10_000)
    timing.observe('text_delta', 'x')
    timing.observe('completed')
    with caplog.at_level(logging.INFO, logger='cj_usage.audit'):
        accepted('msg-1')
        timing.log('completed')
    lines = [record.getMessage() for record in caplog.records]
    lines[0] = lines[0].split('accepted_ms=')[0] + 'accepted_ms=9000'
    report = summarize(lines)
    assert report['counted'] == 1 and report['first_text'] == dict(count=1, p50_ms=1000, p95_ms=1000, max_ms=1000)
