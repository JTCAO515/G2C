"""Bounded, stateless translation relay over fixed Beijing DashScope endpoints."""

from base64 import b64decode, b64encode
from contextlib import closing
from dataclasses import dataclass
from http.client import HTTPSConnection, HTTPException
from io import BytesIO
import json
import re
import time
from uuid import UUID
import wave


from cj_auth.interfaces import AdmissionReason, AdmissionStatus
from cj_strict_json import reject_duplicates
from cj_usage.translation_budget import IMAGE_MODEL, SPEECH_MODEL, TEXT_MODEL


VERSION = 'TRANSLATION.1'
ROUTE = '/v1/tools/translate'
MAX_BODY = 4 * 1024 * 1024
MAX_MEDIA = 3 * 1024 * 1024 - 4096
MAX_TEXT = 4000
MAX_LINES = 24
MAX_SPEECH = 60
SAMPLE_RATE = 16_000
LANGUAGES = {'zh': 'Chinese', 'en': 'English'}
DASHSCOPE = 'dashscope.aliyuncs.com'
CHAT = '/compatible-mode/v1/chat/completions'
MULTIMODAL = '/api/v1/services/aigc/multimodal-generation/generation'
MAX_PROVIDER_RESPONSE = 256 * 1024
SUPPLIER_ID = re.compile(r'[a-zA-Z0-9_-]{1,128}')


