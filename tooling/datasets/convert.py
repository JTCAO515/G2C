"""Validate native B transcripts, group complete tasks, deduplicate and split.

Only local synthetic input is admitted in v1. Never invokes a model or tool.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator, FormatChecker

from cj_api.real_services import TOOLS, NATIVE_REGISTRATION, canonical_tool
from cj_agent.provider import ProviderUnknown
from cj_fact.policy import FactFailure
from cj_place.contract_v1 import decode_query, decode_result
from cj_strict_json import reject_duplicates

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
VERSION = 'G2C-dataset.1'
CONVERTER = 'G2C-dataset-converter.1'
SPLITS = ('train', 'validation', 'test')
SOURCE_FILES = (
    'backend/cj_api/real_services.py', 'backend/agent/cj_agent/provider.py',
    'backend/run/cj_run/tool_turn.py', 'backend/place/cj_place/contract_v1.py',
    'backend/strict_json/cj_strict_json/__init__.py',
    'contracts/run/MODEL-TOOL-TURN-STREAM-V1.md',
    'contracts/run/MODEL-TOOL-TURN-STREAM-V2.md', 'uv.lock',
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value).encode())


def invalid_constant(_):
    raise ValueError('non_json_number')


def load(raw):
    return json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate_json_key'),
                      parse_constant=invalid_constant)


SCHEMA = load((HERE / 'schema.v1.json').read_bytes())
VALIDATOR = Draft202012Validator(SCHEMA)
TOOLS_HASH = digest(TOOLS)
TOOLS_BY_NAME = {t['function']['name']: t['function']['parameters'] for t in TOOLS}


class Rejected(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Rejected(reason)


def validate(row):
    """One deserialization boundary; callers then use the established values."""
    require(not any(VALIDATOR.iter_errors(row)), 'schema_invalid')
    require(row['source']['kind'] in ('synthetic_manual', 'synthetic_fixture'), 'source_not_authorized')
    require(row['versions']['tool_schema_sha256'] == TOOLS_HASH, 'tool_schema_mismatch')
    messages = row['messages']
    require(any(m['role'] == 'user' for m in messages), 'user_message_required')
    calls, results, pending = {}, {}, set()
    round_index = 0
    queries = set()
    # Native tool results must follow their original calls, before another user/model turn.
    for index, message in enumerate(messages):
        role = message['role']
        if role == 'system':
            require(index == 0, 'system_position')
        if role in ('assistant', 'user'):
            require(not pending, 'unresolved_call_before_next_turn')
        if 'tool_calls' in message:
            for call_index, call in enumerate(message['tool_calls']):
                call_id, name = call['id'], call['function']['name']
                require(call_id not in calls, 'duplicate_tool_call_id')
                require(name in TOOLS_BY_NAME, 'unregistered_tool')
                arguments = load(call['function']['arguments'])
                validator = Draft202012Validator(TOOLS_BY_NAME[name], format_checker=FormatChecker())
                require(not any(validator.iter_errors(arguments)), 'tool_arguments_invalid')
                kind, query = canonical_tool(name, canonical(arguments))
                original_query = (kind, query)
                require(original_query not in queries, 'repeated_original_tool_query')
                queries.add(original_query)
                # Reuse the actual domain query codec rather than trusting the native shape alone.
                if kind == 'place':
                    decode_query(query)
                else:
                    from cj_fact.contract_v1 import decode_query as fact_query
                    from datetime import datetime, timezone
                    fact_query(query, evaluated_at=datetime(2026, 11, 11, tzinfo=timezone.utc))
                operation_id = 'op-' + sha((row['run']['run_id'] + '\0' +
                                          f'tool.{round_index}.{call_index}').encode())
                calls[call_id] = (name, load(query), call_index, operation_id)
                pending.add(call_id)
            round_index += 1
        if role == 'tool':
            call_id = message['tool_call_id']
            require(call_id in pending and call_id not in results, 'tool_result_association')
            results[call_id] = load(message['content'])
            pending.remove(call_id)
    require(len(calls) <= 8, 'per_run_tool_limit')
    executions = {}
    for execution in row['executions']:
        call_id = execution['tool_call_id']
        require(call_id in calls and call_id not in executions, 'execution_association')
        require(execution['attempt_id'] == row['run']['attempt_id'] and
                execution['run_id'] == row['run']['run_id'], 'execution_task_association')
        evidence = execution['evidence']
        require(all(evidence[k] == execution[k] for k in
                    ('attempt_id', 'run_id', 'tool_call_id', 'operation_id', 'status')), 'receipt_association')
        require(execution['operation_id'] == calls[call_id][3], 'operation_association')
        present = execution['result']['state'] == 'present'
        status = execution['status']
        require(present == (status == 'received'), 'execution_result_state')
        require((execution['error_code'] is not None) == (status == 'failed'), 'failure_code_state')
        if present:
            name, query, call_index, operation_id = calls[call_id]
            # PLACE has a frozen lossless result codec. Live FACT/weather and Lio projections
            # lack a dataset exporter: leave these explicitly unsupported until B/C deliver it.
            require(NATIVE_REGISTRATION[name] == 'place', 'result_codec_not_delivered')
            value = decode_result(execution['result']['value'].encode())
            require(value['query'] == query['query'], 'result_query_association')
            source = value['source']
            require(source is None or source['evidence_kind'] == 'synthetic', 'result_source_not_synthetic')
            require(source is None or source['request_ref'] == operation_id, 'result_receipt_association')
            expected = dict(results=[dict(index=call_index, name=name, tool='place', result=value)])
            require(call_id not in results or results[call_id] == expected, 'actual_result_mismatch')
        else:
            require(call_id not in results, 'fabricated_result_for_unreceived_call')
        executions[call_id] = execution
    require(set(executions) == set(calls), 'execution_missing')
    # Failed/unknown dispatches terminate the native task; do not manufacture a follow-up answer.
    # B appends messages only after every execution in a batch finishes. A preceding
    # received result may exist solely in execution evidence when a later call fails.
    for message in messages:
        if 'tool_calls' in message:
            batch_ids = {call['id'] for call in message['tool_calls']}
            visible = batch_ids & set(results)
            require(not visible or visible == batch_ids, 'partial_visible_tool_batch')
    require(not pending or row['run']['status'] in ('failed', 'unknown', 'cancelled', 'context_invalid'),
            'completed_with_unresolved_calls')
    require(not pending or messages[-1]['role'] in ('assistant', 'tool'), 'invalid_terminal_messages')
    require(row['run']['status'] != 'completed' or messages[-1]['role'] == 'assistant' and
            'tool_calls' not in messages[-1], 'completed_answer_missing')
    require(not any(e['status'] == 'failed' for e in executions.values()) or row['run']['status'] == 'failed',
            'failed_execution_run_mismatch')
    require(not any(e['status'] == 'unknown' for e in executions.values()) or row['run']['status'] == 'unknown',
            'unknown_execution_run_mismatch')
    return row


def content_hash(row):
    """Exact transcript dedup, ignoring supplier ID spelling; no semantic paraphrase claims."""
    messages = load(canonical(row['messages']))
    ids = {}
    for message in messages:
        for call in message.get('tool_calls', []):
            original = call['id']
            ids[original] = str(len(ids))
            call['id'] = ids[original]
        if message['role'] == 'tool':
            message['tool_call_id'] = ids[message['tool_call_id']]
    return digest(dict(messages=messages, run_status=row['run']['status'],
                       executions=[dict(status=e['status'], result=e['result'], error_code=e['error_code'])
                                   for e in row['executions']]))


def partition(rows, seed):
    """Connect all travel/task/rewrite identities AND exact duplicates before splitting."""
    parent = {}

    def root(key):
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    tokens = []
    for row in rows:
        keys = [f'{k}:{row[k]}' for k in ('trip_family', 'task_id', 'rewrite_family')]
        keys.append('content:' + content_hash(row))
        for key in keys[1:]:
            a, b = sorted((root(keys[0]), root(key)))
            parent[b] = a
        tokens.append(keys)
    components = {}
    for keys in tokens:
        components.setdefault(root(keys[0]), set()).update(keys)
    groups = {key: digest(sorted(values)) for key, values in components.items()}
    result = []
    for row, keys in zip(rows, tokens, strict=True):
        group = groups[root(keys[0])]
        bucket = int(sha((seed + '\0' + group).encode())[:16], 16) % 100
        split = 'train' if bucket < 80 else 'validation' if bucket < 90 else 'test'
        result.append((row, group, split))
    return result


def convert(raw, seed=VERSION):
    valid, rejected = [], []
    for line_no, line in enumerate(raw.splitlines(), 1):
        source = dict(line=line_no, input_sha256=sha(line))
        try:
            require(0 < len(line) <= 1048576, 'input_line_size')
            row = load(line)
            source.update({k: row[k] for k in ('sample_id', 'source') if type(row) is dict and k in row})
            valid.append((validate(row), source))
        except (ValueError, TypeError, UnicodeError, RecursionError, ProviderUnknown, FactFailure) as error:
            # Stable reason codes only: external payloads and parser text are not diagnostics.
            reason = str(error) if isinstance(error, Rejected) else 'invalid_json_or_domain_value'
            rejected.append(dict(**source, reason=reason))
    # Ambiguous sample IDs are rejected as a whole, never selected by input order.
    identities = {}
    for row, _ in valid:
        identities.setdefault(row['sample_id'], set()).add(digest(row))
    unambiguous = []
    for row, source in valid:
        if len(identities[row['sample_id']]) > 1:
            rejected.append(dict(**source, reason='sample_id_collision'))
        else:
            unambiguous.append((row, source))
    valid = sorted(unambiguous, key=lambda item: (item[0]['sample_id'], canonical(item[0])))
    grouped = partition([row for row, _ in valid], seed)
    output = {split: [] for split in SPLITS}
    seen, lineage = {}, []
    groups = {}
    for (row, group, split), (_, source) in zip(grouped, valid, strict=True):
        fingerprint = content_hash(row)
        duplicate = fingerprint in seen
        retained = seen.get(fingerprint, row['sample_id'])
        lineage.append(dict(**source, retained_sample_id=retained, group_id=group, split=split,
                            reason='duplicate_content' if duplicate else 'accepted'))
        groups.setdefault(group, dict(split=split, samples=[]))['samples'].append(row['sample_id'])
        if not duplicate:
            output[split].append(row)
            seen[fingerprint] = row['sample_id']
    report = dict(version=VERSION, status='FAIL' if rejected or not seen else 'PASS', scope='synthetic_structure_only',
                  input_rows=len(raw.splitlines()), accepted=sum(map(len, output.values())),
                  duplicates=sum(x['reason'] == 'duplicate_content' for x in lineage), rejected=len(rejected),
                  rejection_reasons=dict(sorted(Counter(x['reason'] for x in rejected).items())),
                  split_counts={s: len(output[s]) for s in SPLITS}, group_count=len(groups),
                  scenarios=dict(sorted(Counter(row['scenario'] for rows in output.values() for row in rows).items())),
                  unrun=['real_user_data', 'teacher_generation', 'training', 'model_quality', 'final_acceptance'])
    return output, sorted(lineage, key=lambda x: x['line']), sorted(rejected, key=lambda x: x['line']), groups, report


def write_release(input_path, output_path, seed):
    raw = input_path.read_bytes()
    output, lineage, rejected, groups, report = convert(raw, seed)
    # Releases never overwrite an earlier dataset or leave stale split files behind.
    output_path.mkdir(parents=True, exist_ok=False)
    files = {}
    for split, rows in output.items():
        files[split + '.jsonl'] = ''.join(canonical(row) + '\n' for row in rows).encode()
    files['lineage.json'] = (canonical(lineage) + '\n').encode()
    files['rejected.json'] = (canonical(rejected) + '\n').encode()
    files['quality.json'] = (canonical(report) + '\n').encode()
    files['tools.json'] = (canonical(TOOLS) + '\n').encode()
    for name, data in files.items():
        (output_path / name).write_bytes(data)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    tracked = (*SOURCE_FILES, 'tooling/datasets/schema.v1.json', 'tooling/datasets/convert.py',
               'tooling/datasets/samples.py', 'tooling/datasets/test_convert.py')
    manifest = dict(version=VERSION, converter_version=CONVERTER, repository_revision=revision,
                    input_sha256=sha(raw), schema_sha256=sha((HERE / 'schema.v1.json').read_bytes()),
                    tool_schema_sha256=TOOLS_HASH, source_hashes={p: sha((ROOT / p).read_bytes()) for p in tracked},
                    split_policy=dict(version='task-components-sha256.1', seed=seed, percentages=[80, 10, 10],
                                      note='public synthetic test; never final acceptance'),
                    groups=groups, artifacts={name: dict(sha256=sha(data), bytes=len(data)) for name, data in files.items()},
                    release_eligibility='synthetic_interface_only')
    (output_path / 'manifest.json').write_text(canonical(manifest) + '\n')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', default=VERSION)
    args = parser.parse_args(argv)
    report = write_release(args.input, args.output, args.seed)
    print(canonical(report))
    # Negative control corpora intentionally return nonzero while publishing diagnostics.
    return 2 if report['status'] == 'FAIL' else 0


if __name__ == '__main__':
    sys.exit(main())
