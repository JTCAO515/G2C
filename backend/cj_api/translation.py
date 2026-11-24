"""Bounded, stateless translation relay over fixed Beijing DashScope endpoints."""

from base64 import b64decode, b64encode
from contextlib import closing
from dataclasses import dataclass
from http.client import HTTPSConnection, HTTPException, HTTPResponse, IncompleteRead
from io import BytesIO
import json
import logging
import re
import time
from urllib.parse import urlsplit
from uuid import UUID
import wave

from PIL import Image

from cj_auth.interfaces import AdmissionReason, AdmissionStatus
from cj_strict_json import reject_duplicates
from cj_usage.translation_budget import IMAGE_MODEL, SPEECH_MODEL, TEXT_MODEL, TTS_MODEL


VERSION = 'TRANSLATION.1'
ROUTE = '/v1/tools/translate'
IMAGE_LAYOUT_VERSION = 'IMAGE-LAYOUT.1'
IMAGE_LAYOUT_ROUTE = ROUTE + '/image-layout'
TTS_VERSION = 'TTS.1'
TTS_ROUTE = '/v1/tools/tts'
TTS_RESULT_HOST = 'dashscope-result-bj.oss-cn-beijing.aliyuncs.com'
MAX_TTS_TEXT = 280
MAX_TTS_WAV = 2_500_000
MAX_BODY = 4 * 1024 * 1024
MAX_MEDIA = 3 * 1024 * 1024 - 4096
MAX_TEXT = 4000
MAX_LINES = 24
MIN_LAYOUT_PIXELS = 3072
MAX_LAYOUT_PIXELS = 4 * 1024 * 1024
MAX_LAYOUT_DIMENSION = 4096
MAX_SPEECH = 60
SAMPLE_RATE = 16_000
LANGUAGES = {'zh': 'Chinese', 'en': 'English'}
DASHSCOPE = 'dashscope.aliyuncs.com'
CHAT = '/compatible-mode/v1/chat/completions'
MULTIMODAL = '/api/v1/services/aigc/multimodal-generation/generation'
MAX_PROVIDER_RESPONSE = 256 * 1024
SUPPLIER_ID = re.compile(r'[a-zA-Z0-9_-]{1,128}')
_LOGGER = logging.getLogger(__name__)