class TranslationError(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status = status
        self.code = code


def invalid():
    return TranslationError(400, 'invalid_request')


def supplier_unavailable():
    return TranslationError(502, 'provider_unavailable')


def _audio(data):
    """Read and re-encode only the counted PCM samples, in memory."""
    try:
        with wave.open(BytesIO(data), 'rb') as src:
            if (src.getnchannels(), src.getsampwidth(), src.getframerate(), src.getcomptype()) != (
                    1, 2, SAMPLE_RATE, 'NONE'):
                raise invalid()
            frames = src.getnframes()
            if not 0 < frames <= MAX_SPEECH * SAMPLE_RATE:
                raise invalid()
            pcm = src.readframes(frames)
            if len(pcm) != frames * 2:
                raise invalid()
    except (EOFError, OSError, ValueError, wave.Error):
        raise invalid() from None
    destination = BytesIO()
    with wave.open(destination, 'wb') as wav:
        wav.setparams((1, 2, SAMPLE_RATE, frames, 'NONE', 'not compressed'))
        wav.writeframes(pcm)
    return destination.getvalue(), (frames + SAMPLE_RATE - 1) // SAMPLE_RATE


@dataclass(frozen=True, repr=False)
class TranslationInput:
    request_id: UUID
    kind: str
    source_lang: str
    target_lang: str
    units: int
    value: str

    @classmethod
    def read(cls, raw):
        try:
            value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate translation field'))
            if type(value) is not dict or value.get('version') != VERSION:
                raise invalid()
            kind, source, target = (value[key] for key in ('kind', 'source_lang', 'target_lang'))
            if (kind not in ('text', 'speech', 'image') or source not in LANGUAGES
                    or target not in LANGUAGES or source == target):
                raise invalid()
            content = 'text' if kind == 'text' else 'media'
            if set(value) != {'version', 'request_id', 'kind', 'source_lang', 'target_lang', content}:
                raise invalid()
            request = value['request_id']
            if type(request) is not str or len(request) != 36:
                raise invalid()
            request_id = UUID(request)
            item = value[content]
            if type(item) is not str:
                raise invalid()
            if kind == 'text':
                if not item.strip() or len(item) > MAX_TEXT or '\x00' in item:
                    raise invalid()
                item.encode('utf-8')
                return cls(request_id, kind, source, target, 1, item)
            media = b64decode(item, validate=True)
            if not 0 < len(media) <= MAX_MEDIA:
                raise invalid()
            if kind == 'speech':
                pcm, units = _audio(media)
                media_type, media = 'audio/wav', pcm
            elif media.startswith(b'\x89PNG\r\n\x1a\n'):
                media_type, units = 'image/png', 1
            elif media.startswith(b'\xff\xd8\xff'):
                media_type, units = 'image/jpeg', 1
            else:
                raise invalid()
            data = b64encode(media).decode('ascii')
            return cls(request_id, kind, source, target, units, f'data:{media_type};base64,{data}')
        except (KeyError, RecursionError, TypeError, ValueError):
            raise invalid() from None


class DashScopeTranslation:
    def __init__(self, api_key, *, connection=HTTPSConnection):
        self._api_key = api_key
        self._connection = connection

    def _post(self, path, payload, deadline, authorize):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise supplier_unavailable()
        body = bytearray()
        raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
        try:
            with closing(self._connection(DASHSCOPE, timeout=min(remaining, 12))) as connection:
                connection.connect()
                connection.auto_open = False
                # DNS and TLS can block. Check the App session after both and
                # immediately before the only write carrying the paid request.
                authorize()
                connection.request('POST', path, body=raw, headers={
                    'Authorization': 'Bearer ' + self._api_key, 'Content-Type': 'application/json',
                })
                with closing(connection.getresponse()) as response:
                    if response.status != 200:
                        raise supplier_unavailable()
                    while chunk := response.read1(32 * 1024):
                        if len(body) + len(chunk) > MAX_PROVIDER_RESPONSE or time.monotonic() >= deadline:
                            raise supplier_unavailable()
                        body.extend(chunk)
            value = json.loads(body, object_pairs_hook=reject_duplicates(ValueError, 'duplicate provider field'))
            if type(value) is not dict or 'error' in value or 'code' in value:
                raise supplier_unavailable()
            return value
        except (HTTPException, OSError, RecursionError, ValueError):
            raise supplier_unavailable() from None

    def request(self, model, item, source, target, deadline, authorize):
        if model == IMAGE_MODEL:
            response = self._post(MULTIMODAL, {
                'model': model,
                'input': {'messages': [{'role': 'user', 'content': [
                    {'image': item, 'max_pixels': 4 * 1024 * 1024},
                ]}]},
                'parameters': {'ocr_options': {'task': 'text_recognition'}, 'max_tokens': 4096},
            }, deadline, authorize)
        else:
            options = ({'asr_options': {'language': source}}
                       if model == SPEECH_MODEL else {
                           'translation_options': {'source_lang': LANGUAGES[source],
                                                   'target_lang': LANGUAGES[target]},
                           'max_tokens': 2048})
            content = ([{'type': 'input_audio', 'input_audio': {'data': item, 'format': 'wav'}}]
                       if model == SPEECH_MODEL else item)
            response = self._post(CHAT, dict(model=model, stream=False,
                messages=[dict(role='user', content=content)], **options), deadline, authorize)
        try:
            if model == IMAGE_MODEL:
                supplier_id = response['request_id']
                choice, = response['output']['choices']
                entry, = choice['message']['content']
                text = entry['text']
                usage = {k: response['usage'][k] for k in ('input_tokens', 'output_tokens')}
                # Native text-recognition results do not always carry finish_reason.
                completed = choice.get('finish_reason') in (None, 'stop')
            else:
                if response['model'] != model:
                    raise supplier_unavailable()
                supplier_id = response['id']
                choice, = response['choices']
                text = choice['message']['content']
                completed = choice['finish_reason'] == 'stop'
                usage = ({'seconds': response['usage']['seconds']} if model == SPEECH_MODEL else {
                    'input_tokens': response['usage']['prompt_tokens'],
                    'output_tokens': response['usage']['completion_tokens'],
                })
            if (type(supplier_id) is not str or not SUPPLIER_ID.fullmatch(supplier_id)
                    or type(text) is not str or len(text) > MAX_TEXT or not completed):
                raise supplier_unavailable()
            text.encode('utf-8')
            return supplier_id, usage, text
        except (KeyError, TypeError, ValueError):
            raise supplier_unavailable() from None

    def require_safe_text(self, value):
        if self._api_key in value or '\x00' in value:
            raise supplier_unavailable()


class TranslationRelay:
    def __init__(self, checker, budget, provider, scope_for):
        self.checker = checker
        self.budget = budget
        self.provider = provider
        self.scope_for = scope_for

    def authorize(self, token):
        decision = self.checker.check(token)
        if decision.status == AdmissionStatus.DENIED:
            if decision.reason in (AdmissionReason.NOT_INVITED, AdmissionReason.NOT_CJ_MEMBER):
                raise TranslationError(403, 'not_enabled')
            raise TranslationError(401, 'sign_in_required')
        if decision.status != AdmissionStatus.ALLOWED or decision.principal is None:
            raise TranslationError(503, 'unavailable')
        principal = decision.principal
        return self.scope_for(principal.issuer, principal.subject)

    def translate(self, token, request, owner):
        operation = self.budget.operation(owner, request.request_id, request.kind, request.units)
        deadline = time.monotonic() + 45

        def call(stage, model, value):
            if time.monotonic() >= deadline:
                raise TranslationError(503, 'unavailable')
            self.budget.begin(operation, stage, model)
            def authorize_send():
                if time.monotonic() >= deadline or self.authorize(token) != owner:
                    raise TranslationError(503, 'unavailable')

            supplier_id, usage, text = self.provider.request(
                model, value, request.source_lang, request.target_lang, deadline, authorize_send)
            if model == SPEECH_MODEL and (
                    type(usage['seconds']) is not int or not 1 <= usage['seconds'] <= request.units):
                raise supplier_unavailable()
            self.budget.finish(operation, stage, model, supplier_id, usage)
            self.provider.require_safe_text(text)
            return text

        if request.kind == 'text':
            pairs = [dict(source_text=request.value, translated_text=call(0, TEXT_MODEL, request.value))]
        else:
            recognized = call(0, SPEECH_MODEL if request.kind == 'speech' else IMAGE_MODEL, request.value)
            lines = ([recognized.strip()] if recognized.strip() else []) if request.kind == 'speech' else [
                line.strip() for line in recognized.splitlines() if line.strip()]
            if len(lines) > MAX_LINES:
                raise TranslationError(422, 'content_too_complex')
            pairs = [dict(source_text=line, translated_text=call(i, TEXT_MODEL, line))
                     for i, line in enumerate(lines, 1)]
        if any(not pair['translated_text'].strip() for pair in pairs):
            raise supplier_unavailable()
        return dict(version=VERSION, kind=request.kind, items=pairs)
