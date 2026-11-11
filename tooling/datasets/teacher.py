"""F789 Fake-only producer -> C execution verification -> F admission -> D handoff.

There is no live adapter, authorization switch, credential input or network call.
The public F768 scripts are Fake fixtures, never prompts for real teacher calls.
"""
import argparse
import base64
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import subprocess
from typing import Literal

from jsonschema import Draft202012Validator

from cj_api.real_services import canonical_tool
from cj_agent.provider import ProviderUnknown
from cj_fact.policy import FactFailure
from cj_place import ORIGIN, Config, Response, Search, parse_response, prepare
from cj_place.contract_v1 import decode_query, encode_result

from .convert import HERE, ROOT, SCHEMA, TOOLS_HASH, VERSION, Rejected, canonical, convert, digest, load, sha, validate
from .samples import examples, partial_failure

HANDOFF_VERSION = 'G2C-teacher-handoff.1'
FAKE_VERSION = 'F789-fake.1'
MESSAGE = Draft202012Validator(SCHEMA['properties']['messages']['items'])
REGISTRY = HERE / 'teacher-known-bad.v1.json'


@dataclass(frozen=True)
class Limits:
    model: int = 400
    tool: int = 400

    def __post_init__(self):
        if any(type(v) is not int or not 0 <= v <= 400 for v in (self.model, self.tool)):
            raise ValueError('fake_request_limits_must_be_0_to_400')


@dataclass(frozen=True)
class Case:
    name: str
    template: dict
    fault: str | None = None


@dataclass(frozen=True)
class Reply:
    state: Literal['received', 'failed', 'unknown']
    raw: bytes | None
    visible_partial: bool = False


def registry():
    """Versioned control configuration, using the one canonical message schema."""
    value = load(REGISTRY.read_bytes())
    if (type(value) is not dict or set(value) != {'version', 'replies'} or
            value['version'] != 'G2C-teacher-known-bad.1' or
            type(value['replies']) is not list or not value['replies']):
        raise Rejected('invalid_known_bad_registry')
    result = {}
    for entry in value['replies']:
        if (type(entry) is not dict or set(entry) != {'id', 'message', 'reason', 'source'} or
                any(type(entry[k]) is not str or not entry[k].strip() for k in ('id', 'reason', 'source')) or
                any(MESSAGE.iter_errors(entry['message'])) or entry['message']['role'] != 'assistant'):
            raise Rejected('invalid_known_bad_registry')
        key = digest(entry['message'])
        if key in result:
            raise Rejected('duplicate_known_bad_control')
        result[key] = entry
    return result


def decode_reply(raw, bad):
    try:
        if not 0 < len(raw) <= 1048576:
            raise ValueError('reply_size')
        message = load(raw)
        canonical(message).encode('utf8')
    except (ValueError, UnicodeError, RecursionError):
        raise Rejected('teacher_json_invalid') from None
    if any(MESSAGE.iter_errors(message)):
        raise Rejected('teacher_message_schema')
    if message['role'] != 'assistant':
        raise Rejected('teacher_cannot_supply_tool_or_user_messages')
    if 'tool_calls' not in message and not message['content'].strip():
        raise Rejected('teacher_empty_answer')
    if digest(message) in bad:
        raise Rejected(bad[digest(message)]['reason'])
    return message


def check_row(row):
    try:
        validate(row)
    except Rejected:
        raise
    except (ValueError, UnicodeError, RecursionError, ProviderUnknown, FactFailure):
        raise Rejected('invalid_domain_value') from None


class FakeTeacher:
    def reply(self, case, index, visible, attempt):
        """Only an assistant proposal. Tool results are not read from this script."""
        if case.fault == 'bad-json':
            return Reply('received', b'{broken json')
        if case.fault == 'invented-tool':
            return Reply('received', canonical(dict(role='tool', tool_call_id='invented', content='success')).encode())
        if case.fault == 'save-zh':
            return Reply('received', canonical(dict(role='assistant', content='已为你保存行程。')).encode())
        if case.fault == 'save-en':
            return Reply('received', canonical(dict(role='assistant', content='I have saved your trip.')).encode())
        if case.fault == 'unknown-model':
            return Reply('unknown', None)
        partial = case.template['run']['answer_state'] == 'partial'
        return Reply('unknown' if partial else 'received',
                     canonical(case.template['messages'][index]).encode(), partial)


