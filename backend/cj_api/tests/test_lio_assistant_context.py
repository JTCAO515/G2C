"""W2-2 (#1728): recent Lio replies join the answer context behind a switch; refs stay the same."""
import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from cj_api import lio_assistant_context as context
from cj_api.lio_assistant_context import interleave, shorten, assistant_context_enabled, read_replies


def ref(mid):
    return dict(conversation_id='c', generation='g', message_id=mid, sequence=int(mid[1:]), input_sha256='0' * 64)


class AssistantContext(unittest.TestCase):
    def test_switch_is_off_by_default_and_accepts_only_zero_or_one(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CJ_LIO_ASSISTANT_CONTEXT', None)
            self.assertFalse(assistant_context_enabled())
        with patch.dict(os.environ, {'CJ_LIO_ASSISTANT_CONTEXT': '1'}):
            self.assertTrue(assistant_context_enabled())
        with patch.dict(os.environ, {'CJ_LIO_ASSISTANT_CONTEXT': 'true'}), self.assertRaises(ValueError):
            assistant_context_enabled()

    def test_replies_follow_their_own_traveler_turn_and_only_the_last_few(self):
        texts = ('成都三天怎么玩', '第二天呢', '有什么吃的', '换成两天', '第二个推荐在哪')
        refs = tuple(ref(f'm{index}') for index in range(1, 5))
        replies = {'m1': '第一天看熊猫……', 'm2': '第二天去青城山', 'm3': '推荐钟水饺、龙抄手', 'm4': '   '}
        history = [dict(role='system', content='MEMORY')]
        messages = interleave(history, texts, refs, replies, turns=3)
        self.assertEqual(messages, [
            dict(role='system', content='MEMORY'),
            dict(role='user', content='成都三天怎么玩'),
            dict(role='user', content='第二天呢'), dict(role='assistant', content='第二天去青城山'),
            dict(role='user', content='有什么吃的'), dict(role='assistant', content='推荐钟水饺、龙抄手'),
            dict(role='user', content='换成两天'),
            dict(role='user', content='第二个推荐在哪')])

    def test_long_replies_are_cut_with_an_ellipsis(self):
        self.assertEqual(shorten('短'), '短')
        long = '字' * 1000
        cut = shorten(long)
        self.assertEqual(len(cut), context.REPLY_CHARACTERS)
        self.assertTrue(cut.endswith('…'))

    def test_misaligned_references_are_refused(self):
        with self.assertRaises(ValueError):
            interleave([], ('a', 'b'), (), {})

    def test_reader_returns_completed_text_per_message_in_this_conversation(self):
        calls = []

        class Database:
            def connect(self, scope):
                calls.append(scope)
                rows = [('m1', '你好，'), ('m1', '成都'), ('m2', 'OK')]

                class Connection:
                    def __enter__(self): return self
                    def __exit__(self, *args): return False
                    def execute(self, sql, params):
                        calls.append((sql, params))
                        return SimpleNamespace(fetchall=lambda: rows)
                return Connection()
        binding = SimpleNamespace(scope='s', conversation_id='c', generation='g', message_sequence=5)
        self.assertEqual(read_replies(Database(), binding, ['m1', 'm2']), {'m1': '你好，成都', 'm2': 'OK'})
        sql, params = calls[1]
        for clause in ("r.status='completed'", "e.kind='text_delta'", 'm.conversation_id=%s', 'm.sequence<%s',
                       'm.message_id=ANY(%s)'):
            self.assertIn(clause, sql)
        self.assertEqual(params, ('s', 'c', 'g', 5, ['m1', 'm2']))
        self.assertEqual(read_replies(Database(), binding, []), {})


class NationalAnswerContext(unittest.TestCase):
    def planner(self, texts, refs):
        from cj_api.local_lio_national import NationalLioPlanning
        planner = NationalLioPlanning.__new__(NationalLioPlanning)
        planner.database = object()
        planner.context = lambda binding, current, answer_only=False: ((*texts, current.text), refs, None)
        return planner

    def test_switch_off_keeps_user_turns_only_and_on_adds_replies_with_the_same_refs(self):
        import cj_api.local_lio_national as national
        refs = (ref('m1'),)
        planner = self.planner(('成都三天怎么玩',), refs)
        binding = SimpleNamespace(scope='s', conversation_id='c', generation='g', message_sequence=2)
        messages = [dict(role='system', content='MEMORY'), dict(role='user', content='第二天呢')]
        with patch.dict(os.environ, {'CJ_LIO_ASSISTANT_CONTEXT': '0'}):
            off, off_refs = planner.readonly_answer_context(binding, messages)
        self.assertEqual(off, [messages[0], dict(role='user', content='成都三天怎么玩'), messages[1]])
        with patch.dict(os.environ, {'CJ_LIO_ASSISTANT_CONTEXT': '1'}), \
                patch.object(national, 'read_replies', return_value={'m1': '第一天看熊猫'}) as reader:
            on, on_refs = planner.readonly_answer_context(binding, messages)
        reader.assert_called_once_with(planner.database, binding, ['m1'])
        self.assertEqual(on, [messages[0], dict(role='user', content='成都三天怎么玩'),
                              dict(role='assistant', content='第一天看熊猫'), messages[1]])
        self.assertEqual(on_refs, off_refs)


if __name__ == '__main__':
    unittest.main()
