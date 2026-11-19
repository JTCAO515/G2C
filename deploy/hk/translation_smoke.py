"""Post-deployment translation checks with original metering evidence."""

import json
import re
from uuid import uuid4

from cj_api.translation import ROUTE, VERSION
from cj_usage.authorization_budget import CNY_SCALE, _price_receipt
from cj_usage.sublimits import scope_hash
from cj_usage.translation_budget import SERVICE, TEXT_MODEL


TRANSLATION_CASES = (('zh', 'en', '你好'), ('en', 'zh', 'Good morning'))
LANGUAGES = tuple(source for source, _, _ in TRANSLATION_CASES)


def matches(source, text, reply):
    if (reply.get('version') != VERSION or reply.get('kind') != 'text'
            or type(reply.get('items')) is not list or len(reply['items']) != 1):
        return False
    row = reply['items'][0]
    if type(row) is not dict or row.get('source_text') != text or type(row.get('translated_text')) is not str:
        return False
    answer = row['translated_text'].strip()
    if source == 'zh':
        return re.fullmatch(r'(?i)(?:hello|hi)[.!?！。\s]*', answer) is not None
    return re.fullmatch(r'(?:早上好|早安|上午好)[！。!?.,，\s]*', answer) is not None


def receipt(budget, scope, request_id):
    ident = f'{SERVICE}:{scope_hash(scope)}:{request_id.hex}:00'
    with budget.connect() as db:
        db.execute('BEGIN')
        budget.require_producer(db)
        row = db.execute('SELECT kind,state,receipt FROM attempt WHERE id=?', (ident,)).fetchone()
    if row is None:
        return None
    kind, state, raw = row
    entry = json.loads(raw)
    if kind != 'model' or entry.get('model_id') != TEXT_MODEL or entry.get('service') != SERVICE:
        return None
    return _price_receipt(kind, raw) if state == 'RECEIVED' else None


def checks(budget, scope, token, allowed, send, emit, error_type, *, ready):
    for source, target, prompt in TRANSLATION_CASES:
        row = dict(kind='translation', language=source, status='UNRUN', reason='earlier_case_stopped')
        if ready and allowed():
            request = uuid4()
            try:
                result, _ = send(token, ROUTE, document={
                    'version': VERSION, 'request_id': str(request), 'kind': 'text',
                    'source_lang': source, 'target_lang': target, 'text': prompt,
                })
                if not matches(source, prompt, result):
                    raise error_type('FAIL', 'translation_result_invalid')
                amount = receipt(budget, scope, request)
                if type(amount) is not int or not 0 < amount <= CNY_SCALE:
                    raise error_type('UNKNOWN', 'translation_receipt_unknown')
                row.update(status='PASS', reason=None, estimated_cny_1e7=amount,
                           conservative_cny_1e7=amount, paid_cny='UNKNOWN')
            except error_type as error:
                row.update(status=error.status, reason=error.reason)
        elif ready:
            row['reason'] = 'window_closed'
        ready = row['status'] == 'PASS'
        emit(row)


def complete(events):
    required = [event for event in events if event['kind'] == 'translation_requirement']
    translations = [event for event in events if event['kind'] == 'translation']
    if len(required) != 1 or type(required[0].get('required')) is not bool:
        return False
    expected = LANGUAGES if required[0]['required'] else ()
    return tuple(row.get('language') for row in translations) == expected
