"""Q-1 (#2011): the tappable-answer evaluation runs, and its gates hold on the development pack."""
import json
from pathlib import Path

import pytest

import eval.lio_rich_eval as rich


@pytest.fixture(scope='module')
def report():
    return rich.run('dev')


def test_the_gates_that_do_not_depend_on_the_unreviewed_aliases(report):
    assert report['entity_precision'] >= rich.TARGETS['entity_precision'], report['entities']['rows']
    assert report['followup_coverage'] == 1.0, report['followups']['uncovered']
    assert report['card_accuracy'] == 1.0, report['cards']['wrong']


def test_recall_on_the_development_pack_is_measured_and_not_below_the_baseline(report):
    # The pack has almost no aliases, so this is a measurement of that gap; the 2026-11-27 baseline is 0.849.
    # Reviewed aliases only raise it: a fall means the linker got worse.
    assert report['entity_recall'] >= 0.80, [row for row in report['entities']['rows'] if row['missed']]


def test_the_report_has_every_number_the_acceptance_needs(report):
    for key in ('entity_precision', 'entity_recall', 'followup_coverage', 'card_accuracy', 'targets', 'missed'):
        assert key in report
    assert report['entities']['expected'] >= 40 and report['followups']['n'] >= 30 and report['cards']['n'] >= 20


def test_every_annotation_points_at_text_and_a_place_of_the_pack():
    cases = rich.load_cases()
    ids = {p['id'] for p in json.loads(rich.DEV_PACK.read_text(encoding='utf-8'))['places']}
    for case in cases['entities']:
        for surface, pid in case['expected'] + case['acceptable']:
            assert surface in case['answer'] and pid in ids, (case['id'], surface, pid)


def test_a_wrong_link_and_a_missing_one_are_both_counted():
    docs = rich.dev_docs()
    cases = [dict(id='x', adcode='110000', answer='先去故宫博物院。', expected=[['故宫博物院', 'pl_bj_gugong']], acceptable=[]),
             dict(id='y', adcode='110000', answer='先去故宫博物院。', expected=[], acceptable=[]),
             dict(id='z', adcode='110000', answer='今天天气不错。', expected=[['故宫博物院', 'pl_bj_gugong']], acceptable=[])]
    result = rich.entity_metrics(cases, docs)
    assert (result['produced'], result['correct'], result['expected'], result['found']) == (2, 1, 2, 1)
    assert result['precision'] == 0.5 and result['recall'] == 0.5


def test_the_command_line_prints_a_report_and_strict_fails_on_a_missed_target(capsys, monkeypatch):
    assert rich.main([]) == 0
    assert json.loads(capsys.readouterr().out)['version'] == rich.VERSION
    monkeypatch.setitem(rich.TARGETS, 'entity_recall', 1.01)
    assert rich.main(['--strict']) == 1
