"""Correlate Demo v2 transport evidence before independent scene assessment."""
from hashlib import sha256
import json
import math
import re

from cj_strict_json import reject_duplicates


ORIGINAL_KEYS = ('message_id', 'conversation_id', 'run_id')
MESSAGE_VERSIONS = ('DEMO-dialogue-message.1', 'DEMO-dialogue-message.2')
CARD_KINDS = {'needs_card', 'trip_candidate', 'edit_candidate', 'memory_candidate'}
PROGRESS_STAGES = {'queued', 'running', 'tool'}
TERMINAL_STAGES = {'completed', 'failed', 'cancelled', 'context_invalid', 'unknown'}
SOURCE_LINE = re.compile(r'(?:Source:|来源：)\s*(?:https?://\S+)?')
MAX_EVENT_BYTES = 1_048_576
MAX_CAPTURE_BYTES = 4_194_304


def _object(raw):
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=reject_duplicates(ValueError, 'duplicate wire field'))
    if not isinstance(value, dict):
        raise ValueError('expected wire object')
    return value


def original_receipt(submission, response):
    """Verify the exact POST or its protected GET readback. A null stays unknown."""
    if len(submission) > 16_384 or len(response) > 65_536:
        raise ValueError('message evidence exceeds bound')
    request, envelope = _object(submission), _object(response)
    if (request.get('version') not in MESSAGE_VERSIONS or
            envelope.get('version') != 'DEMO-dialogue-receipt.1' or
            not isinstance(envelope.get('request_id'), str) or not envelope['request_id'] or
            'receipt' not in envelope):
        raise ValueError('original dialogue receipt required')
    receipt = envelope['receipt']
    if receipt is None:
        return None
    if (not isinstance(receipt, dict) or
            any(not isinstance(receipt.get(key), str) or not receipt[key] for key in ORIGINAL_KEYS) or
            receipt['message_id'] != request.get('message_id') or
            ('conversation_id' in request and receipt['conversation_id'] != request['conversation_id']) or
            receipt.get('input_sha256') != sha256(submission).hexdigest()):
        raise ValueError('dialogue receipt differs from original submission')
    return receipt


def original_action_receipt(submission, response):
    """Bind an action receipt without treating its queued RUN as completed."""
    if len(submission) > 32_768 or len(response) > 65_536:
        raise ValueError('action evidence exceeds bound')
    request, envelope = _object(submission), _object(response)
    if (request.get('version') != 'DEMO-dialogue-action.1' or
            envelope.get('version') != 'DEMO-dialogue-action-receipt.1' or
            not isinstance(envelope.get('request_id'), str) or not envelope['request_id'] or
            'receipt' not in envelope):
        raise ValueError('original dialogue action receipt required')
    receipt = envelope['receipt']
    if receipt is None:
        return None
    identity = ('action_id', 'conversation_id', 'card_id', 'operation')
    if (not isinstance(receipt, dict) or
            any(not isinstance(receipt.get(key), str) or not receipt[key] or
                receipt[key] != request.get(key) for key in identity) or
            receipt.get('input_sha256') != sha256(submission).hexdigest()):
        raise ValueError('dialogue action receipt differs from original submission')
    child = (receipt.get('message_id'), receipt.get('run_id'))
    if child != (None, None) and not all(isinstance(value, str) and value for value in child):
        raise ValueError('queued action RUN needs its original MESSAGE')
    return receipt


