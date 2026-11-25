"""MENU.1 menu explanation for Tools → Menu helper (#1583, contract contracts/api/MENU.1.md).

M4 item 19 with entry 9 (JT 2026-11-25): the App sends one menu photo. The server reads it once with entry 9's
image recognition model, splits the text into lines and takes printed prices off the line ends, then asks the
flash model, at most twice, which lines are dishes and what each dish is: a short bilingual description,
main ingredients, method, portion, a spice level and the ingredients it may contain. Every dish name must be
a continuous part of its own recognised line, or the line becomes "unclear" (the App says: ask staff). The
model never sees the user's dietary needs, account or location: only the recognised menu text. The photo is
handled in memory only and never stored or logged. Explanations are cached by line text, language-neutral
(both languages in one call) and prompt version, holding public dish knowledge only.
Routes, the worker socket, the roster and deployment belong to deploy/hk (S line).
"""

from base64 import b64decode, b64encode
from collections import OrderedDict
import copy
from http.client import HTTPException, HTTPSConnection
import json
import re
from threading import Lock
import time
from typing import Annotated, Literal
import unicodedata
from uuid import UUID

from pydantic import Field, field_validator

from cj_strict_json import reject_duplicates
from cj_usage.menu_budget import CALLS_PER_MENU, MAX_OUTPUT_TOKENS, MODEL, MenuDuplicate, MenuLimit
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.translation_budget import IMAGE_MODEL, TranslationDuplicate, TranslationLimit

from .plugin_tools import PluginError
from .taxi_tools import WireModel, _visible
from .translation import MAX_MEDIA, TranslationError


VERSION = 'MENU.1'
ROUTE = '/v1/tools/menu/explain'
PROMPT_VERSION = 1
LINES_PER_CALL = 25
MAX_LINES = LINES_PER_CALL * CALLS_PER_MENU
MAX_LINE_LENGTH = 60
INGREDIENTS = ('pork', 'beef', 'lamb', 'poultry', 'fish', 'shellfish', 'peanut', 'tree_nut', 'egg', 'dairy',
               'gluten', 'soy', 'sesame', 'alcohol', 'coriander', 'animal_broth')
CERTAINTIES = ('likely', 'possible')
TEXT_FIELDS = ('summary', 'ingredients', 'method', 'portion')
FIELD_LIMITS = {'zh': 80, 'en': 200}
DEADLINE_SECONDS = 45
DASHSCOPE = 'dashscope.aliyuncs.com'
CHAT = '/compatible-mode/v1/chat/completions'
MAX_PROVIDER_RESPONSE = 256 * 1024
SUPPLIER_ID = re.compile(r'[A-Za-z0-9_-]{1,128}')

_CJK = re.compile(r'[一-鿿]')
# A printed price at the end of a line (checked after NFKC, so ￥ is ¥): ¥38, 38元, 38/份, 12.5元/位.
_PRICE_TAIL = re.compile(r'\s*(?:¥\s*)?\d{1,4}(?:\.\d{1,2})?\s*(?:元)?\s*(?:/\s*(?:份|位|例|斤|只|个|碗|盘|杯|瓶|两|串))?\s*$')
# No guarantee that something is absent: allergy and diet flags are the App's, from `contains` only.
_ABSENCE = re.compile(r'安全|不含|无(?:花生|坚果|海鲜|虾|蟹|鱼|蛋|奶|麸质|麦|大豆|芝麻|酒|猪|牛|羊|肉|过敏)|'
                      r'\b(?:safe|free of|[a-z]+-free|does not contain|doesn\'t contain|contains no|no (?:pork|beef|'
                      r'meat|nuts?|peanuts?|shellfish|fish|eggs?|dairy|milk|gluten|wheat|soy|sesame|alcohol))\b',
                      re.IGNORECASE)

