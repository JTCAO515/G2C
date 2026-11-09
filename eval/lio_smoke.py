"""Single-submit evidence capture for LIO-message.1 and LIO-timeline.1."""
import re
import time

from demo_v2_evidence import _object
from demo_v2_transport import _journal, _small_read, _sync_directory, _write


CHAT = re.compile(r'lio-dialogue-[0-9a-f]{32}')
SEND = '/v1/lio/messages'
TIMELINE = '/v1/lio/timeline'
TERMINAL = frozenset({'completed', 'failed'})


def _conversation(value):
    if type(value) is not str or CHAT.fullmatch(value) is None:
        raise ValueError('Lio conversation identity required')
    return value


def _request(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 16_384:
        raise ValueError('bounded original Lio input required')
    value = _object(raw)
    fields = {'version', 'message_id', 'text', 'locale'}
    if (set(value) not in (fields, fields | {'conversation_id'})
            or value['version'] != 'LIO-message.1' or value['locale'] not in ('zh', 'en')):
        raise ValueError('Lio message version and exact fields required')
    message_id, text = value['message_id'], value['text']
    if (type(message_id) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,128}', message_id) is None
            or type(text) is not str or not text.strip() or '\0' in text or len(text.encode()) > 12_000):
        raise ValueError('bounded synthetic Lio message required')
    if 'conversation_id' in value:
        _conversation(value['conversation_id'])
    return value


def _ack(raw, original):
    value = _object(raw)
    if (set(value) != {'version', 'message_id', 'conversation_id'}
            or value['version'] != 'LIO-message-receipt.1'
            or value['message_id'] != original['message_id']):
        raise ValueError('original Lio receipt required')
    conversation = _conversation(value['conversation_id'])
    if original.get('conversation_id', conversation) != conversation:
        raise ValueError('original Lio conversation changed')
    return conversation


def _observation(raw, original, conversation):
    value = _object(raw)
    if (set(value) != {'version', 'conversation_id', 'messages', 'next_before'}
            or value['version'] != 'LIO-timeline.1'
            or not isinstance(value['messages'], list) or len(value['messages']) > 20):
        raise ValueError('Lio timeline version and page required')
    if value['conversation_id'] is None and value['messages'] == [] and conversation is None:
        return None, None
    found_conversation = _conversation(value['conversation_id'])
    if conversation is not None and found_conversation != conversation:
        raise ValueError('timeline changed the original conversation')
    if any(type(row) is not dict or 'message_id' not in row for row in value['messages']):
        raise ValueError('Lio timeline contains a malformed message')
    matches = [row for row in value['messages'] if row['message_id'] == original['message_id']]
    if not matches:
        return found_conversation, None
    if len(matches) != 1:
        raise ValueError('timeline repeated the original message')
    item = matches[0]
    if (set(item) != {'message_id', 'text', 'answer', 'status', 'failure', 'sources', 'trip', 'memory'}
            or item['text'] != original['text'] or not isinstance(item['answer'], str)
            or item['status'] not in ('sending', 'answering', 'completed', 'failed')
            or not isinstance(item['sources'], list)):
        raise ValueError('timeline changed or malformed the original message')
    return found_conversation, item


def capture(client, raw, directory, *, clock=time.perf_counter, delay=time.sleep,
            max_reads=160, max_seconds=140):
    """Keep POST and each poll; observe the original without sending it again."""
    original = _request(raw)
    if directory.name != original['message_id']:
        raise ValueError('attempt directory must be named for the original ID')
    directory.mkdir(mode=0o700)
    _write(directory / 'intent.utf8', raw)
    _sync_directory(directory)
    _sync_directory(directory.parent)
    started = clock()
    status, response = _small_read(client, 'POST', SEND, directory, 'submit', content=raw,
                                   headers={'Content-Type': 'application/octet-stream'})
    conversation = original.get('conversation_id')
    submit = 'UNKNOWN'
    if status == 200:
        try:
            conversation = _ack(response, original)
        except ValueError:
            pass  # Preserve the response and continue by reading only.
        else:
            submit = 'ACK'
    elif status in (400, 401, 403, 409, 429):
        try:
            failure = _object(response).get('failure')
        except ValueError:
            pass
        else:
            if failure in ('quota', 'unavailable'):
                submit = 'REJECTED'

    progress = first_body = complete = None
    item = None
    if submit != 'REJECTED':
        for index in range(1, max_reads + 1):
            remaining = max_seconds - (clock() - started)
            if remaining <= 0:
                break
            params = {} if conversation is None else {'conversation_id': conversation}
            label = f'timeline-{index:03}'
            code, page = _small_read(client, 'GET', TIMELINE, directory, label,
                                     max_bytes=4_500_000, params=params, timeout=remaining)
            elapsed = clock() - started
            _journal(directory / (label + '.clock'), {'elapsed_seconds': elapsed})
            if code == 200:
                conversation, message = _observation(page, original, conversation)
                if message is not None:
                    item = message
                    if item['status'] == 'answering' and progress is None:
                        progress = elapsed
                    if item['answer'] and first_body is None:
                        first_body = elapsed
                    if item['status'] in TERMINAL:
                        if item['status'] == 'completed' and item['answer'].strip():
                            complete = elapsed
                        break
            elif code not in (None, 503):
                break
            delay(min(.4, max(0, max_seconds - elapsed)))

    summary = dict(message_id=original['message_id'], conversation_id=conversation,
                   submission=submit, message=item, first_server_progress_seconds=progress,
                   first_body_seconds=first_body, complete_seconds=complete)
    _journal(directory / 'summary.json', summary)
    return summary