def execution(row, call, round_index, index):
    op = 'op-' + sha((row['run']['run_id'] + '\0' + f'tool.{round_index}.{index}').encode())
    return dict(tool_call_id=call['id'], attempt_id=row['run']['attempt_id'], run_id=row['run']['run_id'],
                operation_id=op, status='not_started', result=dict(state='unknown', value=None), error_code=None,
                evidence=dict(ref='tasks.json#' + row['sample_id'], attempt_id=row['run']['attempt_id'],
                              run_id=row['run']['run_id'], tool_call_id=call['id'], operation_id=op, status='not_started'))


class FakeTools:
    def execute(self, case, call, stub):
        """Local synthetic supplier bytes -> actual unchanged C parser/encoder.

        Received Search fixtures only. This is not a guessed B762 wire/API.
        """
        source_calls = [c for m in case.template['messages'] for c in m.get('tool_calls', [])]
        expected = next((c for c in source_calls if c['id'] == call['id']), None)
        if expected is None or canonical(call) != canonical(expected):
            raise Rejected('unplanned_fake_tool_request')
        planned = next(e for e in case.template['executions'] if e['tool_call_id'] == call['id'])
        result = deepcopy(stub)
        result['status'] = result['evidence']['status'] = planned['status']
        result['evidence']['ref'] = 'tools.jsonl#' + stub['operation_id']
        proof = dict(call=deepcopy(call), execution=result, response_state='unknown', response_base64=None)
        if planned['status'] == 'received':
            kind, raw_query = canonical_tool(call['function']['name'], call['function']['arguments'])
            query = decode_query(raw_query)
            if kind != 'place' or type(query) is not Search:
                raise Rejected('fake_received_codec_not_supported')
            empty = load(planned['result']['value'])['outcome'] == 'no_results'
            payload = dict(status='1', info='OK', infocode='10000', count='0' if empty else '1',
                           pois=[] if empty else [dict(id='SYNTH_F768', name='合成地点', address=[], location='116.1,39.1')])
            raw = canonical(payload).encode()
            at = datetime(2026, 11, 11, tzinfo=timezone.utc)
            config = Config(ORIGIN, 8192, 65536, 20, 60)
            request = prepare(config, query, stub['operation_id'], at, basic=True)
            response = Response(request.binding_digest, request.origin, request.path, 200, raw, at + timedelta(seconds=1))
            actual = parse_response(config, request, response, now=at + timedelta(seconds=2), evidence='synthetic', basic=True)
            result['result'] = dict(state='present', value=encode_result(actual, evidence_kind='synthetic').decode())
            proof.update(response_state='present', response_base64=base64.b64encode(raw).decode(),
                         query=load(raw_query), request_ref=request.request_ref, binding_digest=request.binding_digest,
                         query_started_at=at.isoformat(), received_at=response.received_at.isoformat(), profile='basic-v3-default-zh')
        elif planned['status'] == 'failed':
            result['error_code'] = 'ProviderFailed'
        if case.fault == 'bad-receipt':
            result['evidence']['attempt_id'] = 'wrong-original-attempt'
        return proof


def cases(control='smoke'):
    source = examples()
    if control == 'unknown':
        return [Case('unknown-batch', partial_failure('en')), Case('must-not-start', source[0])]
    if control == 'bad-receipt':
        return [Case('bad-receipt', next(r for r in source if r['scenario'] == 'tool_result'), 'bad-receipt'),
                Case('must-not-start', source[0])]
    result = [Case(r['sample_id'], r) for r in source if r['run']['status'] != 'unknown']
    result.append(Case('duplicate-direct', source[0]))
    for fault, language in [('bad-json', 'zh'), ('invented-tool', 'zh'), ('save-zh', 'zh'), ('save-en', 'en')]:
        template = deepcopy(next(r for r in source if r['scenario'] == 'direct_answer' and r['language'] == language))
        family = 'fake-negative-save' if fault.startswith('save-') else 'fake-negative-' + fault
        template.update(task_id=family, trip_family=family, rewrite_family=family)
        result.append(Case(fault, template, fault))
    return result


