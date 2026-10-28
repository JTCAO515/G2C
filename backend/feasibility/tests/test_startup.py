"""Fresh-process regression for #176; real CP-SAT, unchanged request budget."""
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event
import unittest
from unittest.mock import patch

TESTS = Path(__file__).resolve().parent
STARTUPS = ('from cj_api.app import create_app; create_app()', 'import cj_agent.worker')


def process(source):
    return subprocess.run([sys.executable, '-B', '-c', source], capture_output=True, text=True,
                          timeout=90, env={'PATH': os.environ['PATH'], 'CJ_ENV': 'local', 'PYTHONDONTWRITEBYTECODE': '1'})


class StartupTests(unittest.TestCase):
    def test_api_and_worker_preload_before_first_actual_request(self):
        for startup in STARTUPS:
            with self.subTest(startup=startup):
                run = process(f'''
import json, sys
from threading import Event
assert 'ortools.sat.python.cp_model' not in sys.modules
{startup}
preloaded = 'ortools.sat.python.cp_model' in sys.modules
sys.path.insert(0, {str(TESTS)!r})
from test_solver import item, event, problem, StartWindow, utc, limits
from cj_feasibility.solver import solve
a = item('a', start=event('2026-10-22','23:30'), end=event('2026-10-23','00:30'))
p = problem([a], selected=frozenset({{'a'}}), windows=(StartWindow('a',utc(16,30),utc(16,30)),))
r = solve(p, limits(), stop=Event())
print(json.dumps(dict(preloaded=preloaded, budget=limits().max_solve_seconds, status=r.status, reason=r.reason)))
''')
                self.assertEqual(run.returncode, 0, run.stderr)
                result = json.loads(run.stdout)
                self.assertTrue(result['preloaded'], result)
                self.assertEqual(result['budget'], 5.0)
                self.assertEqual(result['status'], 'CONDITIONAL_SOLUTION', result)

    def test_native_import_failure_aborts_startup(self):
        for startup in STARTUPS:
            with self.subTest(startup=startup):
                run = process(f'''
import importlib.abc, sys
class MissingNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'ortools' or fullname.startswith('ortools.'):
            raise ModuleNotFoundError('CJ176_NATIVE_IMPORT_FAILED')
sys.meta_path.insert(0, MissingNative())
{startup}
print('STARTUP_SUCCEEDED')
''')
                self.assertNotEqual(run.returncode, 0, run.stdout)
                self.assertIn('CJ176_NATIVE_IMPORT_FAILED', run.stderr)
                self.assertNotIn('STARTUP_SUCCEEDED', run.stdout)

    def test_model_phase_still_consumes_the_original_budget(self):
        from test_solver import route_problem, limits
        from cj_feasibility.solver import solve
        from ortools.sat.python import cp_model
        # Only the test clock advances: real preparation/model construction still run.
        with patch('time.monotonic', side_effect=[0.0, 0.0, 6.0]), patch.object(cp_model.CpSolver, 'solve') as engine:
            result = solve(route_problem(), limits(), stop=Event())
        self.assertEqual((result.status, result.reason), ('TIMEOUT', 'MODEL_BUDGET_EXHAUSTED'))
        self.assertIsNone(result.candidate)
        engine.assert_not_called()
