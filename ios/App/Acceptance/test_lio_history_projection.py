import unittest

from lio_history_projection import HistoryProjection


def row(index, count, *, answer='A', failure=None, complete=True, earlier=False):
    nodes = [dict(identifier='lio.question', depth=1, label='', value='Repeated question', enabled=True,
                  progress_indicator=False),
             dict(identifier=f'lio.position.{index}.loaded.{count}.earlier.{int(earlier)}', depth=1,
                  label='Lio', value='', enabled=True, progress_indicator=False)]
    if failure is not None:
        nodes += [dict(identifier='lio.failure', depth=1, label=failure, value='', enabled=True,
                       progress_indicator=False)]
    else:
        nodes += [dict(identifier='lio.answer', depth=1, label=answer,
                       value='Reply complete' if complete else 'Replying…', enabled=True, progress_indicator=False)]
    return nodes


class CompleteHistoryProjectionTests(unittest.TestCase):
    def test_repeated_text_stays_in_actual_ui_ordinal_order_across_views(self):
        projection = HistoryProjection()
        self.assertFalse(projection.ingest(row(1, 2))['body_complete'])
        view = projection.ingest(row(0, 2))
        self.assertTrue(view['body_complete'])
        self.assertEqual(view['transcript'], [dict(question='Repeated question', answer='A', visible_failure=False)] * 2)

    def test_historical_failure_has_no_invented_body_and_is_not_a_new_load_error(self):
        projection = HistoryProjection()
        projection.ingest(row(0, 2))
        view = projection.ingest(row(1, 2, failure='I couldn’t complete this request.'))
        self.assertTrue(view['body_complete'])
        self.assertEqual(view['errors'], [])
        self.assertIsNone(view['transcript'][1]['answer'])
        self.assertIs(view['transcript'][1]['visible_failure'], True)

    def test_more_pages_and_incomplete_body_never_complete_the_census(self):
        self.assertFalse(HistoryProjection().ingest(row(0, 1, earlier=True))['body_complete'])
        self.assertFalse(HistoryProjection().ingest(row(0, 1, complete=False))['body_complete'])

    def test_page_prepend_resets_old_ordinals_instead_of_mixing_different_positions(self):
        projection = HistoryProjection()
        projection.ingest(row(0, 1, earlier=True))
        view = projection.ingest(row(1, 2))
        self.assertFalse(view['body_complete'])
        self.assertEqual(view['observed_indices'], [1])

    def test_read_retry_remains_a_global_failure(self):
        nodes = row(0, 1) + [dict(identifier='lio.read.retry', depth=0, label='Try reading again', value='',
                                 enabled=True, progress_indicator=False)]
        view = HistoryProjection().ingest(nodes)
        self.assertFalse(view['body_complete'])
        self.assertEqual(view['errors'], ['Try reading again'])

    def test_clipped_question_and_multiple_bylines_are_not_guessed_from_repeated_text(self):
        projection = HistoryProjection()
        self.assertFalse(projection.ingest(row(0, 1)[1:])['body_complete'])
        ambiguous = row(0, 2) + row(1, 2)[1:]
        self.assertEqual(projection.ingest(ambiguous)['observed_indices'], [])

    def test_loading_marker_and_changed_completed_row_are_not_silently_accepted(self):
        nodes = row(0, 1)
        nodes[1]['identifier'] = 'lio.position.0.loaded.1.earlier.2'
        self.assertFalse(HistoryProjection().ingest(nodes)['body_complete'])
        projection = HistoryProjection()
        projection.ingest(row(0, 1))
        from lio_basic_ui_projection import EvidenceUnknown
        with self.assertRaises(EvidenceUnknown): projection.ingest(row(0, 1, answer='Changed'))

    def test_same_count_pending_answer_cannot_reuse_a_previous_completed_row(self):
        from lio_basic_ui_projection import EvidenceUnknown
        projection = HistoryProjection()
        self.assertTrue(projection.ingest(row(0, 1))['body_complete'])
        changed = row(0, 1, answer='Partial', complete=False)
        changed[0]['value'] = 'Different current question'
        with self.assertRaises(EvidenceUnknown): projection.ingest(changed)

    def test_pending_rendering_of_the_same_question_invalidates_cached_completion(self):
        projection = HistoryProjection()
        projection.ingest(row(0, 1))
        view = projection.ingest(row(0, 1, answer='Partial', complete=False))
        self.assertFalse(view['body_complete'])
        self.assertEqual(view['observed_indices'], [])

    def test_opening_is_not_positive_proof_of_an_empty_conversation(self):
        opening = dict(identifier='lio.opening', label='Hello', value='', depth=0, enabled=True, progress_indicator=False)
        example = dict(opening, identifier='lio.example.0', label='Weather')
        legacy = [node for node in row(0, 1) if not node['identifier'].startswith('lio.position.')]
        for nodes in ([opening], [opening] + legacy, [example] + legacy):
            with self.subTest(identifiers=[node['identifier'] for node in nodes]):
                self.assertFalse(HistoryProjection().ingest(nodes)['body_complete'])
        self.assertTrue(HistoryProjection().ingest([example])['body_complete'])


if __name__ == '__main__': unittest.main()
