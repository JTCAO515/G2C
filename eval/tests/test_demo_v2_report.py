"""Report fixtures keep scene verdicts, original attempts, and fees distinct."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo_v2_report import markdown, summarize


def original(run, *, body=1.2, complete=2.3):
    return dict(run_id=run, evidence_ref=run+'.json', first_server_progress_seconds=.2,
                first_running_or_tool_seconds=.4, first_body_seconds=body, complete_seconds=complete)


def attempt(scene, index, verdict, runs, meter, **extra):
    return dict(scene=scene, attempt=index, verdict=verdict, verdict_basis='program', verdict_ref='original-verdict.json',
                runs=runs, meter=meter, **extra)


def test_original_failure_and_child_run_survive_successful_repeat():
    report = summarize([
        attempt('Z03', 1, 'FAIL', [original('needs'), original('planning', body=None, complete=None)], [],
                actions=[dict(action_id='confirmed', operation='confirm_needs', evidence_ref='confirm.json')]),
        attempt('Z03', 2, 'PASS', [original('retest')], []),
        attempt('E01', 1, 'PASS', [original('question')], []),
    ])
    assert report['languages']['zh']['outcomes'] == dict(PASS=0, FAIL=1, UNKNOWN=0, UNRUN=4)
    assert report['languages']['en']['success_rate'] == .2
    assert report['scenes']['Z03'][0]['actions'][0]['action_id'] == 'confirmed'
    assert report['scenes']['Z03'][0]['runs'][1]['complete_seconds'] is None
    assert '| Z03／1 | FAIL | needs<br>planning |' in markdown(report)
    assert '| Z03／2 | PASS | retest |' in markdown(report)


def test_lio_stage_uses_its_fixed_denominator_and_reports_the_latest_attempt_separately():
    rows = [
        attempt('Z03', 1, 'FAIL', [original('initial')], []),
        attempt('Z03', 2, 'PASS', [original('rerun')], []),
    ]
    report = summarize(rows, lio_phase=2)
    assert set(report['scenes']) == {'Z03', 'E03'}
    assert report['languages']['zh']['success_rate'] == 0
    assert report['languages']['zh']['latest_success_rate'] == 1
    assert report['languages']['en']['latest_success_rate'] is None
    rendered = markdown(report)
    assert rendered.startswith('# Lio 阶段 2')
    assert '| Z03／1 | FAIL | initial |' in rendered
    assert '| Z03／2 | PASS | rerun |' in rendered
    with pytest.raises(ValueError, match='attempts must be in order'):
        summarize(rows, lio_phase=1)


def test_lio_stage_one_counts_bilingual_fact_questions_without_changing_legacy_plan():
    rows = [
        attempt('Z06', 1, 'PASS', [original('fact-zh')], []),
        attempt('E06', 1, 'UNKNOWN', [original('fact-en')], None),
    ]
    report = summarize(rows, lio_phase=1)
    assert list(report['scenes']) == ['Z01', 'Z02', 'Z06', 'E01', 'E02', 'E06']
    assert report['languages']['zh']['success_rate'] == 1 / 3
    assert report['languages']['en']['outcomes'] == dict(PASS=0, FAIL=0, UNKNOWN=1, UNRUN=2)
    assert len(summarize([])['scenes']) == 10


def test_missing_and_unresolved_meter_remain_unknown_with_known_subtotals():
    completed = dict(attempt_id='model-received', run_id='question', kind='model', state='RECEIVED',
                     receipt=dict(model_id='qwen3.8-flash', region='cn-beijing',
                                  usage=dict(prompt_tokens=1000, completion_tokens=100, total_tokens=1100)))
    paid_tool = dict(attempt_id='place-received', run_id='question', kind='place', state='RECEIVED',
                     estimated_cny='0.003')
    unresolved = dict(attempt_id='route-intent', run_id='question', kind='route', state='INTENT')
    report = summarize([
        attempt('E01', 1, 'PASS', [original('question')], [completed, paid_tool, unresolved]),
        attempt('E02', 1, 'UNKNOWN', [original('other', body=None, complete=None)], None),
    ])
    fees = report['scenes']['E01'][0]['fees']
    assert fees['conservative_known_cny'] == dict(model=1, tool=2)
    assert fees['estimated_model_known_cny'] == '0.00107'
    assert fees['estimated_tool_known_cny'] == '0.003'
    assert fees['estimated_model_complete'] is True and fees['estimated_tool_complete'] is False
    assert fees['actual_billed_cny'] == 'UNKNOWN'
    assert report['fees']['meter_complete'] is False
    assert report['languages']['zh']['success_rate'] is None
    assert 'UNKNOWN（已知 ¥0.003）' in markdown(report)


def test_original_run_meter_and_attempt_order_are_never_rebound():
    first = attempt('E01', 1, 'PASS', [original('first')], [])
    duplicate = attempt('Z01', 1, 'PASS', [original('first')], [])
    with pytest.raises(ValueError, match='RUN may be reported once'):
        summarize([first, duplicate])
    wrong_meter = dict(attempt_id='foreign', run_id='another', kind='model', state='INTENT')
    with pytest.raises(ValueError, match='Meter must attach'):
        summarize([dict(first, meter=[wrong_meter])])
    with pytest.raises(ValueError, match='attempts must be in order'):
        summarize([dict(first, attempt=2)])
    with pytest.raises(ValueError, match='first body'):
        summarize([dict(first, runs=[original('first', body=None)])])
    with pytest.raises(ValueError, match='independent scene verdict'):
        summarize([dict(first, verdict_basis='model')])
