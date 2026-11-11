from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .convert import canonical, load, sha
from .samples import examples
from .teacher import Case, FakeTeacher, FakeTools, Limits, Reply, cases, main, run_fake
from . import teacher as pipeline


class SpyTeacher(FakeTeacher):
    def __init__(self):
        self.inputs = []

    def reply(self, case, index, visible, attempt):
        self.inputs.append(dict(case=case.name, messages=deepcopy(visible), attempt=attempt))
        return super().reply(case, index, visible, attempt)


class SpyTools(FakeTools):
    def __init__(self):
        self.calls = []

    def execute(self, case, call, stub):
        self.calls.append(deepcopy(stub))
        return super().execute(case, call, stub)


class TeacherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def produce(self, name='bundle', control='smoke', teacher=None, tools=None, plan=None, limits=Limits()):
        output = self.root / name
        teacher = SpyTeacher() if teacher is None else teacher
        tools = SpyTools() if tools is None else tools
        report = run_fake(output, 'f789-smoke-v1', cases(control) if plan is None else plan, teacher, tools, limits)
        return output, report, teacher, tools

    def test_full_pipeline_counts_and_pending_quality(self):
        output, report, teacher, tools = self.produce()
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['generation'], dict(planned=21, attempted=21,
                         statuses=dict(PASS=17, FAIL=4), model_requests=31, tool_requests=6,
                         real_model_requests=0, real_tool_requests=0))
        self.assertEqual(len(teacher.inputs), 31)
        self.assertEqual(len(tools.calls), 6)
        self.assertEqual((report['admission']['accepted'], report['admission']['duplicates']), (16, 1))
        self.assertEqual(report['known_bad']['canonical_rejected'], 17)
        self.assertEqual(report['known_bad']['replies_blocked'], 2)
        manifest = load((output / 'handoff.json').read_bytes())
        self.assertEqual(manifest['mode'], 'fake')
        self.assertEqual(manifest['record_schema'], 'G2C-dataset.1')
        self.assertEqual(manifest['independent_quality_issue'], 788)
        self.assertEqual(manifest['release_eligibility'], 'fake_only_not_released')
        for key in ('quality_status', 'training_status', 'live_adapter_status'):
            self.assertEqual(manifest[key], 'UNRUN')
        self.assertFalse(manifest['live_authorization_checked'])

    def test_actual_results_are_fresh_and_visible_only_after_verification(self):
        output, report, teacher, tools = self.produce()
        rows = [load(line) for line in (output / 'candidates.jsonl').read_bytes().splitlines()]
        result = next(r for r in rows if r['task_id'] == 'f768-result' and r['language'] == 'en')
        actual = load(result['executions'][0]['result']['value'])
        op = result['executions'][0]['operation_id']
        self.assertEqual(actual['source']['request_ref'], op)
        self.assertTrue(result['run']['run_id'].startswith('fake-run/f789-smoke-v1/'))
        self.assertNotEqual(actual['source']['request_ref'],
                            load(next(r for r in examples() if r['sample_id'] == 'f768-result/en')['executions'][0]['result']['value'])['source']['request_ref'])
        followup = next(e for e in teacher.inputs if e['case'] == 'f768-result/en' and e['messages'][-1]['role'] == 'tool')
        self.assertEqual(load(followup['messages'][-1]['content'])['results'][0]['result'], actual)
        events = [load(line) for line in (output / 'tools.jsonl').read_bytes().splitlines()]
        proof = next(e for e in events if e['execution']['operation_id'] == op)
        self.assertEqual(proof['response_state'], 'present')
        self.assertEqual(proof['request_ref'], op)

    def test_original_family_language_split_and_duplicate_sources_preserved(self):
        output, _, _, _ = self.produce()
        rows = {r['sample_id']: r for r in map(load, (output / 'candidates.jsonl').read_bytes().splitlines())}
        lineage = load((output / 'lineage.json').read_bytes())
        for key in ('trip_family', 'task_id', 'rewrite_family'):
            uses = {}
            for item in lineage:
                uses.setdefault(rows[item['sample_id']][key], set()).add(item['split'])
            self.assertTrue(all(len(splits) == 1 for splits in uses.values()))
        duplicate = next(e for e in lineage if e['reason'] == 'duplicate_content')
        retained = next(e for e in lineage if e['sample_id'] == duplicate['retained_sample_id'])
        self.assertNotEqual(retained['source']['source_id'], duplicate['source']['source_id'])
        self.assertEqual(retained['group_id'], duplicate['group_id'])

    def test_cancel_and_known_failure_are_controls_without_fabricated_result(self):
        output, _, _, tools = self.produce()
        rows = list(map(load, (output / 'candidates.jsonl').read_bytes().splitlines()))
        cancelled = [r for r in rows if r['run']['status'] == 'cancelled']
        self.assertEqual(len(cancelled), 2)
        self.assertTrue(all(r['executions'][0]['status'] == 'not_started' for r in cancelled))
        dispatched = {e['operation_id'] for e in tools.calls}
        self.assertTrue(all(r['executions'][0]['operation_id'] not in dispatched for r in cancelled))
        failed = [r for r in rows if r['run']['status'] == 'failed']
        self.assertEqual(len(failed), 2)
        self.assertTrue(all(r['executions'][0]['result'] == dict(state='unknown', value=None) for r in failed))
        self.assertTrue(all(not any(m['role'] == 'tool' for m in r['messages']) for r in failed))

    def test_bad_teacher_proposals_are_quarantined_before_tools(self):
        output, report, _, tools = self.produce()
        rejected = load((output / 'rejected.json').read_bytes())['generation']
        self.assertEqual(len(rejected), 4)
        self.assertEqual({t['reason'] for t in rejected},
                         {'teacher_json_invalid', 'teacher_cannot_supply_tool_or_user_messages', 'known_unverified_write_claim'})
        self.assertTrue(all(t['tool_requests'] == 0 for t in rejected))
        self.assertEqual(report['generation']['real_model_requests'], 0)

    def test_wrong_receipt_stops_without_repair_or_further_dispatch(self):
        output, report, teacher, tools = self.produce(control='bad-receipt')
        self.assertEqual(report['status'], 'UNKNOWN')
        self.assertEqual((len(teacher.inputs), len(tools.calls)), (1, 1))
        self.assertEqual(report['admission']['accepted'], 0)
        tasks = load((output / 'tasks.json').read_bytes())
        self.assertEqual([t['processing_status'] for t in tasks], ['UNKNOWN', 'UNRUN'])
        self.assertEqual(tasks[0]['reason'], 'receipt_association')
        proof = load((output / 'tools.jsonl').read_bytes().splitlines()[0])
        self.assertEqual(proof['execution']['evidence']['attempt_id'], 'wrong-original-attempt')

    def test_tool_without_a_receipt_still_keeps_the_original_request(self):
        class NoReceipt(FakeTools):
            def execute(self, case, call, stub):
                from .convert import Rejected
                raise Rejected('fake_supplier_unavailable')
        output, report, teacher, _ = self.produce(control='bad-receipt', tools=NoReceipt())
        self.assertEqual(report['status'], 'UNKNOWN')
        self.assertEqual(report['generation']['model_requests'], 1)
        self.assertEqual(report['generation']['tool_requests'], 1)
        proof = load((output / 'tools.jsonl').read_bytes().splitlines()[0])
        self.assertIsNone(proof['execution'])
        self.assertTrue(proof['requested_execution']['operation_id'].startswith('op-'))
        self.assertEqual(proof['reason'], 'fake_supplier_unavailable')
        self.assertEqual(len(teacher.inputs), 1)

    def test_partial_batch_unknown_preserves_actual_unseen_result_and_stops(self):
        output, report, teacher, tools = self.produce(control='unknown')
        self.assertEqual(report['status'], 'UNKNOWN')
        self.assertEqual((len(teacher.inputs), len(tools.calls)), (1, 2))
        row = load((output / 'candidates.jsonl').read_bytes().splitlines()[0])
        self.assertEqual([e['status'] for e in row['executions']], ['received', 'unknown'])
        self.assertEqual([m['role'] for m in row['messages']], ['user', 'assistant'])
        self.assertEqual(row['run']['answer_state'], 'none')
        self.assertEqual(report['generation']['statuses'], dict(UNKNOWN=1, UNRUN=1))

    def test_unknown_model_never_dispatches_unsettled_tool_proposal(self):
        class Unsettled(FakeTeacher):
            def reply(self, case, index, visible, attempt):
                reply = super().reply(case, index, visible, attempt)
                return Reply('unknown', reply.raw)
        plan = [Case('unknown', next(r for r in examples() if r['task_id'] == 'f768-result')), cases()[0]]
        output, report, _, tools = self.produce(plan=plan, teacher=Unsettled())
        self.assertEqual(report['status'], 'UNKNOWN')
        self.assertEqual(tools.calls, [])
        self.assertEqual(report['generation']['model_requests'], 1)
        self.assertEqual((output / 'candidates.jsonl').read_bytes(), b'')

    def test_known_model_failure_is_not_relabelled_unknown_or_retried(self):
        class Failed(FakeTeacher):
            def reply(self, case, index, visible, attempt):
                return Reply('failed', None)
        output, report, _, tools = self.produce(teacher=Failed())
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['generation']['model_requests'], 1)
        self.assertEqual(tools.calls, [])
        tasks = load((output / 'tasks.json').read_bytes())
        self.assertEqual(tasks[0]['reason'], 'model_outcome_failed')
        self.assertEqual(tasks[0]['processing_status'], 'FAIL')
        self.assertTrue(all(t['processing_status'] == 'UNRUN' for t in tasks[1:]))

    def test_invalid_partial_on_unknown_receipt_still_stops_the_batch(self):
        proposal = next(r for r in examples() if r['task_id'] == 'f768-result')['messages'][1]
        for index, raw in enumerate([b'{broken', canonical(proposal).encode(),
                                     canonical(dict(role='assistant', content='   ')).encode()]):
            class InvalidPartial(FakeTeacher):
                def reply(self, case, step, visible, attempt):
                    return Reply('unknown', raw, True)
            _, report, _, tools = self.produce(name='partial-' + str(index), teacher=InvalidPartial())
            self.assertEqual(report['status'], 'UNKNOWN')
            self.assertEqual(report['generation']['model_requests'], 1)
            self.assertEqual(tools.calls, [])
            self.assertEqual(report['generation']['statuses']['UNKNOWN'], 1)

    def test_invalid_arguments_and_empty_answer_do_not_reach_execution(self):
        source = next(r for r in examples() if r['task_id'] == 'f768-result')
        invalid = deepcopy(source['messages'][1])
        invalid['tool_calls'][0]['function']['arguments'] = canonical(dict(keyword=1))
        for index, message in enumerate([invalid, dict(role='assistant', content='   ')]):
            class Invalid(FakeTeacher):
                def reply(self, case, step, visible, attempt):
                    return Reply('received', canonical(message).encode())
            output, report, _, tools = self.produce(name='invalid-' + str(index),
                                                    plan=[Case('invalid', source)], teacher=Invalid())
            self.assertEqual(report['status'], 'FAIL')
            self.assertEqual(tools.calls, [])
            self.assertEqual(report['admission']['accepted'], 0)

    def test_known_bad_control_regression_blocks_handoff_success(self):
        original = pipeline.convert
        negative = (pipeline.HERE / 'negative.v1.jsonl').read_bytes()
        def regressed(raw):
            result = original(raw)
            if raw == negative:
                result[-1]['accepted'] = 1
            return result
        with patch.object(pipeline, 'convert', side_effect=regressed):
            output, report, _, _ = self.produce()
        self.assertEqual(report['known_bad']['status'], 'FAIL')
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(load((output / 'handoff.json').read_bytes())['quality_status'], 'UNRUN')

    def test_limits_stop_before_dispatch_and_never_clip_into_complete_task(self):
        for name, limits, expected_model in [('model', Limits(model=0), 0), ('tool', Limits(tool=0), 1)]:
            plan = [Case('query', next(r for r in examples() if r['task_id'] == 'f768-result')), cases()[0]]
            output, report, teacher, tools = self.produce(name=name, plan=plan, limits=limits)
            self.assertEqual(report['status'], 'UNRUN')
            self.assertEqual(report['generation']['model_requests'], expected_model)
            self.assertEqual(tools.calls, [])
            self.assertEqual(report['admission']['accepted'], 0)
        with self.assertRaises(ValueError):
            Limits(model=401)

    def test_bundle_repeats_bytes_hashes_and_refuses_overwrite(self):
        first, _, _, _ = self.produce('first')
        second, _, _, _ = self.produce('second')
        self.assertEqual({p.name: p.read_bytes() for p in first.iterdir()},
                         {p.name: p.read_bytes() for p in second.iterdir()})
        manifest = load((first / 'handoff.json').read_bytes())
        for name, item in manifest['artifacts'].items():
            self.assertEqual(item['sha256'], sha((first / name).read_bytes()))
        with self.assertRaises(FileExistsError):
            self.produce('first')

    def test_real_mode_refuses_without_constructing_any_runner_or_output(self):
        output = self.root / 'real'
        stream = io.StringIO()
        with patch('tooling.datasets.teacher.run_fake', side_effect=AssertionError('must not run')), redirect_stdout(stream):
            code = main(['--mode', 'real', '--output', str(output)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stream.getvalue())['status'], 'UNRUN')
        self.assertFalse(output.exists())

    def test_fake_never_uses_http_and_rejects_empty_plan(self):
        with patch('httpx.Client.send', side_effect=AssertionError('network forbidden')), \
                patch('httpx.AsyncClient.send', side_effect=AssertionError('network forbidden')):
            self.produce()
        with self.assertRaises(ValueError):
            self.produce('empty', plan=[])


if __name__ == '__main__':
    unittest.main()