RULES = """你在帮外国游客看懂一张中文菜单。输入是菜单照片识别出的若干行，JSON 数组，每项 {"i": 行号, "text": 该行文字}。
逐行判断：
- dish：这一行是一道菜（含主食、汤、饮品）的名字；
- unclear：看起来是菜名，但字缺失或错乱，看不出是什么菜；
- other：店名、分类标题、说明文字等，不是菜。
只输出一个 JSON 对象 {"items": [...]}：每个输入行恰好一项，按行号顺序。每项字段：
- "i"：行号；"kind"：dish、unclear 或 other。
- kind 为 dish 时再给：
  "name_zh"：该行里的菜名原文，必须是该行文字中连续的一段，不改字、不补字；
  "name_en"：常见英文菜名；
  "summary_en"、"summary_zh"：一句话说明这是什么菜；
  "ingredients_en"、"ingredients_zh"：主要食材；
  "method_en"、"method_zh"：做法，如炒、炖、蒸；
  "portion_en"、"portion_zh"：大致分量，如「一盘，约 2 人份」；
  "spice"：0 不辣、1 微辣、2 中辣、3 很辣，拿不准写 null；
  "contains"：对象，列出这道菜按常见做法会用到的配料。键只能从 pork, beef, lamb, poultry, fish, shellfish, peanut, tree_nut, egg, dairy, gluten, soy, sesame, alcohol, coriander, animal_broth 中选；值为 "likely"（通常会用）或 "possible"（常作调料、高汤或点缀）。宁可多列 possible，不要漏。
规则：按这道菜在中国常见的做法写，各店可能不同；拿不准的字段写 null，不要编造。不写价格，不写「安全」「不含」「无××」这类保证。中文字段每项不超过 40 个字，英文字段不超过 120 个字符。"""


