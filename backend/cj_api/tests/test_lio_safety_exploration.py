"""W2-6 (#1733): the v4 practical answer gets the same fixed safety lines before display."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cj_api.local_lio_exploration import ExplorationPlanning
from cj_api.lio_exploration_policy import Scene


class ExplorationSafetyLines(unittest.TestCase):
    def answer(self, question, model_text, switch):
        planner = ExplorationPlanning.__new__(ExplorationPlanning)
        planner._input = lambda worker, view, text, extra: [dict(role='user', content=text)]
        finished = []
        planner._finish = lambda worker, binding, state, body, scene, locale: finished.append(body) or 'done'
        worker = SimpleNamespace(tools=SimpleNamespace(answer=lambda *args, **kwargs: iter((model_text,))),
                                 runs=SimpleNamespace(snapshot=lambda binding: 'state'))
        original = SimpleNamespace(locale='zh', question_day=None)
        view = SimpleNamespace(references=())
        with patch.dict(os.environ, {'CJ_LIO_SAFETY_LINES': switch}):
            planner._answer(worker, 'binding', 'state', question, original, view, Scene.PRACTICAL)
        return finished[0]

    def test_switch_on_appends_missing_essentials(self):
        body = self.answer('护照丢了怎么办', '别着急。', '1')
        self.assertTrue(body.startswith('别着急。\n\n'))
        self.assertIn('派出所', body)
        self.assertIn('使馆', body)

    def test_switch_off_keeps_the_model_text(self):
        self.assertEqual(self.answer('护照丢了怎么办', '别着急。', '0'), '别着急。')


if __name__ == '__main__':
    unittest.main()
