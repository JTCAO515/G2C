"""Synthetic-only CLI regressions for CJ-028 input robustness feedback."""
import copy
from contextlib import redirect_stdout
from decimal import Decimal, localcontext, Overflow
import io
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cj028_boundaries', ROOT / 'evaluate.py')
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)


class SyntheticInputBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((ROOT / 'fixtures/synthetic-plan.json').read_text())
        self.records = json.loads((ROOT / 'fixtures/synthetic-observations.json').read_text())

    def cli(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / 'plan.json'
            records = Path(directory) / 'records.json'
            plan.write_text(json.dumps(self.plan))
            records.write_text(json.dumps(self.records))
            return subprocess.run([sys.executable, str(ROOT / 'evaluate.py'), '--scenarios', str(plan),
                                   '--observations', str(records)], capture_output=True, text=True)

    def assert_rejected_with_records(self):
        run = self.cli()
        print('synthetic CLI: exit={}, stdout_bytes={}, traceback={}'.format(
            run.returncode, len(run.stdout.encode()), 'Traceback' in run.stderr))
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertEqual(run.stderr, '')
        report = json.loads(run.stdout)
        self.assertEqual(report['validation'], 'FAIL')
        self.assertEqual(report['release_decision'], 'UNKNOWN')
        self.assertEqual(report['raw_observations'], self.records)
        self.assertEqual(report['plan'], self.plan)
        return report

    def test_schema_requires_integer_not_boolean_or_float(self):
        for value in (True, 1.0):
            with self.subTest(value=value):
                self.plan['schema_version'] = value
                self.assert_rejected_with_records()

    def test_extreme_finite_decimal_returns_structured_error(self):
        self.records[0]['cost']['components'][0]['amount'] = '1e1000000'
        self.records[0]['status'] = 'failure'
        self.assert_rejected_with_records()

    def test_out_of_range_amounts_preserve_failure_and_unknown_cost(self):
        component = self.records[0]['cost']['components'][0]
        self.records[0]['status'] = 'failure'
        unknown = copy.deepcopy(component)
        unknown.update(name='synthetic-unknown-tool-cost', amount=None)
        self.records[0]['cost']['components'].append(unknown)
        for value in ('1e101', '1e-101', '1' * 101, '0' * 257, '0e101'):
            with self.subTest(value=value):
                component['amount'] = value
                report = self.assert_rejected_with_records()
                self.assertIsNone(report['raw_observations'][0]['cost']['components'][1]['amount'])

    def test_boundary_sum_is_exact_despite_ambient_precision(self):
        values = [evaluate.amount(v) for v in ('9' * 100, '1e100', '1e-100', '0')]
        expected = Decimal('1' + '9' * 100 + '.' + '0' * 99 + '1')
        with localcontext() as context:
            context.prec = 3
            context.Emax = 3
            context.Emin = -3
            self.assertEqual(evaluate.exact_sum(values), expected)
        self.assertEqual(evaluate.exact_sum([Decimal('0'), Decimal('0e100')]), Decimal('0'))

    def test_decimal_exception_fallback_returns_structured_error(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / 'plan.json'
            records = Path(directory) / 'records.json'
            plan.write_text(json.dumps(self.plan))
            records.write_text(json.dumps(self.records))
            output = io.StringIO()
            with patch.object(evaluate, 'exact_sum', side_effect=Overflow('synthetic decimal fault')):
                with redirect_stdout(output):
                    code = evaluate.main(['--scenarios', str(plan), '--observations', str(records)])
            self.assertEqual(code, 2)
            report = json.loads(output.getvalue())
            self.assertEqual(report['release_decision'], 'UNKNOWN')
            self.assertEqual(report['raw_observations'], self.records)

    def test_long_significand_sum_is_exact(self):
        value = '1234567890123456789012345678901234567890.123456789'
        components = self.records[0]['cost']['components']
        components[0]['amount'] = value
        extra = copy.deepcopy(components[0])
        extra.update(name='synthetic-extra-cost', amount='0.000000001')
        components.append(extra)
        run = self.cli()
        self.assertEqual(run.returncode, 0, run.stderr)
        report = json.loads(run.stdout)
        group = next(g for g in report['groups'] if g['language'] == 'zh' and g['split'] == 'tuning')
        self.assertEqual(group['cost']['known_subtotals_by_currency']['USD'],
                         '1234567890123456789012345678901234567890.123456790')
        self.assertEqual(report['release_decision'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
