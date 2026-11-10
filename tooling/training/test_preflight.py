"""Synthetic boundary cases; these do not establish a real model/template PASS."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import unittest

from preflight import Invalid, check_config, check_swift_row, main, read_json


def tool_row():
    return {'tools': [{'type': 'function', 'function': {
        'name': 'lookup', 'parameters': {'type': 'object', 'properties': {
            'city': {'type': 'string'}}, 'required': ['city'], 'additionalProperties': False}}}],
        'messages': [{'role': 'user', 'content': '合成问题'},
                     {'role': 'assistant', 'content': None, 'tool_calls': [{
                         'id': 'call-1', 'type': 'function', 'function': {
                             'name': 'lookup', 'arguments': '{"city":"北京"}'}}]},
                     {'role': 'tool', 'tool_call_id': 'call-1', 'content': '{"status":"failed"}'},
                     {'role': 'assistant', 'content': '工具失败，无法确认。'}]}


class BoundaryTests(unittest.TestCase):
    def test_direct_and_clarification_and_cancel(self):
        for answer in ('合成回答', '请补充日期', '已取消，未执行操作'):
            check_swift_row({'messages': [{'role': 'user', 'content': 'synthetic'},
                                         {'role': 'assistant', 'content': answer}]})

    def test_tool_failure_and_parallel_receipts(self):
        row = tool_row()
        check_swift_row(row)
        call = deepcopy(row['messages'][1]['tool_calls'][0])
        call['id'] = 'call-2'
        row['messages'][1]['tool_calls'].append(call)
        row['messages'].insert(3, {'role': 'tool', 'tool_call_id': 'call-2', 'content': '{}'})
        check_swift_row(row)

    def test_missing_messages(self):
        with self.assertRaisesRegex(Invalid, 'MISSING_MESSAGES'):
            check_swift_row({})

    def test_wrong_receipt(self):
        row = tool_row()
        row['messages'][2]['tool_call_id'] = 'different-call'
        with self.assertRaisesRegex(Invalid, 'WRONG_TOOL_ASSOCIATION'):
            check_swift_row(row)

    def test_missing_receipt(self):
        row = tool_row()
        del row['messages'][2]
        with self.assertRaisesRegex(Invalid, 'MISSING_TOOL_RESULT'):
            check_swift_row(row)

    def test_duplicate_call(self):
        row = tool_row()
        row['messages'][1]['tool_calls'] *= 2
        with self.assertRaisesRegex(Invalid, 'DUPLICATE_CALL_ID'):
            check_swift_row(row)

    def test_unknown_tool(self):
        row = tool_row()
        row['messages'][1]['tool_calls'][0]['function']['name'] = 'other'
        with self.assertRaisesRegex(Invalid, 'UNKNOWN_TOOL_NAME'):
            check_swift_row(row)

    def test_arguments_schema_and_missing_field(self):
        for value in ('{}', '{"city":1}', '{"city":"北京","secret":"no"}'):
            row = tool_row()
            row['messages'][1]['tool_calls'][0]['function']['arguments'] = value
            with self.assertRaisesRegex(Invalid, 'INVALID_TOOL_ARGUMENTS'):
                check_swift_row(row)

    def test_duplicate_json_and_nan(self):
        for text in ('{"messages":[],"messages":[]}', '{"x":NaN}'):
            with self.assertRaises(Invalid):
                read_json(text)

    def test_unknown_role(self):
        row = tool_row()
        row['messages'][0]['role'] = 'unrecognized'
        with self.assertRaisesRegex(Invalid, 'UNKNOWN_MESSAGE_ROLE'):
            check_swift_row(row)

    def test_external_schema_cannot_fetch_and_messages_cannot_override_loss(self):
        row = tool_row()
        row['tools'][0]['function']['parameters']['$ref'] = 'https://invalid.example/schema'
        with self.assertRaisesRegex(Invalid, 'UNSUPPORTED_TOOL_SCHEMA_REFERENCE'):
            check_swift_row(row)
        row = tool_row()
        row['messages'][2]['loss'] = True
        with self.assertRaisesRegex(Invalid, 'UNSUPPORTED_MESSAGE_LOSS_OVERRIDE'):
            check_swift_row(row)

    def test_unknown_data_version_and_missing_f_schema(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(['dataset', 'not-read.jsonl', '--version', 'invented-v1'])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())['status'], 'UNRUN')
        self.assertIn('UNKNOWN_DATA_VERSION', output.getvalue())

    def test_config_reports_all_missing_choices(self):
        config = read_json(Path(__file__).with_name('sft.example.json').read_text())
        self.assertEqual(len(check_config(config)), 7)
        config['loss_scale'] = 'all'
        self.assertIn('UNSAFE_CONFIG:loss_scale', check_config(config))


if __name__ == '__main__':
    unittest.main()
