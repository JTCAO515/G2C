import unittest
from types import SimpleNamespace
from unittest.mock import patch

from lio_paginated_capture import PagedCapture
from lio_basic_ui_projection import EvidenceUnknown


def position(index, count):
    return dict(identifier=f'lio.position.{index}.loaded.{count}.earlier.0', frame=[0, 140, 50, 20])


class PaginationNavigationTests(unittest.TestCase):
    def test_missing_middle_uses_current_visible_position_instead_of_old_cached_minimum(self):
        capture = object.__new__(PagedCapture)
        calls = []
        first = dict(errors=[], body_complete=False, page_ready=True, loaded_count=12,
                     earlier_available=False, observed_indices=[0, 1, 10, 11])
        last = dict(first, body_complete=True, observed_indices=list(range(12)))
        snapshots = iter([({'nodes': [position(10, 12), position(11, 12)]}, first), ({'nodes': []}, last)])
        capture.state = lambda: next(snapshots)
        capture.action = lambda kind, **fields: calls.append(kind)
        _, view = capture.ready()
        self.assertTrue(view['body_complete'])
        self.assertEqual(calls, ['swipe_down'])

    def test_earlier_button_must_be_inside_the_actual_scroll_container(self):
        scroll = dict(identifier='', scroll_container=True, frame=[0, 137, 393, 562])
        hidden = dict(identifier='lio.earlier', frame=[20, 100, 140, 30])
        shown = dict(hidden, frame=[20, 149, 140, 30])
        self.assertFalse(PagedCapture.visible([scroll, hidden], 'lio.earlier'))
        self.assertTrue(PagedCapture.visible([scroll, shown], 'lio.earlier'))

    def test_first_body_and_completion_use_native_times_before_reading_the_full_census(self):
        capture = object.__new__(PagedCapture)
        before = dict(draft='Q new', errors=[], body_complete=True, loaded_count=1,
                      transcript=[dict(question='Q old', answer='A old', visible_failure=False)])
        final = dict(before, draft='', loaded_count=2,
                     transcript=before['transcript'] + [dict(question='Q new', answer='A new', visible_failure=False)])
        ready = iter([({}, before), ({'finished_uptime': 8}, final)])
        capture.ready = lambda **kwargs: next(ready)
        capture.action = lambda *args, **kwargs: dict(started_uptime=1)
        capture.projection = SimpleNamespace(count=2, rows={})
        snapshots = iter([(2, 'A', 'Replying…'), (3, 'A new', 'Reply complete')])
        def state():
            uptime, body, status = next(snapshots)
            if status == 'Reply complete':
                capture.projection.rows[1] = dict(question='Q new', answer=body, visible_failure=False)
            nodes = [dict(identifier='lio.question', label='', value='Q new', depth=1),
                     dict(identifier='lio.position.1.loaded.2.earlier.0', label='Lio', value='', depth=1),
                     dict(identifier='lio.answer', label=body, value=status, depth=1)]
            return dict(nodes=nodes, finished_uptime=uptime), dict(final, body_complete=False)
        capture.state = state
        _, view, timing = capture.send_once('Q new')
        self.assertTrue(view['body_complete'])
        self.assertEqual(timing['first_body_ms'], 1000)
        self.assertEqual(timing['complete_ms'], 2000)

    def test_unknown_history_candidate_cannot_be_ignored_to_claim_a_unique_match(self):
        capture = object.__new__(PagedCapture)
        target = [dict(question='Q', answer='A', visible_failure=False)]
        capture.ready = lambda **kwargs: ({}, dict(transcript=[], body_complete=False))
        capture.history = lambda count: dict(rows=[dict(row_key='a'), dict(row_key='b')],
            opened=[dict(transcript=target, body_complete=True, errors=[]),
                    dict(transcript=[], body_complete=False, errors=[])])
        capture.history_rows = lambda: ({}, [dict(row_key='a'), dict(row_key='b')])
        capture.action = lambda *args, **kwargs: self.fail('Do not choose among incompletely read candidates')
        with self.assertRaises(EvidenceUnknown): capture.select_transcript(target, 2)

    def test_immediate_snapshot_never_uses_the_previous_complete_census(self):
        from lio_history_projection import HistoryProjection
        from test_lio_history_projection import row
        capture = object.__new__(PagedCapture)
        capture.projection = HistoryProjection()
        capture.projection.ingest(row(0, 1))
        nodes = row(0, 1, answer='Partial', complete=False) + [
            dict(identifier='lio.composer', value='draft', label='', enabled=True, depth=0, progress_indicator=False),
            dict(identifier='lio.chat.newShortcut', value='', label='', enabled=True, depth=0, progress_indicator=False)]
        capture.raw = lambda: dict(nodes=nodes)
        capture.action = lambda *args, **kwargs: self.fail('Immediate observation must not navigate')
        _, view = capture.immediate(timeout=0)
        self.assertFalse(view['body_complete'])
        self.assertEqual(view['transcript'], [])


if __name__ == '__main__': unittest.main()