class LimitReached(Exception):
    pass


def generate(case, batch, teacher, tools, counts, limits, bad, model_events, tool_events):
    row = deepcopy(case.template)
    row.update(sample_id=case.name, messages=[], executions=[],
               source=dict(kind='synthetic_fixture', source_id='fake/' + batch + '/' + case.name, revision=FAKE_VERSION))
    row['versions'].update(model='FakeTeacher.1', prompt='F768-public-scripts.1', adapter=FAKE_VERSION)
    row['run'] = dict(attempt_id='fake-task/' + batch + '/' + case.name, run_id='fake-run/' + batch + '/' + case.name,
                      status='unknown', answer_state='none', evidence_ref='tasks.json#' + case.name)
    start = dict(counts)
    phase, round_index, unsettled = 'teacher', 0, False
    status, reason, candidate = 'PASS', None, None
    try:
        for index, scripted in enumerate(case.template['messages']):
            role = scripted['role']
            if role == 'tool':
                continue  # Never copy a script's claimed result into the generated transcript.
            if role in ('user', 'system'):
                row['messages'].append(deepcopy(scripted))
                continue
            phase = 'teacher'
            if counts['model'] >= limits.model or counts['model'] - start['model'] >= 8:
                raise LimitReached('model_request_limit')
            attempt = row['run']['attempt_id'] + '/model/' + str(counts['model'] - start['model'])
            counts['model'] += 1
            reply = teacher.reply(case, index, deepcopy(row['messages']), attempt)
            unsettled = reply.state == 'unknown'
            model_events.append(dict(attempt_id=attempt, task_attempt_id=row['run']['attempt_id'],
                                     model_version=row['versions']['model'], prompt_version=row['versions']['prompt'],
                                     adapter_version=FAKE_VERSION, tools_sha256=TOOLS_HASH,
                                     state=reply.state, input_messages=deepcopy(row['messages']),
                                     response_base64=None if reply.raw is None else base64.b64encode(reply.raw).decode()))
            if reply.state != 'received':
                processing = {'failed': 'FAIL', 'unknown': 'UNKNOWN'}[reply.state]
                row['run'].update(status=reply.state, answer_state='none')
                if reply.state == 'unknown' and reply.visible_partial:
                    message = decode_reply(reply.raw, bad)
                    if 'tool_calls' in message:
                        raise Rejected('unverified_tool_proposal')
                    row['messages'].append(message)
                    row['run']['answer_state'] = 'partial'
                    check_row(row)
                    candidate = row
                return dict(processing_status=processing, reason='model_outcome_' + reply.state), candidate, row
            message = decode_reply(reply.raw, bad)
            row['messages'].append(message)
            if 'tool_calls' not in message:
                row['run'].update(status='completed', answer_state='complete')
                continue
            row['run'].update(status='unknown', answer_state='none')
            offset = len(row['executions'])
            row['executions'].extend(execution(row, call, round_index, i) for i, call in enumerate(message['tool_calls']))
            check_row(row)  # Untrusted proposals are admitted before the first execution.
            if case.template['run']['status'] == 'cancelled':
                row['run']['status'] = 'cancelled'
                check_row(row)
                return dict(processing_status='PASS', reason='cancelled_before_dispatch'), row, row
            phase = 'tool'
            for i, call in enumerate(message['tool_calls']):
                if counts['tool'] >= limits.tool or counts['tool'] - start['tool'] >= 8:
                    raise LimitReached('tool_request_limit')
                counts['tool'] += 1
                event = dict(call=deepcopy(call), requested_execution=deepcopy(row['executions'][offset + i]),
                             execution=None, response_state='unknown', response_base64=None)
                tool_events.append(event)
                try:
                    proof = tools.execute(case, call, row['executions'][offset + i])
                except Rejected as error:
                    event['reason'] = str(error)
                    raise
                event.update(deepcopy(proof))
                row['executions'][offset + i] = proof['execution']
                outcome = proof['execution']['status']
                row['run']['status'] = {'received': 'unknown', 'failed': 'failed', 'unknown': 'unknown',
                                        'cancelled': 'cancelled', 'not_started': 'cancelled'}[outcome]
                check_row(row)  # Verify actual result/query/op/receipt before exposing it to the teacher.
                if outcome != 'received':
                    return dict(processing_status='UNKNOWN' if outcome == 'unknown' else 'PASS',
                                reason='tool_' + outcome), row, row
            for i, call in enumerate(message['tool_calls']):
                actual = load(row['executions'][offset + i]['result']['value'])
                row['messages'].append(dict(role='tool', tool_call_id=call['id'], content=canonical(dict(
                    results=[dict(index=i, name=call['function']['name'], tool='place', result=actual)]))))
            round_index += 1
        phase = 'teacher'
        check_row(row)
        candidate = row
    except LimitReached as error:
        status, reason = 'UNRUN', str(error)
    except Rejected as error:
        # An unassociable execution may have occurred. Never continue dispatch or invent its outcome.
        status, reason = ('UNKNOWN' if phase == 'tool' or unsettled else 'FAIL'), str(error)
    return dict(processing_status=status, reason=reason), candidate, row


