"""B-operated, same-owner Hong Kong deployment smoke over the app's HTTP API."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from http.client import IncompleteRead
import json
import os
import re
import socket
from sqlite3 import Error as SQLiteError
import sys
from tempfile import TemporaryDirectory
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid
from zoneinfo import ZoneInfo

from cj_message.lio_context import CAPABILITIES_EN, CAPABILITIES_ZH
from cj_strict_json import reject_duplicates
from cj_usage.authorization_budget import CNY_SCALE
from cj_usage.metered_exit import BudgetUnknown
from psycopg import Error as PostgresError

ORIGIN = 'https://api-beta.go2china.space'
SHANGHAI = ZoneInfo('Asia/Shanghai')
CASE_LIMIT_SECONDS = 90
POLL_SECONDS = 1
HTTP_SECONDS = 5
HISTORY_PAGE_SIZE = 20
MAX_HISTORY_PAGES = 40
CASES = (
    ('zh.identity', '你是谁'),
    ('zh.capability', '你能做啥'),
    ('zh.plan', '北京三日游'),
    ('en.identity', 'Who are you?'),
    ('en.capability', 'What can you do?'),
    ('en.plan', 'A three-day trip to Beijing'),
)
DAY_HEADER = re.compile(
    r'(?im)^\s*(?:[#>*_\-]+\s*)*(?:(?:Day|D)\s*([123])\b|第\s*([一二三123])\s*[天日])'
)
DAY_NUMBER = {'一': 1, '二': 2, '三': 3, '1': 1, '2': 2, '3': 3}
BEIJING_PLACE = re.compile(
    r'故宫|天安门|景山|长城|八达岭|慕田峪|颐和园|天坛|雍和宫|什刹海|南锣鼓巷|胡同|'
    r'北海公园|国家博物馆|圆明园|国子监|恭王府|前门|王府井|三里屯|奥林匹克|'
    r'Forbidden City|Palace Museum|Tiananmen|Jingshan|Great Wall|Badaling|Mutianyu|'
    r'Summer Palace|Temple of Heaven|Lama Temple|Shichahai|Nanluoguxiang|hutongs?|'
    r'Beihai|National Museum|Old Summer Palace|Imperial College|Prince Gong|'
    r'Qianmen|Wangfujing|Sanlitun|Olympic|798 Art', re.I
)
NEGATED_IDENTITY = re.compile(r'不是\s*Lio|\bnot\s+Lio\b', re.I)
DAY_ACTIVITY = re.compile(
    r'^(?:可以?|建议)?(?:去|参观|游览|游玩|游逛|乘车|坐车|坐地铁|步行|登上|爬山|漫步|'
    r'散步|逛|前往|抵达|体验|品尝|欣赏|走访)|'
    r'^(?:(?:you can|you will|you could|you should)\s+)?'
    r'(?:visit|walk|hike|tour|take|climb|ride|explore|stroll|see|browse|stop|spend|start|head|admire)\b', re.I
)
SCHEDULE_PREFIX = re.compile(
    r'^\s*(?:[#>*_·•:\-–—：]+\s*)*'
    r'(?:(?:早上|清晨|上午|中午|下午|傍晚|晚上|'
    r'(?:in the |this )?(?:morning|afternoon|evening)|after (?:breakfast|lunch|dinner))'
    r'[\s：:，,*_–—-]*)?', re.I
)
NO_DAY_ACTIVITY = re.compile(
    r'没有(?:任何)?安排|并未安排|不安排|未安排|取消|暂无|不建议|不要|不去|不参观|不游览|'
    r'无法|不能|不可|不可能|未能|没法|禁止|闭馆|'
    r"\b(?:no (?:activity|activities|plans?)|nothing (?:is )?planned|not (?:planned|scheduled|possible)|"
    r"(?:do|should|can|will) not|(?:don|shouldn|won|can)[’']t|unable|impossible|avoid|skip)\b", re.I
)
DAY_QUESTION = re.compile(
    r'[?？]|(?:吗|么|呢)\s*[。.]?\s*$|你(?:想|要不要)|是否|'
    r'\b(?:would you like|do you want|want to know|are you planning)\b', re.I
)
WIRE_TIMING = re.compile(
    r'\bM4_MODEL_WIRE_TIMING attempt_sha256=([a-f0-9]{64}) '
    r'first_provider_body_ms=([0-9]+(?:\.[0-9]+)?) socket_read_ms=[0-9]+(?:\.[0-9]+)?\b'
)


class SmokeResult(Exception):
    def __init__(self, status, reason):
        self.status = status
        self.reason = reason


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(token, route, *, document=None):
    opener = build_opener(NoRedirect())
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json'}
    data = None
    if document is not None:
        headers['Content-Type'] = 'application/octet-stream'
        data = json.dumps(document, ensure_ascii=False).encode()
    try:
        with opener.open(Request(ORIGIN + route, data=data, headers=headers), timeout=HTTP_SECONDS) as response:
            if response.status != 200:
                raise SmokeResult('FAIL', f'http_{response.status}')
            raw = response.read(4_500_001)
            ref = response.headers.get('X-Request-ID')
    except HTTPError as error:
        code = error.code
        error.close()
        raise SmokeResult('FAIL', f'http_{code}') from None
    except (TimeoutError, socket.timeout):
        raise SmokeResult('FAIL' if document is None else 'UNKNOWN', 'http_timeout') from None
    except IncompleteRead:
        raise SmokeResult('FAIL' if document is None else 'UNKNOWN', 'http_incomplete_body') from None
    except URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise SmokeResult('FAIL' if document is None else 'UNKNOWN', 'http_timeout') from None
        raise SmokeResult('UNKNOWN', 'transport_unavailable') from None
    except OSError:
        raise SmokeResult('UNKNOWN', 'transport_unavailable') from None
    try:
        if len(raw) > 4_500_000:
            raise ValueError('response bound')
        value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate response field'))
        if not isinstance(value, dict):
            raise ValueError('response object')
    except (ValueError, UnicodeError):
        raise SmokeResult('FAIL', 'invalid_api_response') from None
    return value, ref if ref and re.fullmatch(r'[a-fA-F0-9-]{36}', ref) else None


def _normalize_capability_copy(value):
    value = re.sub(r'(?m)^[ \t]*(?:>[ \t]*|#{1,6}[ \t]+|[-+*][ \t]+|\d+[.)][ \t]+)+', '', value)
    value = value.translate(str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"'}))
    value = value.translate(str.maketrans('', '', '*_`~'))
    return ' '.join(value.casefold().split())


def valid_answer(case, answer):
    if not isinstance(answer, str) or not answer.strip():
        return False
    locale, kind = case.split('.')
    if locale == 'zh' and len(re.findall(r'[\u3400-\u9fff]', answer)) < 8:
        return False
    if locale == 'en' and len(re.findall(r'\b[a-zA-Z]{2,}\b', answer)) < 6:
        return False
    if kind == 'identity':
        return bool(re.search(r'\bLio\b|旅行助手|旅游助手', answer, re.I)
                    and re.search(r'我是|旅行|旅游|助手|\bI(?:\s+am|[’\']m)\b|travel|assistant', answer, re.I)
                    and not NEGATED_IDENTITY.search(answer))
    if kind == 'capability':
        approved = CAPABILITIES_ZH if locale == 'zh' else CAPABILITIES_EN
        return _normalize_capability_copy(answer) == _normalize_capability_copy(approved)
    headings = list(DAY_HEADER.finditer(answer))
    if [DAY_NUMBER[match.group(1) or match.group(2)] for match in headings] != [1, 2, 3]:
        return False
    for index, match in enumerate(headings):
        day = answer[match.end():headings[index+1].start() if index < 2 else len(answer)]
        activities = re.split(r'(?<=[。！？.!?])|\n', day)
        if not any(BEIJING_PLACE.search(clause) and DAY_ACTIVITY.match(SCHEDULE_PREFIX.sub('', clause, count=1))
                   and not NO_DAY_ACTIVITY.search(clause) and not DAY_QUESTION.search(clause)
                   for clause in activities):
            return False
    return True


def find_message(value, message_id, expected_conversation):
    if (value.get('version') != 'LIO-timeline.2' or not isinstance(value.get('messages'), list)
            or expected_conversation is not None and value.get('conversation_id') != expected_conversation):
        raise SmokeResult('FAIL', 'timeline_binding')
    if any(not isinstance(item, dict) for item in value['messages']):
        raise SmokeResult('FAIL', 'timeline_message_shape')
    rows = [item for item in value['messages'] if item.get('message_id') == message_id]
    if len(rows) > 1:
        raise SmokeResult('FAIL', 'duplicate_original_message')
    return rows[0] if rows else None


def permitted(now, start, end, *, minimum_seconds=0):
    local = now.astimezone(SHANGHAI)
    return (start <= now < end and (end - now).total_seconds() >= minimum_seconds
            and 8 <= local.hour < 23)


def run_case(case, prompt, token, allowed, send=request):
    message_id = str(uuid.uuid4())
    payload = dict(version='LIO-message.2', message_id=message_id, text=prompt,
                   locale=case[:2], new_conversation=True)
    started = time.monotonic()
    result = dict(case=case, status='UNRUN', polls=[], message_id=message_id)
    clock_ms = lambda: round((time.monotonic()-started)*1000, 3)

    def submit():
        # Record this lower boundary immediately before the single POST.
        result['dispatch_ms'] = clock_ms()
        return send(token, '/v2/lio/messages', document=payload)

    with ThreadPoolExecutor(max_workers=1) as queue:
        try:
            if not allowed():
                raise SmokeResult('UNRUN', 'window_or_budget_closed')
            result['status'] = 'UNKNOWN'
            # The first read is strictly before the first write. An unreadable old
            # timeline cannot become a successful concurrency baseline.
            parsed, _ = send(token, '/v2/lio/timeline')
            find_message(parsed, message_id, None)
            default_conversation = parsed.get('conversation_id')
            if not allowed():
                raise SmokeResult('UNRUN', 'window_or_budget_closed')
            pending = queue.submit(submit)
            conversation = None
            next_poll = time.monotonic()
            while time.monotonic() < started + CASE_LIMIT_SECONDS:
                if not allowed():
                    raise SmokeResult('UNKNOWN', 'window_or_budget_closed_after_post')
                if conversation is None and pending.done():
                    try:
                        ack, ref = pending.result()
                    except SmokeResult as error:
                        if error.reason.startswith('http_5'):
                            raise SmokeResult('UNKNOWN', 'message_write_outcome') from None
                        raise
                    conversation = ack.get('conversation_id')
                    if (ack.get('version') != 'LIO-message-receipt.2' or ack.get('message_id') != message_id
                            or not isinstance(conversation, str) or not conversation):
                        raise SmokeResult('UNKNOWN', 'unbound_message_ack')
                    result.update(conversation_id=conversation, message_ref=ref)
                    if conversation == default_conversation:
                        raise SmokeResult('UNKNOWN', 'reused_default_conversation')
                route = '/v2/lio/timeline'
                if conversation is not None:
                    route += '?' + urlencode({'conversation_id': conversation})
                began = clock_ms()
                try:
                    value, ref = send(token, route)
                except SmokeResult as error:
                    result['polls'].append(dict(start_ms=began, end_ms=clock_ms(), outcome=error.reason))
                    raise
                row = find_message(value, message_id, conversation)
                sample = dict(start_ms=began, end_ms=clock_ms(), http=200, ref=ref,
                              answering=bool(row and row.get('status')=='answering' and not row.get('answer')))
                result['polls'].append(sample)
                if row is not None and row.get('status') == 'failed':
                    raise SmokeResult('FAIL' if row.get('failure') == 'quota' else 'UNKNOWN', 'original_run_' +
                                      ('quota' if row.get('failure') == 'quota' else 'unavailable'))
                if conversation is not None and row is not None and row.get('status') == 'completed':
                    answer = row.get('answer')
                    if not valid_answer(case, answer):
                        raise SmokeResult('FAIL', 'required_answer_missing')
                    result.update(status='PASS', answer_chars=len(answer),
                                  answer_sha256=hashlib.sha256(answer.encode()).hexdigest())
                    break
                next_poll += POLL_SECONDS
                time.sleep(max(0, next_poll - time.monotonic()))
            else:
                raise SmokeResult('UNKNOWN', 'original_run_deadline')
        except SmokeResult as error:
            result.update(status=error.status, reason=error.reason)
    result['elapsed_ms'] = clock_ms()
    return result


def overlap_witness(result, attempt_hashes, wire_log_lines):
    """Prove at least one full 200 read happened inside original model I/O.

    Read samples cover POST through first visible answer. Before publication,
    The bound answer's send-to-first-body duration must exceed the longest
    interval that can avoid containing a complete 200 read. The original
    answer is sent after POST and its first byte precedes its terminal answer,
    so its contiguous pre-body interval is fully inside the observed timeline.
    """
    if result['status'] != 'PASS':
        return False
    polls = result['polls']
    if not polls or any(row.get('http') != 200 for row in polls):
        return False
    answering = [row for row in polls if row['answering']]
    if not answering or not attempt_hashes:
        return False
    start, end = result['dispatch_ms'], polls[-1]['end_ms']
    usable = [row for row in answering if row['start_ms'] >= start]
    if not usable:
        return False
    gaps = [usable[0]['end_ms']-start, end-usable[-1]['start_ms']]
    gaps.extend(later['end_ms']-earlier['start_ms'] for earlier,later in zip(usable,usable[1:]))
    minimum = max(gaps)
    matching = [m for line in wire_log_lines if (m := WIRE_TIMING.search(line))
                and m[1] in attempt_hashes]
    return (len({m[1] for m in matching}) == len(matching)
            and any(minimum < float(m[2]) <= end-start for m in matching))


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, separators=(',', ':')), flush=True)


def history(token, cases, allowed):
    started = time.monotonic()
    try:
        by_conversation = {}
        for case in cases:
            by_conversation.setdefault(case['conversation_id'], set()).add(case['message_id'])
        for conversation, expected in by_conversation.items():
            found = set()
            cursors = set()
            query = {'conversation_id': conversation, 'limit': HISTORY_PAGE_SIZE}
            for _ in range(MAX_HISTORY_PAGES):
                if not allowed():
                    raise SmokeResult('UNRUN', 'window_closed')
                value, _ = request(token, '/v5/message-history?' + urlencode(query))
                rows = value.get('messages')
                if (value.get('version') != 'MESSAGE-history.5' or type(rows) is not list
                        or any(type(row) is not dict or type(row.get('receipt')) is not dict for row in rows)):
                    raise SmokeResult('FAIL', 'invalid_history')
                if any(row['receipt'].get('conversation_id') != conversation for row in rows):
                    raise SmokeResult('FAIL', 'history_conversation_binding')
                found.update(row['receipt'].get('message_id') for row in rows)
                if expected <= found:
                    break
                cursor = value.get('next_cursor')
                if cursor is None:
                    raise SmokeResult('FAIL', 'original_message_missing_from_history')
                if type(cursor) is not str or not cursor or cursor in cursors:
                    raise SmokeResult('FAIL', 'history_cursor_invalid')
                cursors.add(cursor)
                query['cursor'] = cursor
            else:
                raise SmokeResult('UNKNOWN', 'history_page_bound')
        return dict(status='PASS', elapsed_ms=round((time.monotonic()-started)*1000, 3))
    except SmokeResult as error:
        return dict(status=error.status, reason=error.reason,
                    elapsed_ms=round((time.monotonic()-started)*1000, 3))


def original_model_attempts(database, scope, message_id):
    with database.connect(scope) as db:
        db.execute('SET TRANSACTION READ ONLY')
        attempts = db.execute(
            "SELECT o.attempt_id FROM cj_message_delivery d "
            "JOIN cj_run_metered_operation o ON (o.scope,o.run_id)=(d.scope,d.run_id) "
            "WHERE d.scope=%s AND d.message_id=%s AND o.kind='model' "
            "AND ((o.registration_id='model.answer' AND o.operation_key='model.lio_discussion.0') "
            "OR (o.registration_id='model.tool_turn' AND o.operation_key ~ '^model[.]tool_turn[.][0-9]+$') "
            "OR (o.registration_id='model.draft' AND o.operation_key='model.draft'))",
            (scope, message_id),
        ).fetchall()
    return {hashlib.sha256(row[0].encode()).hexdigest() for row in attempts}


def run(budget, database, scope, token, owner, start, end):
    from deploy.hk.server_smoke_budget import budget_state, restrict, settlement

    def allowed():
        return permitted(datetime.now(timezone.utc), start, end)

    if not permitted(datetime.now(timezone.utc), start, end, minimum_seconds=CASE_LIMIT_SECONDS):
        print_json(dict(kind='batch', status='UNRUN', reason='approved_window_closed'))
        return 3
    from deploy.hk.configuration import TRANSLATION_INTERNAL_SUBJECTS
    from deploy.hk.translation_relay import translation_state
    try:
        translation_required = translation_state()
        if translation_required != (TRANSLATION_INTERNAL_SUBJECTS in os.environ):
            raise ValueError('translation worker differs from expected configuration')
    except (OSError, ValueError):
        print_json(dict(kind='batch', status='UNKNOWN', reason='translation_worker_state_unavailable'))
        return 2
    print_json(dict(kind='translation_requirement', required=translation_required))
    before = budget_state(budget, owner)
    print_json(dict(kind='restriction_intent', before=before))
    restricted = restrict(budget, before)
    print_json(dict(kind='restricted', before=before, restricted=restricted))

    results = []
    tail = before['tail']
    for case, prompt in CASES:
        if results and results[-1]['status'] != 'PASS':
            result = dict(case=case, status='UNRUN', reason='earlier_case_stopped')
        elif not permitted(datetime.now(timezone.utc), start, end, minimum_seconds=CASE_LIMIT_SECONDS):
            result = dict(case=case, status='UNRUN', reason='approved_window_too_short')
        else:
            result = run_case(case, prompt, token, allowed)
            try:
                tail, price, used = settlement(budget, owner, restricted, tail)
                result['cost'] = price
                if result['status'] == 'PASS':
                    bound = original_model_attempts(database, scope, result['message_id'])
                    result['bound_model_attempts'] = sorted(bound.intersection(price['model_attempts']))
                    if used-before['used'] > 5*CNY_SCALE:
                        raise ValueError('original C cash bound exceeded')
            except (ValueError, SQLiteError, PostgresError, BudgetUnknown):
                result['accounting'] = 'UNKNOWN'
                if result['status'] == 'PASS':
                    result.update(status='UNKNOWN', reason='original_cost_boundary_unconfirmed')
        results.append(result)
        print_json(dict(kind='case', **result))

    history_result = (history(token, results, allowed) if all(row['status']=='PASS' for row in results)
                      else dict(status='UNRUN', reason='earlier_case_stopped'))
    print_json(dict(kind='history', **history_result))
    if translation_required:
        from deploy.hk.translation_smoke import checks
        checks(budget, scope, token, allowed, request, print_json, SmokeResult,
               ready=history_result['status']=='PASS')
    _, price, used = settlement(budget, owner, restricted, before['tail'])
    print_json(dict(kind='cost', **price, line_usage_delta_cny_1e7=used-before['used']))
    return 0


def decide(events, wire_logs):
    cases = [entry for entry in events if entry['kind']=='case']
    history_rows = [entry for entry in events if entry['kind']=='history']
    costs = [entry for entry in events if entry['kind']=='cost']
    outcomes = cases + history_rows + [row for row in events if row['kind']=='translation']
    if any(row['status']=='FAIL' for row in outcomes):
        failed_read = any(row['status']=='FAIL' and 'dispatch_ms' in row
                          and any('outcome' in poll for poll in row.get('polls', ())) for row in cases)
        return dict(status='FAIL', concurrency='FAIL' if failed_read else 'UNRUN')
    if any(row['status']=='UNKNOWN' for row in outcomes):
        unknown_read = any(row['status']=='UNKNOWN' and 'dispatch_ms' in row
                           and any('outcome' in poll for poll in row.get('polls', ())) for row in cases)
        return dict(status='UNKNOWN', concurrency='UNKNOWN' if unknown_read else 'UNRUN')
    if not cases and any(row['kind']=='batch' and row['status']=='UNRUN' for row in events):
        return dict(status='UNRUN', concurrency='UNRUN')
    if [row['case'] for row in cases] != [name for name, _ in CASES] or len(history_rows)!=1 or len(costs)!=1:
        return dict(status='UNKNOWN', concurrency='UNKNOWN')
    if any(row['status'] not in {'PASS','UNRUN'} for row in outcomes):
        return dict(status='UNKNOWN', concurrency='UNKNOWN', reason='invalid_smoke_status')
    if any(row['status']=='UNRUN' for row in outcomes):
        return dict(status='UNRUN', concurrency='UNRUN')
    from deploy.hk.translation_smoke import complete
    if not complete(events):
        return dict(status='UNKNOWN', concurrency='UNRUN', reason='translation_smoke_incomplete')
    if (costs[0]['conservative_cny_1e7'] > 5*CNY_SCALE
            or costs[0]['line_usage_delta_cny_1e7'] > 5*CNY_SCALE):
        return dict(status='UNKNOWN', concurrency='UNRUN', reason='smoke_cost_boundary_unconfirmed')
    concurrent = any(overlap_witness(row, set(row['bound_model_attempts']), wire_logs) for row in cases)
    return dict(status='PASS' if concurrent else 'UNKNOWN', concurrency='PASS' if concurrent else 'UNKNOWN')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'run', 'restore', 'verify'))
    args = parser.parse_args()
    raw = sys.stdin.buffer.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('bounded smoke input required')
    envelope = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate smoke input'))
    if args.action == 'verify':
        result = decide(envelope['events'], envelope['wire_logs'])
        print_json(result)
        return {'PASS': 0, 'FAIL': 1, 'UNKNOWN': 2, 'UNRUN': 3}[result['status']]

    from cj_api.local_app import scope_for
    from cj_api.local_worker_context import checker_for
    from cj_auth.interfaces import AdmissionStatus
    from cj_usage.authorization_budget import AuthorizationBudget, HK_JOURNAL_ROOT
    from cj_usage.sublimits import scope_hash
    from deploy.hk.configuration import Runtime, authorization, load_secret_environment
    from deploy.hk.server_smoke_budget import budget_state, restore

    load_secret_environment('worker')
    authorization()
    if args.action == 'restore':
        budget = AuthorizationBudget(HK_JOURNAL_ROOT, authorization_guard=authorization, demo=True)
        restore(budget, envelope['before'], envelope['restricted'], envelope['drained_ledger'])
        print_json(dict(kind='budget_restore', status='PASS'))
        return 0

    token = envelope['access_token']
    start, end = (datetime.fromisoformat(envelope[field]) for field in ('starts_at', 'ends_at'))
    if (start.tzinfo is None or end.tzinfo is None
            or not 0 < (end-start).total_seconds() <= 1800):
        raise ValueError('bounded deployment smoke window required')
    with TemporaryDirectory(prefix='hk-server-smoke-') as directory:
        runtime = Runtime.load(directory, worker=True)
        try:
            decision = checker_for(runtime.auth, selected_subjects=runtime.demo_subjects).check(token)
            if decision.status is AdmissionStatus.DENIED:
                print_json(dict(kind='batch', status='UNRUN', reason='synthetic_session_denied'))
                return 3
            if decision.principal is None:
                raise ValueError('invited synthetic session required')
            if decision.principal.expires_at < end.timestamp():
                print_json(dict(kind='batch', status='UNRUN', reason='synthetic_session_window_too_short'))
                return 3
            scope = scope_for(decision.principal.issuer, decision.principal.subject)
            owner = scope_hash(scope)
            budget = AuthorizationBudget(HK_JOURNAL_ROOT, authorization_guard=authorization, demo=True)
            if args.action == 'preflight':
                state = budget_state(budget, owner)
                from deploy.hk.app_smoke_ceiling import BASELINE
                from cj_usage.sublimits import policy
                if state['policy'] != policy(BASELINE) or state['used']+CNY_SCALE > BASELINE['cap']:
                    raise ValueError('C standing budget qualification failed')
                print_json(dict(kind='preflight', status='PASS', provider_calls=0))
                return 0
            return run(budget, runtime.database(), scope, token, owner, start, end)
        finally:
            runtime.close()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, TypeError, SQLiteError, PostgresError, BudgetUnknown):
        # Any partial operation must be reconciled from its original intent.
        # Never put a private input, token, body or exception text in output.
        print_json(dict(kind='execution_error', status='UNKNOWN', reason='original_smoke_state_unavailable'))
        raise SystemExit(2) from None
