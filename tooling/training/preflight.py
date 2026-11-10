"""Read-only preparation checks. Never downloads a model or starts training.

F owns the dataset schema. Until #768 is delivered, `dataset` fails closed.
`swift-jsonl` checks ONLY the official OpenAI input subset, not F provenance/QC.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend/strict_json'))
from cj_strict_json import reject_duplicates


class Invalid(ValueError):
    pass


def read_json(text):
    return json.loads(text, object_pairs_hook=reject_duplicates(Invalid, 'DUPLICATE_KEY'),
                      parse_constant=lambda value: fail('NON_FINITE_JSON'))


def fail(code):
    raise Invalid(code)


def check_swift_row(row):
    """Validate external OpenAI-formatted input BEFORE ms-swift drops call IDs.

    This is a constrained upstream interchange format, not a G2C data schema.
    No receipt/provenance/action-state claim can be made here.
    """
    from jsonschema import Draft202012Validator

    if not isinstance(row, dict):
        fail('ROW_NOT_OBJECT')
    messages = row.get('messages')
    if not isinstance(messages, list) or not messages:
        fail('MISSING_MESSAGES')
    tools = row.get('tools', [])
    if isinstance(tools, str):
        tools = read_json(tools)
    if not isinstance(tools, list):
        fail('TOOLS_NOT_LIST')
    functions = {}
    for tool in tools:
        if not isinstance(tool, dict) or tool.get('type') != 'function':
            fail('INVALID_TOOL_DEFINITION')
        function = tool.get('function')
        if not isinstance(function, dict):
            fail('MISSING_TOOL_FUNCTION')
        name, parameters = function.get('name'), function.get('parameters')
        if not isinstance(name, str) or not name or name in functions:
            fail('INVALID_OR_DUPLICATE_TOOL_NAME')
        if not isinstance(parameters, dict):
            fail('MISSING_TOOL_PARAMETERS')
        # Validation of an external schema must not fetch remote references.
        nodes = [parameters]
        while nodes:
            node = nodes.pop()
            if isinstance(node, dict):
                if '$ref' in node or '$dynamicRef' in node:
                    fail('UNSUPPORTED_TOOL_SCHEMA_REFERENCE')
                nodes.extend(node.values())
            elif isinstance(node, list):
                nodes.extend(node)
        Draft202012Validator.check_schema(parameters)
        functions[name] = Draft202012Validator(parameters)
    pending, seen = {}, set()
    user_seen = False
    for message in messages:
        if not isinstance(message, dict):
            fail('MESSAGE_NOT_OBJECT')
        if 'loss' in message or 'loss_scale' in message:
            fail('UNSUPPORTED_MESSAGE_LOSS_OVERRIDE')
        role = message.get('role')
        content = message.get('content')
        if role not in ('system', 'user', 'assistant', 'tool'):
            fail('UNKNOWN_MESSAGE_ROLE')
        if pending and role != 'tool':
            fail('MISSING_TOOL_RESULT')
        if role == 'tool':
            call_id = message.get('tool_call_id')
            if not isinstance(call_id, str) or call_id not in pending:
                fail('WRONG_TOOL_ASSOCIATION')
            if not isinstance(content, str) or not content:
                fail('MISSING_TOOL_RESULT_CONTENT')
            if 'name' in message and message['name'] != pending[call_id]:
                fail('WRONG_TOOL_NAME')
            del pending[call_id]
        elif role == 'assistant':
            if not user_seen:
                fail('ASSISTANT_WITHOUT_USER')
            calls = message.get('tool_calls', [])
            if not isinstance(calls, list):
                fail('TOOL_CALLS_NOT_LIST')
            if not calls and (not isinstance(content, str) or not content):
                fail('MISSING_ASSISTANT_CONTENT')
            if calls and content is not None and not isinstance(content, str):
                fail('INVALID_ASSISTANT_CONTENT')
            for call in calls:
                if not isinstance(call, dict) or call.get('type') != 'function':
                    fail('INVALID_TOOL_CALL')
                call_id, function = call.get('id'), call.get('function')
                if not isinstance(call_id, str) or not call_id or call_id in seen:
                    fail('INVALID_OR_DUPLICATE_CALL_ID')
                if not isinstance(function, dict):
                    fail('MISSING_CALL_FUNCTION')
                name = function.get('name')
                if not isinstance(name, str) or name not in functions:
                    fail('UNKNOWN_TOOL_NAME')
                arguments = function.get('arguments')
                if not isinstance(arguments, str):
                    fail('ARGUMENTS_NOT_JSON_STRING')
                arguments = read_json(arguments)
                if not isinstance(arguments, dict):
                    fail('ARGUMENTS_NOT_OBJECT')
                if not functions[name].is_valid(arguments):
                    fail('INVALID_TOOL_ARGUMENTS')
                pending[call_id] = name
                seen.add(call_id)
        else:
            if role == 'system' and user_seen:
                fail('LATE_SYSTEM_MESSAGE')
            if not isinstance(content, str) or not content:
                fail('MISSING_MESSAGE_CONTENT')
            user_seen |= role == 'user'
        if role != 'assistant' and 'tool_calls' in message:
            fail('TOOL_CALLS_ON_WRONG_ROLE')
        if role != 'tool' and 'tool_call_id' in message:
            fail('TOOL_RESULT_ON_WRONG_ROLE')
    if pending:
        fail('MISSING_TOOL_RESULT')
    if messages[-1]['role'] != 'assistant' or messages[-1].get('tool_calls'):
        fail('MISSING_FINAL_ASSISTANT')


def check_config(config):
    """Report missing experiment choices without manufacturing a ready run."""
    if not isinstance(config, dict):
        fail('CONFIG_NOT_OBJECT')
    missing = [key for key in ('model', 'model_revision', 'template', 'agent_template',
                              'dataset', 'val_dataset', 'output_dir') if not config.get(key)]
    errors = ['MISSING_CONFIG:' + key for key in missing]
    required = {'loss_scale': 'default', 'template_backend': 'swift', 'strict': True,
                'disable_auto_column_mapping': True, 'split_dataset_ratio': 0,
                'packing': False, 'padding_free': False, 'save_only_model': False,
                'push_to_hub': False, 'report_to': ['none']}
    errors.extend('UNSAFE_CONFIG:' + key for key, value in required.items()
                  if config.get(key) != value)
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    config = commands.add_parser('config')
    config.add_argument('path', type=Path)
    dataset = commands.add_parser('dataset')
    dataset.add_argument('path', type=Path)
    dataset.add_argument('--version', required=True)
    upstream = commands.add_parser('swift-jsonl')
    upstream.add_argument('path', type=Path)
    args = parser.parse_args(argv)
    if args.command == 'dataset':
        print(json.dumps({'status': 'UNRUN', 'code': 'UNKNOWN_DATA_VERSION',
                          'reason': 'F_SCHEMA_UNAVAILABLE: #768 has no delivered version/adapter; '
                                    'no G2C dataset is accepted. See README missing-input list.'}))
        return 2
    try:
        if args.command == 'config':
            errors = check_config(read_json(args.path.read_text()))
        else:
            errors, rows = [], 0
            from jsonschema.exceptions import SchemaError
            with args.path.open(encoding='utf-8') as source:
                for number, line in enumerate(source, 1):
                    rows += 1
                    try:
                        check_swift_row(read_json(line))
                    except (Invalid, json.JSONDecodeError, SchemaError) as error:
                        # Never echo input, arguments, receipts, or raw schema errors.
                        code = str(error) if isinstance(error, Invalid) else type(error).__name__
                        errors.append(f'line={number}:{code}')
            if rows == 0:
                errors.append('EMPTY_DATASET')
    except (OSError, UnicodeError, json.JSONDecodeError, Invalid) as error:
        print(json.dumps({'status': 'FAIL', 'code': type(error).__name__}))
        return 1
    print(json.dumps({'status': 'FAIL' if errors else 'PASS', 'scope': args.command,
                      'errors': errors, 'training_readiness': 'UNRUN'}))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