def known_bad_report(bad):
    raw = (HERE / 'negative.v1.jsonl').read_bytes()
    negative = convert(raw)[-1]
    blocked = 0
    for entry in bad.values():
        try:
            decode_reply(canonical(entry['message']).encode(), bad)
        except Rejected as error:
            blocked += str(error) == entry['reason']
    count = len(raw.splitlines())
    return dict(status='PASS' if count and negative['accepted'] == 0 and negative['rejected'] == count and
                blocked == len(bad) else 'FAIL', canonical_controls=count, canonical_accepted=negative['accepted'],
                canonical_rejected=negative['rejected'],
                canonical_reasons=negative['rejection_reasons'], reply_controls=len(bad), replies_blocked=blocked,
                negative_sha256=sha(raw), reply_registry_sha256=sha(REGISTRY.read_bytes()))


def write_json(path, value):
    path.write_text(canonical(value) + '\n')


def write_jsonl(path, values):
    path.write_text(''.join(canonical(value) + '\n' for value in values))


def run_fake(output, batch, plan, teacher, tools, limits=Limits()):
    if re.fullmatch('[A-Za-z0-9_-]{1,64}', batch) is None or not plan:
        raise Rejected('nonempty_fake_plan_and_bounded_batch_id_required')
    bad = registry()
    output.mkdir(parents=True, exist_ok=False)
    counts, model_events, tool_events, tasks, raw_rows, candidates = dict(model=0, tool=0), [], [], [], [], []
    halted = None
    for case in plan:
        identity = dict(sample_id=case.name, task_id=case.template['task_id'], trip_family=case.template['trip_family'],
                        rewrite_family=case.template['rewrite_family'], language=case.template['language'],
                        scenario=case.template['scenario'])
        if halted is not None:
            tasks.append(dict(**identity,
                              processing_status='UNRUN', reason='batch_stopped', model_requests=0, tool_requests=0))
            continue
        before = dict(counts)
        result, candidate, raw = generate(case, batch, teacher, tools, counts, limits, bad, model_events, tool_events)
        result.update(**identity, model_requests=counts['model'] - before['model'],
                      tool_requests=counts['tool'] - before['tool'])
        tasks.append(result)
        raw_rows.append(dict(sample_id=case.name, processing_status=result['processing_status'], row=raw))
        if candidate is not None:
            candidates.append(candidate)
        if result['processing_status'] in ('UNKNOWN', 'UNRUN') or result['reason'] == 'model_outcome_failed':
            halted = result['processing_status']
    raw = ''.join(canonical(row) + '\n' for row in candidates).encode()
    split, lineage, rejected, groups, admission = convert(raw)
    controls = known_bad_report(bad)
    status = halted if halted is not None else 'PASS'
    if controls['status'] != 'PASS' or admission['status'] != 'PASS':
        status = status if status in ('UNKNOWN', 'UNRUN') else 'FAIL'
    generation = dict(planned=len(plan), attempted=sum(t['model_requests'] > 0 for t in tasks),
                      statuses=dict(Counter(t['processing_status'] for t in tasks)),
                      model_requests=counts['model'], tool_requests=counts['tool'], real_model_requests=0, real_tool_requests=0)
    report = dict(status=status, scope='fake_pipeline_only', generation=generation, admission=admission,
                  known_bad=controls, quality_status='UNRUN', training_status='UNRUN', release_status='UNRUN')
    retained = [r for rows in split.values() for r in rows]
    report['denominators'] = dict(
        planned_language_behavior=dict(Counter(t['language'] + '/' + t['scenario'] for t in tasks)),
        admitted_language_behavior=dict(Counter(r['language'] + '/' + r['scenario'] for r in retained)),
        admitted_run_states=dict(Counter(r['run']['status'] for r in retained)))
    write_json(output / 'planned-cases.json', [dict(sample_id=c.name, task_id=c.template['task_id'],
        trip_family=c.template['trip_family'], rewrite_family=c.template['rewrite_family'],
        language=c.template['language'], scenario=c.template['scenario'], fake_fault=c.fault,
        source_fixture_sha256=digest(c.template)) for c in plan])
    write_jsonl(output / 'candidates.jsonl', candidates)
    write_jsonl(output / 'raw-candidates.jsonl', raw_rows)
    write_jsonl(output / 'models.jsonl', model_events)
    write_jsonl(output / 'tools.jsonl', tool_events)
    write_json(output / 'tasks.json', tasks)
    write_json(output / 'lineage.json', lineage)
    write_json(output / 'rejected.json', dict(generation=[t for t in tasks if t['processing_status'] != 'PASS'], admission=rejected))
    write_json(output / 'known-bad.json', controls)
    write_json(output / 'report.json', report)
    for purpose, rows in split.items():
        write_jsonl(output / (purpose + '.jsonl'), rows)
    files = {p.name: dict(sha256=sha(p.read_bytes()), bytes=p.stat().st_size) for p in sorted(output.iterdir())}
    original = load((HERE / 'manifest.v1.json').read_bytes())
    sources = [*original['source_hashes'], 'tooling/datasets/teacher.py', 'tooling/datasets/teacher-known-bad.v1.json',
               'tooling/datasets/test_teacher.py', 'tooling/datasets/teacher-pipeline.md']
    manifest = dict(version=HANDOFF_VERSION, mode='fake', batch_id=batch, candidate_version=FAKE_VERSION,
                    parent_issue=767, producer_issue=789, independent_quality_issue=788,
                    record_schema=VERSION, tools_sha256=TOOLS_HASH,
                    repository_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    source_hashes={name: sha((ROOT / name).read_bytes()) for name in sources},
                    reference_manifest_sha256=sha((HERE / 'manifest.v1.json').read_bytes()),
                    artifacts=files, groups=groups, generation=generation, pipeline_status=status,
                    denominators=report['denominators'],
                    authorization_request_ref='https://github.com/JTCAO515/G2C/issues/495#issuecomment-6783714210',
                    original_cost_evidence=dict(status='UNRUN', reason='fake_has_no_original_meter', ledger_ref=None),
                    quality_status='UNRUN', release_eligibility='fake_only_not_released', training_status='UNRUN',
                    live_adapter_status='UNRUN', live_authorization_checked=False,
                    limits=dict(model_requests=limits.model, tool_requests=limits.tool, per_task=8),
                    semantic_quality='UNKNOWN')
    write_json(output / 'handoff.json', manifest)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('fake', 'real'), required=True)
    parser.add_argument('--batch-id', default='f789-smoke-v1')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--control', choices=('smoke', 'bad-receipt', 'unknown'), default='smoke')
    args = parser.parse_args(argv)
    if args.mode == 'real':
        print(canonical(dict(status='UNRUN', reason='REAL_ADAPTER_NOT_DELIVERED', real_requests=0,
                             required=['JT approval in #495', 'B #762 trusted exit and original budget guards',
                                       'reviewed teacher admission and task/version inputs'])))
        return 2
    report = run_fake(args.output, args.batch_id, cases(args.control), FakeTeacher(), FakeTools())
    print(canonical(report))
    return 0 if report['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
