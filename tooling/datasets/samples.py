"""Rebuild public synthetic controls using local PLACE codecs; never sends requests."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cj_place import ORIGIN, Config, Response, Search, parse_response, prepare
from cj_place.contract_v1 import encode_result

from .convert import TOOLS_HASH, VERSION, canonical, sha

HERE = Path(__file__).resolve().parent


def message(role, content):
    return dict(role=role, content=content)


def row(task, language, scenario, messages, status='completed'):
    sample = task + '/' + language
    return dict(version=VERSION, sample_id=sample, task_id=task, trip_family='synthetic-trip/' + task,
                rewrite_family=task, language=language, scenario=scenario,
                source=dict(kind='synthetic_manual', source_id='F768/' + sample, revision='1'),
                versions=dict(trajectory='MODEL-TOOL-TURN-STREAM@2', tool_schema_sha256=TOOLS_HASH,
                              model=None, prompt=None, adapter=None),
                run=dict(attempt_id='synthetic-attempt/' + sample, run_id='synthetic-run/' + sample,
                         status=status, evidence_ref='synthetic-state/' + sample),
                messages=messages, executions=[])


def tool_sample(task, language, status, empty=False):
    chinese = language == 'zh'
    r = row(task, language, 'cancellation' if status == 'not_started' else 'tool_result' if status == 'received' else
            'tool_failure' if status == 'failed' else 'unknown_result', [],
            'completed' if status == 'received' else 'failed' if status == 'failed' else
            'cancelled' if status == 'not_started' else 'unknown')
    r['source']['kind'] = 'synthetic_fixture'
    arguments = dict(keyword='合成地点', city='北京', page=1, page_size=20)
    call_id = 'synthetic-call-' + task
    r['messages'] = [message('user', '请查合成地点。' if chinese else 'Find the synthetic place.'),
                     dict(role='assistant', content=None, tool_calls=[dict(id=call_id, type='function',
                          function=dict(name='place_search', arguments=canonical(arguments)))])]
    operation_id = 'op-' + sha((r['run']['run_id'] + '\0tool.0.0').encode())
    execution = dict(tool_call_id=call_id, attempt_id=r['run']['attempt_id'], run_id=r['run']['run_id'],
                     operation_id=operation_id, status=status,
                     result=dict(state='unknown', value=None),
                     error_code='ProviderFailed' if status == 'failed' else None,
                     evidence=dict(ref='synthetic-receipt/' + r['sample_id'], attempt_id=r['run']['attempt_id'],
                                   run_id=r['run']['run_id'], tool_call_id=call_id, operation_id=operation_id, status=status))
    if status == 'received':
        at = datetime(2026, 11, 11, tzinfo=timezone.utc)
        config = Config(ORIGIN, 8192, 65536, 20, 60)
        request = prepare(config, Search(**arguments), operation_id, at, basic=True)
        payload = dict(status='1', info='OK', infocode='10000', count='0' if empty else '1',
                       pois=[] if empty else [dict(id='SYNTH_F768', name='合成地点', address=[], location='116.1,39.1')])
        response = Response(request.binding_digest, request.origin, request.path, 200,
                            canonical(payload).encode(), at + timedelta(seconds=1))
        result = parse_response(config, request, response, now=at + timedelta(seconds=2), evidence='synthetic', basic=True)
        raw = encode_result(result, evidence_kind='synthetic').decode()
        execution['result'] = dict(state='present', value=raw)
        from .convert import load
        r['messages'].append(dict(role='tool', tool_call_id=call_id,
                                  content=canonical(dict(results=[dict(index=0, name='place_search', tool='place', result=load(raw))]))))
        answer = ('没有匹配结果。' if chinese else 'There are no matching results.') if empty else (
            '查到合成地点，英文官方名称未知。' if chinese else 'Found the synthetic place. Its official English name is unknown.')
        r['messages'].append(message('assistant', answer))
    r['executions'] = [execution]
    return r


def examples():
    rows = []
    texts = {
        'direct_answer': [('user', '北京公园散步适合穿什么？', 'What should I wear for a walk in a Beijing park?'),
                          ('assistant', '穿舒适的步行鞋，按天气增减衣物。', 'Wear comfortable walking shoes and dress for the weather.')],
        'clarification': [('user', '帮我规划北京行程。', 'Plan a Beijing trip for me.'),
                          ('assistant', '计划哪天出发、玩几天？', 'What is your start date and how many days will you stay?'),
                          ('user', '日期还不知道，玩三天。', 'The date is unknown. I will stay for three days.'),
                          ('assistant', '我可以先讨论三天的安排，具体日期确定后再核开放时间。',
                           'We can discuss a three-day outline and check opening hours once the dates are known.')],
        'correction': [('user', '三天北京游，偏好公园。', 'Three days in Beijing. I prefer parks.'),
                       ('assistant', '好的，先按三天和公园偏好讨论。', 'We can discuss three days with a focus on parks.'),
                       ('user', '改成两天，偏好不变。', 'Change that to two days. Keep my preferences.'),
                       ('assistant', '按两天讨论，保留公园偏好；目前尚未保存行程。',
                        'We will discuss two days and keep the park preference. No trip has been saved.')],
        'cancellation': [('user', '先帮我查地点。', 'Please look up a place.'),
                         ('assistant', '请告诉我地点名称。', 'What is the place name?'),
                         ('user', '取消，不用查了。', 'Cancel. Do not look it up.'),
                         ('assistant', '好的，停止这项查询。', 'Okay, I will stop this lookup.')],
    }
    for scenario, turns in texts.items():
        for language in ('zh', 'en'):
            rows.append(row('f768-' + scenario, language, scenario,
                            [message(role, zh if language == 'zh' else en) for role, zh, en in turns],
                            'completed'))
    for task, status, empty in [('f768-result', 'received', False), ('f768-empty', 'received', True),
                                ('f768-failure', 'failed', False), ('f768-unknown', 'unknown', False),
                                ('f768-cancelled', 'not_started', False)]:
        rows.extend(tool_sample(task, language, status, empty) for language in ('zh', 'en'))
    rows.extend(partial_failure(language) for language in ('zh', 'en'))
    return rows


def partial_failure(language):
    """B executes batch call 0, then loses call 1; neither result is model-visible."""
    r = tool_sample('f768-partial', language, 'received')
    r['scenario'] = 'tool_failure'
    r['run']['status'] = 'unknown'
    r['messages'] = r['messages'][:2]
    call_id = 'synthetic-call-partial-unknown'
    r['messages'][1]['tool_calls'].append(dict(id=call_id, type='function', function=dict(
        name='place_detail', arguments=canonical(dict(provider_id='SYNTH_F768')))))
    operation_id = 'op-' + sha((r['run']['run_id'] + '\0tool.0.1').encode())
    r['executions'].append(dict(tool_call_id=call_id, attempt_id=r['run']['attempt_id'], run_id=r['run']['run_id'],
        operation_id=operation_id, status='unknown', result=dict(state='unknown', value=None), error_code=None,
        evidence=dict(ref='synthetic-receipt/partial-unknown', attempt_id=r['run']['attempt_id'],
                      run_id=r['run']['run_id'], tool_call_id=call_id, operation_id=operation_id, status='unknown')))
    return r


def negative_examples(rows):
    result = []
    def bad(name, original):
        value = deepcopy(original)
        value['sample_id'] = 'bad/' + name
        value['source']['source_id'] = 'F768/bad/' + name
        result.append(value)
        return value
    received = next(r for r in rows if r['scenario'] == 'tool_result')
    failed = next(r for r in rows if r['scenario'] == 'tool_failure')
    bad('unknown-field', rows[0])['invented'] = True
    bad('wrong-tool-id', received)['messages'][2]['tool_call_id'] = 'wrong-call'
    bad('wrong-attempt', received)['executions'][0]['evidence']['attempt_id'] = 'another-attempt'
    bad('wrong-run', received)['executions'][0]['run_id'] = 'another-run'
    bad('wrong-operation', received)['executions'][0]['evidence']['operation_id'] = 'another-operation'
    bad('fake-success', failed)['run']['status'] = 'completed'
    bad('teacher-unchecked', rows[0])['source']['kind'] = 'teacher'
    bad('real-user-default', rows[0])['source']['kind'] = 'real_user'
    bad('tool-schema-drift', rows[0])['versions']['tool_schema_sha256'] = '0' * 64
    bad('bad-arguments', received)['messages'][1]['tool_calls'][0]['function']['arguments'] = '{"keyword":1}'
    bad('unknown-is-empty', failed)['executions'][0]['result'] = dict(state='unknown', value='')
    bad('actual-result-changed', received)['messages'][2]['content'] = '{"results":[]}'
    return result


def main():
    rows = examples()
    (HERE / 'samples.v1.jsonl').write_text(''.join(canonical(r) + '\n' for r in rows))
    negatives = ''.join(canonical(r) + '\n' for r in negative_examples(rows))
    negatives += '{"version":"G2C-dataset.1","version":"duplicate"}\n'
    negatives += '{broken json\n'
    (HERE / 'negative.v1.jsonl').write_text(negatives)


if __name__ == '__main__':
    main()
