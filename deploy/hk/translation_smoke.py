"""Post-deployment translation checks with original metering evidence."""

import json
import re
from sqlite3 import Error as SQLiteError
from uuid import uuid4

from cj_api.translation import ROUTE, VERSION
from cj_usage.authorization_budget import CNY_SCALE, LIMITS, _price_receipt
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.sublimits import scope_hash
from cj_usage.translation_budget import SERVICE, TEXT_MODEL


TRANSLATION_CASES = (('zh', 'en', '你好'), ('en', 'zh', 'Good morning'))
LANGUAGES = tuple(source for source, _, _ in TRANSLATION_CASES)
RESERVATION = LIMITS['model'][1] * CNY_SCALE
BATCH_RESERVATION = len(TRANSLATION_CASES) * RESERVATION
METER_FIELDS = ('estimated_cny_1e7', 'conservative_cny_1e7', 'unresolved_attempts')


def matches(source, text, reply, *, structure_only=False):
    if (reply.get('version') != VERSION or reply.get('kind') != 'text'
            or type(reply.get('items')) is not list or len(reply['items']) != 1):
        return False
    row = reply['items'][0]
    if type(row) is not dict or row.get('source_text') != text or type(row.get('translated_text')) is not str:
        return False
    answer = row['translated_text'].strip()
    if structure_only:
        return bool(answer)
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
    if kind != 'model' or state != 'RECEIVED':
        return None
    entry = json.loads(raw)
    if type(entry) is not dict or entry.get('model_id') != TEXT_MODEL or entry.get('service') != SERVICE:
        return None
    return _price_receipt(kind, raw)


def checks(budget, scope, token, allowed, send, emit, error_type, *,
           ready, cases=TRANSLATION_CASES, structure_only=False):
    rows = []
    for source, target, prompt in cases:
        row = dict(kind='translation', language=source, status='UNRUN', reason='earlier_case_stopped',
                   estimated_cny_1e7=0, conservative_cny_1e7=0, unresolved_attempts=0, paid_cny='UNKNOWN')
        if ready and allowed():
            request = uuid4()
            try:
                result, _ = send(token, ROUTE, document={
                    'version': VERSION, 'request_id': str(request), 'kind': 'text',
                    'source_lang': source, 'target_lang': target, 'text': prompt,
                })
                if not matches(source, prompt, result, structure_only=structure_only):
                    raise error_type('FAIL', 'translation_result_invalid')
                row.update(status='PASS', reason=None)
            except error_type as error:
                row.update(status=error.status, reason=error.reason)
            try:
                amount = receipt(budget, scope, request)
            except (ValueError, OSError, SQLiteError, BudgetUnknown):
                amount = None
            if type(amount) is int and 0 < amount <= RESERVATION:
                row.update(estimated_cny_1e7=amount, conservative_cny_1e7=amount)
            else:
                # A lost HTTP response can precede the durable attempt. Keep
                # its full headroom until the original operation is reconciled.
                row.update(conservative_cny_1e7=RESERVATION, unresolved_attempts=1)
                if row['status'] == 'PASS':
                    row.update(status='UNKNOWN', reason='translation_receipt_unknown')
        elif ready:
            row['reason'] = 'window_closed'
        ready = row['status'] == 'PASS'
        emit(row)
        rows.append(row)
    return rows


def complete(events):
    required = [event for event in events if event['kind'] == 'translation_requirement']
    translations = [event for event in events if event['kind'] == 'translation']
    if len(required) != 1 or type(required[0].get('required')) is not bool:
        return False
    expected = LANGUAGES if required[0]['required'] else ()
    return tuple(row.get('language') for row in translations) == expected