class MenuRequest(WireModel):
    version: Literal['MENU.1']
    request_id: Annotated[str, Field(min_length=36, max_length=36)]
    media: Annotated[str, Field(min_length=8, max_length=(MAX_MEDIA * 4) // 3 + 4)]

    @field_validator('request_id')
    @classmethod
    def valid_id(cls, value):
        if str(UUID(value)) != value.lower():
            raise ValueError('explicit request UUID required')
        return value

    @field_validator('media')
    @classmethod
    def photo(cls, value):
        image_url(value)
        return value


def image_url(media):
    """A data URL for one JPEG or PNG photo of at most MAX_MEDIA bytes, or ValueError."""
    data = b64decode(media, validate=True)
    if not 0 < len(data) <= MAX_MEDIA:
        raise ValueError('photo size')
    if data.startswith(b'\xff\xd8\xff'):
        kind = 'image/jpeg'
    elif data.startswith(b'\x89PNG\r\n\x1a\n'):
        kind = 'image/png'
    else:
        raise ValueError('JPEG or PNG photo required')
    return f'data:{kind};base64,{b64encode(data).decode("ascii")}'


def menu_lines(text):
    """Recognised lines that may name a dish: (name text, printed price or None), and whether some were cut."""
    lines = []
    for raw in text.splitlines():
        line = unicodedata.normalize('NFKC', raw).strip()
        if not line or len(line) > MAX_LINE_LENGTH or not _visible(line):
            continue
        price = None
        match = _PRICE_TAIL.search(line)
        if match and match.start() > 0 and re.search(r'\d', match.group(0)):
            price, line = match.group(0).strip(), line[:match.start()].strip()
        if _CJK.search(line):
            lines.append(dict(text=line, price=price))
    return lines[:MAX_LINES], len(lines) > MAX_LINES


def cache_key(line):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', line))


class MemoryMenuCache:
    """Line text → checked explanation; public dish knowledge only, never photos or user data."""

    def __init__(self, limit=5000):
        self.limit = limit
        self.values = OrderedDict()
        self.lock = Lock()

    def get(self, key):
        with self.lock:
            value = self.values.get((key, PROMPT_VERSION))
            if value is not None:
                self.values.move_to_end((key, PROMPT_VERSION))
            return copy.deepcopy(value)

    def put(self, key, value):
        with self.lock:
            self.values[(key, PROMPT_VERSION)] = copy.deepcopy(value)
            self.values.move_to_end((key, PROMPT_VERSION))
            while len(self.values) > self.limit:
                self.values.popitem(last=False)


def messages_for(lines):
    rows = [dict(i=index, text=line) for index, line in enumerate(lines)]
    return [dict(role='system', content=RULES), dict(role='user', content=json.dumps(rows, ensure_ascii=False))]


def _field(value, language):
    if value is None:
        return ''
    if (type(value) is not str or len(value.strip()) > FIELD_LIMITS[language] or not _visible(value)
            or _ABSENCE.search(unicodedata.normalize('NFKC', value))):
        return ''
    return value.strip()


def _dish(item, line):
    """A checked dish for one line, or None when the name is not the line's own text."""
    name = item.get('name_zh')
    if type(name) is not str:
        return None
    name = unicodedata.normalize('NFKC', name).strip()
    if not _CJK.search(name) or not _visible(name) or cache_key(name) not in cache_key(line):
        return None
    name_en = _field(item.get('name_en'), 'en')
    if not name_en:
        return None
    spice = item.get('spice')
    if spice is not None and (type(spice) is not int or not 0 <= spice <= 3):
        return None
    contains = item.get('contains')
    if contains is None:
        contains = {}
    if type(contains) is not dict:
        return None
    # Unknown ingredients are not shown; an unclear certainty for a known one is read as "possible".
    contains = {key: value if value in CERTAINTIES else 'possible'
                for key, value in contains.items() if key in INGREDIENTS}
    dish = dict(kind='dish', name_zh=name, name_en=name_en, spice=spice, contains=contains)
    for field in TEXT_FIELDS:
        for language in ('en', 'zh'):
            dish[f'{field}_{language}'] = _field(item.get(f'{field}_{language}'), language)
    return dish


def checked_items(raw, lines):
    """Line index → checked entry for the model's JSON, or None when it is not the agreed object.

    A dish whose name is not its own line's text, or whose fields fail, becomes "unclear": the App then asks
    the user to ask staff instead of showing a guess."""
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate menu field'))
    except (TypeError, ValueError):
        return None
    items = value.get('items') if type(value) is dict else None
    if type(items) is not list or len(items) > len(lines):
        return None
    result = {}
    for item in items:
        index = item.get('i') if type(item) is dict else None
        if type(index) is not int or not 0 <= index < len(lines) or index in result:
            return None
        kind = item.get('kind')
        if kind == 'dish':
            result[index] = _dish(item, lines[index]) or dict(kind='unclear')
        elif kind in ('unclear', 'other'):
            result[index] = dict(kind=kind)
        else:
            return None
    return result


class DashScopeMenu:
    """Minimal Beijing DashScope chat client for flash, JSON output, no thinking, bounded output."""

    def __init__(self, api_key, *, connection=None, timeout=40):
        if type(api_key) is not str or not api_key:
            raise ValueError('server-side DashScope key required')
        self._api_key = api_key
        self._connection = connection or (lambda: HTTPSConnection(DASHSCOPE, timeout=timeout))

    def generate(self, messages, reserve):
        body = json.dumps(dict(model=MODEL, messages=messages, max_tokens=MAX_OUTPUT_TOKENS, temperature=0.2,
                               response_format={'type': 'json_object'}, enable_thinking=False),
                          ensure_ascii=False).encode()
        connection = self._connection()
        try:
            if hasattr(connection, 'connect'):
                connection.connect()  # DNS and TLS first; the call is reserved only when it can be sent
            reserve()
            connection.request('POST', CHAT, body, {'Authorization': 'Bearer ' + self._api_key,
                                                    'Content-Type': 'application/json'})
            response = connection.getresponse()
            data = response.read(MAX_PROVIDER_RESPONSE + 1)
            if response.status != 200 or len(data) > MAX_PROVIDER_RESPONSE:
                raise PluginError(502, 'supplier_unavailable')
            reply = json.loads(data, object_pairs_hook=reject_duplicates(ValueError, 'duplicate DashScope field'))
            choice, = reply['choices']
            supplier, text, finish = reply['id'], choice['message']['content'], choice['finish_reason']
            usage = {'input_tokens': reply['usage']['prompt_tokens'],
                     'output_tokens': reply['usage']['completion_tokens']}
            if (reply['model'] != MODEL or type(supplier) is not str or SUPPLIER_ID.fullmatch(supplier) is None
                    or type(text) is not str or finish not in ('stop', 'length') or self._api_key in text):
                raise ValueError('unexpected receipt')
        except PluginError:
            raise
        except (KeyError, TypeError, ValueError, OSError, HTTPException):
            raise PluginError(502, 'supplier_unavailable') from None
        finally:
            connection.close()
        return supplier, usage, text, finish


def _wire(index, entry, line):
    item = dict(id=f'l{index}', kind=entry['kind'], price_text=line['price'])
    if entry['kind'] == 'dish':
        item.update({key: value for key, value in entry.items() if key != 'kind'})
    return item


class MenuService:
    def __init__(self, reader, model, budget, image_budget, cache, *, clock=time.monotonic):
        self.reader = reader              # entry 9 image recognition (`translation.DashScopeTranslation`)
        self.model = model                # `DashScopeMenu`
        self.budget = budget              # `menu_budget.MenuBudget`
        self.image_budget = image_budget  # `translation_budget.TranslationBudget`
        self.cache = cache
        self.clock = clock

    def _read(self, scope, request, authorize, deadline):
        """Entry 9: one image recognition, recorded in the translation journal (50 images per day)."""
        operation = self.image_budget.operation(scope, UUID(request.request_id), 'image', 1)
        try:
            self.image_budget.begin(operation, 0, IMAGE_MODEL)
        except TranslationDuplicate:
            raise PluginError(409, 'request_already_used') from None
        except TranslationLimit:
            raise PluginError(429, 'quota_exceeded') from None

        def authorize_send():
            if self.clock() >= deadline:
                raise PluginError(503, 'unavailable')
            authorize()

        try:
            supplier, usage, text = self.reader.request(IMAGE_MODEL, image_url(request.media), 'zh', 'en',
                                                        deadline, authorize_send)
        except TranslationError:
            raise PluginError(502, 'supplier_unavailable') from None
        self.image_budget.finish(operation, 0, IMAGE_MODEL, supplier, usage)
        self.reader.require_safe_text(text)
        return text

    def explain(self, scope, request, authorize):
        authorize()
        deadline = self.clock() + DEADLINE_SECONDS
        try:
            admitted = self.budget.admits(scope)
        except Exception:
            raise PluginError(503, 'unavailable') from None  # nothing was sent
        if not admitted:
            raise PluginError(429, 'quota_exceeded')
        try:
            lines, truncated = menu_lines(self._read(scope, request, authorize, deadline))
            results, todo = {}, []
            for index, line in enumerate(lines):
                cached = self.cache.get(cache_key(line['text']))
                if cached is None:
                    todo.append(index)
                else:
                    results[index] = cached
            chunks = [todo[start:start + LINES_PER_CALL] for start in range(0, len(todo), LINES_PER_CALL)]
            if chunks:
                operation = self.budget.operation(scope, UUID(request.request_id), len(chunks))
                for stage, chunk in enumerate(chunks):
                    if self.clock() >= deadline:
                        raise PluginError(503, 'unavailable')

                    def reserve(stage=stage):
                        authorize()
                        self.budget.begin(operation, stage)

                    texts = [lines[index]['text'] for index in chunk]
                    supplier, usage, raw, finish = self.model.generate(messages_for(texts), reserve)
                    self.budget.finish(operation, stage, supplier, usage)
                    checked = checked_items(raw, texts) if finish == 'stop' else None
                    if checked is None:
                        raise PluginError(502, 'supplier_unavailable')
                    for local, index in enumerate(chunk):
                        # A line the model skipped is not shown and not cached, so a later menu asks again.
                        entry = checked.get(local, dict(kind='other'))
                        results[index] = entry
                        if local in checked and entry['kind'] != 'unclear':
                            self.cache.put(cache_key(lines[index]['text']), entry)
        except MenuDuplicate:
            raise PluginError(409, 'request_already_used') from None
        except MenuLimit:
            raise PluginError(429, 'quota_exceeded') from None
        except BudgetUnknown:
            raise PluginError(503, 'unavailable') from None
        items = [_wire(index, results[index], line) for index, line in enumerate(lines)
                 if results[index]['kind'] != 'other']
        authorize()
        return dict(version=VERSION, items=items, truncated=truncated)