class TranslationError(Exception):
    def __init__(self, status, code, *, reason=None, supplier_http=None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.reason = reason
        self.supplier_http = supplier_http


def invalid():
    return TranslationError(400, 'invalid_request')


def supplier_unavailable(reason=None, supplier_http=None):
    return TranslationError(502, 'provider_unavailable', reason=reason, supplier_http=supplier_http)


def _audio(data):
    """Re-encode the original PCM and give the ASR one full billed second."""
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
    wire_frames = max(frames, SAMPLE_RATE)
    with wave.open(destination, 'wb') as wav:
        wav.setparams((1, 2, SAMPLE_RATE, wire_frames, 'NONE', 'not compressed'))
        wav.writeframes(pcm + b'\0\0' * (wire_frames - frames))
    return destination.getvalue(), (frames + SAMPLE_RATE - 1) // SAMPLE_RATE



def _layout_size(media, media_type):
    png = media_type == 'image/png'
    expected_end = b'\x00\x00\x00\x00IEND\xaeB\x60\x82' if png else b'\xff\xd9'
    if not media.endswith(expected_end):
        raise invalid()

    formats = ('PNG',) if png else ('JPEG',)
    try:
        with Image.open(BytesIO(media), formats=formats) as image:
            width, height = image.size
            if (not 15 <= width <= MAX_LAYOUT_DIMENSION or not 15 <= height <= MAX_LAYOUT_DIMENSION
                    or not MIN_LAYOUT_PIXELS <= width * height <= MAX_LAYOUT_PIXELS
                    or (png and image.n_frames != 1)):
                raise invalid()
            image.verify()
        # Pillow requires a fresh image object after verify. Decode within the
        # checked canvas to catch truncated image data before reserving OCR.
        with Image.open(BytesIO(media), formats=formats) as image:
            image.load()
    # Pillow may report missing PNG scan data as an IndexError during verify.
    except (Image.DecompressionBombError, EOFError, IndexError, OSError, SyntaxError, ValueError):
        raise invalid() from None
    return width, height


def _layout_lines(words, size):
    if type(words) is not list:
        raise supplier_unavailable('supplier_image_layout', 200)
    if len(words) > MAX_LINES:
        raise TranslationError(422, 'content_too_complex')
    width, height = size
    lines = []
    for row in words:
        if type(row) is not dict:
            raise supplier_unavailable('supplier_image_layout', 200)
        text, location = row.get('text'), row.get('location')
        if (type(text) is not str or not text.strip() or len(text) > MAX_TEXT
                or type(location) is not list or len(location) != 8
                or any(type(c) is not int or not 0 <= c <= (height if i % 2 else width)
                       for i, c in enumerate(location))):
            raise supplier_unavailable('supplier_image_layout', 200)
        try:
            text.encode('utf-8')
        except UnicodeError:
            raise supplier_unavailable('supplier_image_layout', 200) from None
        corners = list(zip(location[0::2], location[1::2]))
        for a, b, c in zip(corners, corners[1:] + corners[:1], corners[2:] + corners[:2]):
            if (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) <= 0:
                raise supplier_unavailable('supplier_image_layout', 200)
        lines.append((text.strip(), location))
    return lines


@dataclass(frozen=True, repr=False)
class TranslationInput:
    request_id: UUID
    kind: str
    source_lang: str
    target_lang: str
    units: int
    value: str
    image_size: tuple[int, int] | None = None

    @classmethod
    def read(cls, raw, *, layout=False):
        try:
            value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate translation field'))
            version = IMAGE_LAYOUT_VERSION if layout else VERSION
            if type(value) is not dict or value.get('version') != version:
                raise invalid()
            kind, source, target = (value[key] for key in ('kind', 'source_lang', 'target_lang'))
            if (kind not in ('text', 'speech', 'image') or (layout and kind != 'image')
                    or source not in LANGUAGES or target not in LANGUAGES or source == target):
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
            image_size = _layout_size(media, media_type) if layout else None
            data = b64encode(media).decode('ascii')
            return cls(request_id, kind, source, target, units, f'data:{media_type};base64,{data}', image_size)
        except (KeyError, RecursionError, TypeError, ValueError):
            raise invalid() from None


class _CompleteHTTPResponse(HTTPResponse):
    def _read_and_discard_trailer(self):
        remaining = 64 * 1024
        while remaining > 0:
            line = self.fp.readline(remaining + 1)
            if line == b'\r\n':
                return
            if not line.endswith(b'\r\n'):
                break
            remaining -= len(line)
        raise IncompleteRead(b'')


@dataclass(frozen=True, repr=False)
class TtsInput:
    request_id: UUID
    language: str
    text: str

    @classmethod
    def read(cls, raw):
        try:
            body = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate TTS field'))
            if (type(body) is not dict or set(body) != {'version', 'request_id', 'language', 'text'}
                    or body['version'] != TTS_VERSION or body['language'] not in LANGUAGES):
                raise invalid()
            reference, text = body['request_id'], body['text']
            if (type(reference) is not str or len(reference) != 36 or type(text) is not str
                    or not text.strip() or len(text) > MAX_TTS_TEXT or '\0' in text):
                raise invalid()
            text.encode('utf-8')
            return cls(UUID(reference), body['language'], text)
        except (KeyError, RecursionError, TypeError, ValueError):
            raise invalid() from None


class DashScopeTranslation:
    def __init__(self, api_key, *, connection=HTTPSConnection):
        self._api_key = api_key
        self._connection = connection

    def _post(self, path, payload, deadline, authorize, *, empty_success_code=False):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise supplier_unavailable()
        body = bytearray()
        phase = 'supplier_connect'
        supplier_http = None
        raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
        try:
            with closing(self._connection(DASHSCOPE, timeout=min(remaining, 12))) as connection:
                connection.connect()
                connection.auto_open = False
                connection.response_class = _CompleteHTTPResponse
                # DNS and TLS can block. Check the App session after both and
                # immediately before the only write carrying the paid request.
                authorize()
                phase = 'supplier_request'
                connection.request('POST', path, body=raw, headers={
                    'Authorization': 'Bearer ' + self._api_key, 'Content-Type': 'application/json',
                })
                phase = 'supplier_response_headers'
                with closing(connection.getresponse()) as response:
                    supplier_http = response.status
                    if supplier_http != 200:
                        raise supplier_unavailable('supplier_http', supplier_http)
                    phase = 'supplier_response_body'
                    length = response.getheader('Content-Length')
                    if response.chunked:
                        if length is not None:
                            raise supplier_unavailable(phase, supplier_http)
                    elif (length is None or re.fullmatch(r'[0-9]{1,7}', length) is None
                          or not 0 < int(length) <= MAX_PROVIDER_RESPONSE):
                        raise supplier_unavailable(phase, supplier_http)
                    while chunk := response.read1(32 * 1024):
                        if len(body) + len(chunk) > MAX_PROVIDER_RESPONSE or time.monotonic() >= deadline:
                            raise supplier_unavailable(phase, supplier_http)
                        body.extend(chunk)
                    if length is not None and len(body) != int(length):
                        raise supplier_unavailable(phase, supplier_http)
            phase = 'supplier_response_json'
            value = json.loads(body, object_pairs_hook=reject_duplicates(ValueError, 'duplicate provider field'))
            if (type(value) is not dict or 'error' in value
                    or 'code' in value and (not empty_success_code or value['code'] != '')):
                raise supplier_unavailable('supplier_error_envelope', supplier_http)
            return value
        except (HTTPException, OSError, RecursionError, ValueError):
            raise supplier_unavailable(phase, supplier_http) from None

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
                    raise supplier_unavailable('supplier_model_identity', 200)
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
                raise supplier_unavailable('supplier_receipt_shape', 200)
            text.encode('utf-8')
            return supplier_id, usage, text
        except (KeyError, TypeError, ValueError):
            raise supplier_unavailable('supplier_receipt_shape', 200) from None

    def recognize_image_layout(self, image, deadline, authorize):
        response = self._post(MULTIMODAL, {
            'model': IMAGE_MODEL,
            'input': {'messages': [{'role': 'user', 'content': [{
                'image': image, 'min_pixels': MIN_LAYOUT_PIXELS, 'max_pixels': MAX_LAYOUT_PIXELS,
                'enable_rotate': False,
            }]}]},
            'parameters': {'ocr_options': {'task': 'advanced_recognition'}, 'max_tokens': 4096},
        }, deadline, authorize)
        try:
            supplier_id = response['request_id']
            choice, = response['output']['choices']
            item, = choice['message']['content']
            if (type(supplier_id) is not str or not SUPPLIER_ID.fullmatch(supplier_id)
                    or choice.get('finish_reason') not in (None, 'stop')):
                raise ValueError('incomplete image layout receipt')
            usage = {key: response['usage'][key] for key in ('input_tokens', 'output_tokens')}
        except (KeyError, TypeError, ValueError):
            raise supplier_unavailable('supplier_receipt_shape', 200) from None
        # A valid billed receipt must be settled even when boxes fail validation.
        result = item.get('ocr_result') if type(item) is dict else None
        return supplier_id, usage, result.get('words_info') if type(result) is dict else None

    def require_safe_text(self, value):
        if self._api_key in value or '\x00' in value:
            raise supplier_unavailable()

    def synthesize(self, request, deadline, authorize):
        result = self._post(MULTIMODAL, {
            'model': TTS_MODEL, 'input': {
                'text': request.text, 'voice': 'Cherry', 'language_type': LANGUAGES[request.language],
            },
        }, deadline, authorize, empty_success_code=True)
        try:
            supplier_id = result['request_id']
            if result.get('status_code', 200) != 200 or not SUPPLIER_ID.fullmatch(supplier_id):
                raise ValueError('invalid TTS receipt')
            output = result['output']
            if type(output) is not dict or output['finish_reason'] != 'stop':
                raise ValueError('incomplete audio result')
            return supplier_id, {'characters': result['usage']['characters']}, output['audio']['url']
        except (KeyError, TypeError, ValueError):
            raise supplier_unavailable('supplier_receipt_shape', 200) from None

    def fetch_audio(self, url, deadline):
        phase = 'supplier_audio_url'
        supplier_http = None
        try:
            if type(url) is not str or len(url) > 2048 or any(ord(char) <= 32 for char in url):
                raise ValueError('invalid TTS asset')
            target = urlsplit(url)
            if (target.scheme not in {'http', 'https'} or target.netloc != TTS_RESULT_HOST
                    or not target.path.startswith('/') or not target.query or target.fragment):
                raise ValueError('untrusted TTS asset')
            path = target.path + '?' + target.query
            phase = 'supplier_audio_connect'
            seconds = deadline - time.monotonic()
            if seconds <= 0:
                raise TimeoutError()
            # The official asset examples use HTTP. Fetch only the same
            # Beijing host over TLS, without sending the DashScope key.
            with closing(self._connection(TTS_RESULT_HOST, timeout=min(seconds, 8))) as connection:
                connection.connect()
                connection.auto_open = False
                transport = connection.sock
                seconds = deadline - time.monotonic()
                if seconds <= 0:
                    raise TimeoutError()
                transport.settimeout(min(seconds, 8))
                phase = 'supplier_audio_request'
                connection.request('GET', path, headers={'Accept': 'audio/wav'})
                phase = 'supplier_audio_headers'
                with closing(connection.getresponse()) as response:
                    supplier_http = response.status
                    if supplier_http != 200:
                        raise supplier_unavailable('supplier_audio_status', supplier_http)
                    length = response.getheader('Content-Length')
                    if (response.chunked or length is None or re.fullmatch(r'[0-9]{1,7}', length) is None
                            or not 44 <= int(length) <= MAX_TTS_WAV):
                        raise supplier_unavailable(phase, supplier_http)
                    remaining = int(length)
                    wav = bytearray()
                    phase = 'supplier_audio_body'
                    while remaining:
                        seconds = deadline - time.monotonic()
                        if seconds <= 0:
                            raise TimeoutError()
                        # read1 never waits for the whole body. Reapply the time
                        # left to the underlying socket on every bounded read.
                        transport.settimeout(min(seconds, 8))
                        chunk = response.read1(min(32 * 1024, remaining))
                        if not chunk:
                            raise IncompleteRead(b'')
                        wav.extend(chunk)
                        remaining -= len(chunk)
            phase = 'invalid_supplier_audio'
            if (not wav.startswith(b'RIFF') or wav[8:12] != b'WAVE'
                    or int.from_bytes(wav[4:8], 'little') != len(wav) - 8 or self._api_key.encode() in wav):
                raise supplier_unavailable(phase, supplier_http)
            with wave.open(BytesIO(wav), 'rb') as audio:
                frames = audio.getnframes()
                if frames <= 0 or len(audio.readframes(frames)) != frames * audio.getnchannels() * audio.getsampwidth():
                    raise supplier_unavailable(phase, supplier_http)
            if time.monotonic() >= deadline:
                raise supplier_unavailable('supplier_audio_deadline', supplier_http)
            return bytes(wav)
        except (TypeError, ValueError, OSError, HTTPException, EOFError, wave.Error):
            raise supplier_unavailable(phase, supplier_http) from None


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
                self.budget.authorization.check_date()

            try:
                if request.image_size is not None and stage == 0:
                    supplier_id, usage, recognized = self.provider.recognize_image_layout(value, deadline, authorize_send)
                    self.budget.finish(operation, stage, model, supplier_id, usage)
                    return recognized
                supplier_id, usage, text = self.provider.request(
                    model, value, request.source_lang, request.target_lang, deadline, authorize_send)
                if model == SPEECH_MODEL and (
                        type(usage['seconds']) is not int or not 1 <= usage['seconds'] <= request.units):
                    raise supplier_unavailable('speech_usage_seconds', 200)
            except TranslationError as error:
                if model == SPEECH_MODEL and error.status == 502:
                    _LOGGER.warning('G2C_TRANSLATION_ASR_FAILURE reason=%s supplier_http=%s',
                                    error.reason, error.supplier_http)
                raise
            self.budget.finish(operation, stage, model, supplier_id, usage)
            self.provider.require_safe_text(text)
            return text

        if request.image_size is not None:
            lines = _layout_lines(call(0, IMAGE_MODEL, request.value), request.image_size)
            for line, _ in lines:
                self.provider.require_safe_text(line)
            items = [dict(source_text=line, translated_text=call(i, TEXT_MODEL, line), location=location)
                     for i, (line, location) in enumerate(lines, 1)]
            if any(not item['translated_text'].strip() for item in items):
                raise supplier_unavailable()
            width, height = request.image_size
            return dict(version=IMAGE_LAYOUT_VERSION, image_width=width, image_height=height, items=items)
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

    def synthesize(self, token, request, owner):
        operation = self.budget.operation(owner, request.request_id, 'tts', 1)
        deadline = time.monotonic() + 45
        self.budget.begin(operation, 0, TTS_MODEL)

        def authorize_send():
            if time.monotonic() >= deadline or self.authorize(token) != owner:
                raise TranslationError(503, 'unavailable')
            self.budget.authorization.check_date()

        receipt, usage, url = self.provider.synthesize(request, deadline, authorize_send)
        self.budget.finish(operation, 0, TTS_MODEL, receipt, usage)
        authorize_send()
        try:
            audio = self.provider.fetch_audio(url, deadline)
        except TranslationError as error:
            _LOGGER.warning('G2C_TRANSLATION_TTS_AUDIO_FAILURE reason=%s supplier_http=%s',
                            error.reason, error.supplier_http)
            raise
        authorize_send()
        return {'version': TTS_VERSION, 'audio': b64encode(audio).decode('ascii')}
