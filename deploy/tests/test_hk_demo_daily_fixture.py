"""Deterministic day-boundary controls for the local fixture, not a live quota."""
from collections import Counter
from datetime import date, timedelta

import pytest

from hk_demo_local_check import fill_daily_questions


class Response:
    def __init__(self, status, body):
        self.status_code, self.body, self.text = status, body, str(body)

    def json(self):
        return self.body


class NativeDays:
    def __init__(self, *, original_yesterday=False, flip_manual=None,
                 flip_limit=None, flip_after_lio=False, broken_limit=False,
                 flip_after_broken=False, bad_code=None):
        self.day = date(2026, 11, 16)
        old = self.day - timedelta(days=1) if original_yesterday else self.day
        self.rows = {'original-' + str(i): old for i in range(4)}
        self.originals = self.rows.copy()
        self.flip_manual, self.flip_limit = flip_manual, flip_limit
        self.flip_after_lio = flip_after_lio
        self.broken_limit, self.flip_after_broken = broken_limit, flip_after_broken
        self.bad_code = bad_code
        self.manual, self.limits = [], []

    def counts(self):
        return self.day, dict(Counter(self.rows.values()))

    def question_day(self, mid):
        return self.rows.get(mid)

    def accept(self, kind, mid, *, broken=False):
        if mid in self.rows:
            return Response(200, {'receipt': {'message_id': mid}})
        if not broken and sum(x == self.day for x in self.rows.values()) >= 400:
            if kind == 'lio':
                return Response(429, {'failure': 'wrong' if self.bad_code == 'lio' else 'quota'})
            return Response(429, {'error': {'code': 'WRONG' if self.bad_code == 'demo' else 'DEMO_DAILY_LIMIT'}})
        self.rows[mid] = self.day
        return Response(200, {'receipt': {'message_id': mid}})

    def post_question(self, number):
        assert number == len(self.manual) + 1
        if number == self.flip_manual:
            self.day += timedelta(days=1)
        self.manual.append(number)
        return self.accept('message', 'demo-' + str(number))

    def post_limit(self, kind, mid):
        if kind == self.flip_limit:
            self.day += timedelta(days=1)
            self.flip_limit = None
        self.limits.append((kind, mid))
        response = self.accept(kind, mid, broken=self.broken_limit)
        if self.broken_limit and self.flip_after_broken:
            self.day += timedelta(days=1)
        if kind == 'lio' and self.flip_after_lio:
            self.day += timedelta(days=1)
            self.flip_after_lio = False
        return response

    def run(self):
        result = fill_daily_questions(self.post_question, self.post_limit,
                                      self.counts, self.question_day)
        assert {mid: self.rows[mid] for mid in self.originals} == self.originals
        return result


@pytest.mark.parametrize('settings,expected_manual', [
    ({}, 396),
    ({'original_yesterday': True}, 400),
    ({'flip_manual': 101}, 500),
    ({'flip_limit': 'demo'}, 795),
    ({'flip_limit': 'lio'}, 795),
])
def test_fill_uses_actual_admitted_days_and_keeps_unique_originals(settings, expected_manual):
    native = NativeDays(**settings)
    receipts, tested_day = native.run()
    assert len(receipts) == expected_manual
    assert [r['message_id'] for r in receipts] == ['demo-' + str(i) for i in range(1, expected_manual + 1)]
    assert native.counts()[1][tested_day] == 400
    assert max(native.counts()[1].values()) <= 400
    assert len({mid for _, mid in native.limits}) == len(native.limits)
    # The caller's subsequent rollover check must use the next unused native
    # message/sequence, not the old hard-coded demo-397 after a longer fill.
    assert 'demo-' + str(len(receipts) + 1) not in native.rows


def test_midnight_after_both_rejections_keeps_the_day_actually_tested():
    native = NativeDays(flip_after_lio=True)
    receipts, tested_day = native.run()
    assert tested_day != native.day
    assert len(receipts) == 396 and native.counts()[1][tested_day] == 400


@pytest.mark.parametrize('flip', [False, True])
def test_same_day_over_admission_is_never_hidden_by_a_later_midnight(flip):
    native = NativeDays(broken_limit=True, flip_after_broken=flip)
    with pytest.raises(AssertionError):
        native.run()
    assert len(native.limits) == 1
    assert max(native.counts()[1].values()) == 401


@pytest.mark.parametrize('kind', ['demo', 'lio'])
def test_original_429_error_contracts_are_not_relaxed(kind):
    native = NativeDays(bad_code=kind)
    with pytest.raises(AssertionError):
        native.run()
    assert len(native.manual) == 396


def test_more_than_one_actual_rollover_is_incomplete_not_pass_or_unbounded_retry():
    native = NativeDays(flip_manual=101, flip_limit='demo')
    with pytest.raises(AssertionError, match='more than one native day'):
        native.run()
    assert max(native.counts()[1].values()) <= 400


def test_unexpected_changes_to_the_original_four_are_not_normalized_away():
    native = NativeDays()
    native.rows['unexpected'] = native.day
    with pytest.raises(AssertionError, match='four original'):
        native.run()
    assert native.manual == []