class DialogueObservation:
    """Capture one RUN across read-only SSE reconnects without grading the scene."""

    def __init__(self, receipt):
        self.original = {key: receipt[key] for key in ORIGINAL_KEYS}
        self.events = []
        self.last_event_id = None
        self._seen = {}
        self._bytes = 0
        self._answer = []
        self._last_answer_seconds = None
        self.first_progress_seconds = None
        self.first_run_progress_seconds = None
        self.first_body_seconds = None
        self.terminal = None

    def record(self, event_id, raw, elapsed_seconds, *, event_name=None):
        if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_EVENT_BYTES:
            raise ValueError('bounded original dialogue event required')
        event = _object(raw)
        if (event.get('version') != 'DEMO-dialogue-event.1' or
                any(event.get(key) != value for key, value in self.original.items()) or
                not isinstance(event_id, str) or re.fullmatch(r'[1-9][0-9]{0,11}', event_id) is None or
                event.get('event_id') != event_id):
            raise ValueError('dialogue event belongs to another original')
        kind, payload = event.get('kind'), event.get('payload')
        if not isinstance(kind, str) or not isinstance(payload, dict):
            raise ValueError('dialogue event payload required')
        if event_name is not None and kind != event_name:
            raise ValueError('SSE event name differs from original kind')
        digest = sha256(raw).hexdigest()
        if event_id in self._seen:
            if self._seen[event_id] != digest:
                raise ValueError('original dialogue event changed after resume')
            return False
        if self.last_event_id is not None and int(event_id) <= int(self.last_event_id):
            raise ValueError('unseen dialogue event behind the resume cursor')
        if (type(elapsed_seconds) not in (int, float) or not math.isfinite(elapsed_seconds) or
                elapsed_seconds < 0 or (self.events and elapsed_seconds < self.events[-1]['seconds'])):
            raise ValueError('original client clock must be monotonic')
        if self._bytes + len(raw) > MAX_CAPTURE_BYTES:
            raise ValueError('original dialogue capture exceeds bound')
        if kind == 'status':
            stage = payload.get('stage')
            if not isinstance(stage, str) or stage not in PROGRESS_STAGES | TERMINAL_STAGES:
                raise ValueError('unknown dialogue status stage')
            if self.terminal is not None and stage != self.terminal['stage']:
                raise ValueError('original terminal status changed')
            if stage in PROGRESS_STAGES and self.first_progress_seconds is None:
                self.first_progress_seconds = elapsed_seconds
            if stage in ('running', 'tool') and self.first_run_progress_seconds is None:
                self.first_run_progress_seconds = elapsed_seconds
            if stage in TERMINAL_STAGES and self.terminal is None:
                self.terminal = {'stage': stage, 'seconds': elapsed_seconds}
        elif kind == 'answer_delta':
            text = payload.get('text')
            if not isinstance(text, str):
                raise ValueError('dialogue answer delta must be text')
            text.encode('utf-8')
            if self.first_body_seconds is None and any(line.strip() and not SOURCE_LINE.fullmatch(line.strip())
                                                       for line in text.splitlines()):
                self.first_body_seconds = elapsed_seconds
            if text:
                self._answer.append(text)
                self._last_answer_seconds = elapsed_seconds
        elif kind == 'source':
            if payload.get('state') == 'unknown' and payload.get('url') is not None:
                raise ValueError('unknown dialogue source cannot have a URL')
        elif kind in CARD_KINDS:
            if (not isinstance(payload.get('card_id'), str) or not payload['card_id'] or
                    type(payload.get('version')) is not int or payload['version'] < 1):
                raise ValueError('original dialogue card ID and version required')
        else:
            raise ValueError('unknown dialogue event kind')
        self._seen[event_id] = digest
        self._bytes += len(raw)
        self.last_event_id = event_id
        self.events.append({'event': event, 'original_utf8': raw.decode('utf-8'),
                            'seconds': elapsed_seconds, 'payload_sha256': digest})
        return True

    def read_segment(self, lines, elapsed, *, append=None):
        """Consume the three-field B SSE frames; return an unfinished frame at EOF."""
        fields = {}
        for line in lines:
            if not isinstance(line, bytes) or len(line) > MAX_EVENT_BYTES + 8:
                raise ValueError('bounded SSE line bytes required')
            line = line.rstrip(b'\r\n')
            if not line:
                if fields:
                    if set(fields) != {b'id', b'event', b'data'}:
                        raise ValueError('incomplete dialogue SSE frame')
                    accepted = self.record(fields[b'id'].decode('ascii'), fields[b'data'], elapsed(),
                                           event_name=fields[b'event'].decode('ascii'))
                    if accepted and append is not None:
                        append(self.events[-1])
                    fields.clear()
                continue
            if line.startswith(b':'):
                continue
            name, separator, value = line.partition(b':')
            if not separator or name not in (b'id', b'event', b'data') or name in fields:
                raise ValueError('unexpected dialogue SSE field')
            fields[name] = value.removeprefix(b' ')
        return fields

    def summary(self, *, verified_display=None):
        """Full latency needs the same RUN's independently read terminal text."""
        body = ''.join(self._answer).encode('utf-8')
        completed = self.terminal is not None and self.terminal['stage'] == 'completed'
        matches = None
        if verified_display is not None:
            if (any(verified_display.get(key) != value for key, value in self.original.items()) or
                    not isinstance(verified_display.get('text'), str)):
                raise ValueError('terminal readback belongs to another original')
            matches = (verified_display.get('status') == 'completed' and
                       body == verified_display['text'].encode('utf-8'))
        complete_seconds = (max(self._last_answer_seconds, self.terminal['seconds'])
                            if completed and matches and self.first_body_seconds is not None else None)
        return dict(self.original, first_server_progress_seconds=self.first_progress_seconds,
                    first_running_or_tool_seconds=self.first_run_progress_seconds,
                    first_app_visible_progress_seconds=None, first_body_seconds=self.first_body_seconds,
                    complete_seconds=complete_seconds, terminal=self.terminal, answer_matches_original=matches,
                    body_bytes=len(body), body_sha256=sha256(body).hexdigest(), last_event_id=self.last_event_id)
