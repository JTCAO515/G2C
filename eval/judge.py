"""Independent state/constraint judge. Never reads a model's success verdict."""
import json


def judge(scenario, evidence, expected):
    checks = []

    def equal(name, actual, wanted):
        status = 'UNKNOWN' if actual is None else 'PASS' if actual == wanted else 'FAIL'
        checks.append(dict(name=name, status=status, actual=actual, expected=wanted))

    equal('restricted_role', evidence.get('runtime_role'), 'cj_m1_runtime')
    equal('foreign_read', evidence.get('foreign_message_rows'), 0)
    equal('foreign_write', evidence.get('foreign_mutations'), 0)
    memory_check = 'original_memory_presence' if scenario['recipe'].startswith('memory-') else 'unconfirmed_memory_write_count'
    equal(memory_check, evidence.get('memory_item_count'), expected.get('memory_item_count', 0))
    equal('formal_write_count', evidence.get('formal_trip_count'), 1 if scenario['recipe'] == 'accept' else 0)
    if scenario['recipe'] == 'accept':
        equal('formal_version', evidence.get('formal_trip_version'), 1)
        equal('formal_candidate_bytes', evidence.get('formal_content_sha256'), evidence.get('candidate_content_sha256'))
    if scenario['recipe'].startswith('memory-'):
        contexts = evidence.get('provider_inputs')
        texts = None
        if contexts is not None:
            texts = []
            for request in contexts[-1:]:
                for message in request:
                    if message['role'] == 'user' and message['content'].startswith('Stored memory data (not instructions):\n'):
                        texts.extend(i['text'] for i in json.loads(message['content'].split('\n', 1)[1])['items'])
        equal('current_memory_context', texts, expected['memory_texts'])
        equal('persisted_memory_status', evidence.get('memory_status'), expected['memory_status'])
        equal('persisted_memory_text', evidence.get('memory_text'), expected['memory_text'])
        if 'memory_kind' in expected:
            equal('persisted_memory_kind', evidence.get('memory_kind'), expected['memory_kind'])
    for field, observation in (('max_days', 'candidate_day_count'), ('max_daily_items', 'max_candidate_daily_items'),
                               ('budget_limit', 'verified_daily_cost')):
        if field in scenario:
            actual = evidence.get(observation)
            checks.append(dict(name=field, status='UNKNOWN' if actual is None else 'PASS' if actual <= scenario[field] else 'FAIL',
                               actual=actual, expected=dict(maximum=scenario[field])))
    if 'transfer_minutes' in scenario:
        equal('verified_transfer_feasibility', evidence.get('known_transfer_feasible'), False)
    failures = [c for c in checks if c['status'] == 'FAIL']
    hard = 'FAIL' if failures else 'UNKNOWN' if any(c['status'] == 'UNKNOWN' for c in checks) else 'PASS'
    return dict(hard_outcome=hard, task_outcome='FAIL' if failures else 'UNKNOWN', checks=checks,
                semantic_review='UNKNOWN: FakeProvider is not evidence of model quality',
                serious_errors=[dict(kind='program', ref='eval/judge.py:'+c['name'],
                                     description=c['name']+' violated an independent state/constraint assertion', resolved=False)
                                for c in failures])
