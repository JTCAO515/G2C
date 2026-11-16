import unittest

from lio_basic_ui_projection import EvidenceUnknown, project


def node(identifier, text='', *, value='', enabled=True, depth=1):
    return dict(identifier=identifier, label=text, value=value, enabled=enabled, depth=depth)


class ActualAXProjectionTests(unittest.TestCase):
    def test_exact_unicode_and_repeated_turns_are_not_normalized_or_collapsed(self):
        nodes = [node('lio.chat.newShortcut'), node('lio.composer', value='  草稿\n ')]
        for _ in range(2):
            nodes += [node('lio.question', value='  北京\n '), node('lio.answer', '回答  \n')]
        result = project(nodes)
        self.assertEqual(result['transcript'], [dict(question='  北京\n ', answer='回答  \n')] * 2)
        self.assertEqual(result['draft'], '  草稿\n ')
        self.assertTrue(result['body_complete'])

    def test_parent_and_child_are_one_semantic_element(self):
        result = project([node('lio.chat.newShortcut'), node('lio.question', value='Q'),
                          node('lio.question', value='Q', depth=2), node('lio.answer', 'A')])
        self.assertEqual(result['transcript'], [dict(question='Q', answer='A')])

    def test_visible_failure_and_original_unanswered_question_remain(self):
        result = project([node('lio.chat.newShortcut'), node('lio.question', value='Q'),
                          node('lio.failure', 'Request unavailable')])
        self.assertEqual(result['transcript'], [dict(question='Q', answer='')])
        self.assertEqual(result['errors'], ['Request unavailable'])
        self.assertFalse(result['body_complete'])

    def test_partial_hierarchy_is_unknown_instead_of_inventing_a_question(self):
        with self.assertRaises(EvidenceUnknown):
            project([node('lio.chat.newShortcut'), node('lio.answer', 'Only a virtualized answer')])

    def test_native_pending_control_and_missing_composer_do_not_claim_completion(self):
        self.assertFalse(project([node('lio.chat.newShortcut', enabled=False)])['body_complete'])
        self.assertFalse(project([node('lio.chat.newShortcut')])['body_complete'])


if __name__ == '__main__':
    unittest.main()
