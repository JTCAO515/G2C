"""External adapter configuration/input boundary. No credentials or authority minting."""
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re

from cj_strict_json import compact, reject_duplicates

VERSION = 'G2C-runtime-adapter.1'
SLOTS = ('prompt.answer_style', 'tool.lookup.description', 'example.clarification')


class Invalid(ValueError):
    pass


class Unavailable(RuntimeError):
    """B cannot prove admission/setup/read availability; never permission to send."""
    def __init__(self, code):
        if type(code) is not str or re.fullmatch('[A-Z0-9_]{1,80}', code) is None:
            raise ValueError('UNAVAILABLE_REASON_CODE')
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise Invalid(code)


def encode(value):
    return compact(value, sort_keys=True)


def digest(value):
    return sha256(encode(value)).hexdigest()


def raw_digest(raw):
    return sha256(raw).hexdigest()


def decode(raw):
    def bad_constant(_):
        raise Invalid('NON_FINITE_JSON')
    try:
        return json.loads(raw, object_pairs_hook=reject_duplicates(Invalid, 'DUPLICATE_KEY'),
                          parse_constant=bad_constant)
    except (json.JSONDecodeError, UnicodeError, RecursionError):
        raise Invalid('INVALID_JSON') from None


def label(value):
    require(type(value) is str and 0 < len(value.encode('utf-8')) <= 256 and '\x00' not in value,
            'INVALID_IDENTIFIER')
    return value


def hash256(value):
    require(type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None, 'INVALID_SHA256')
    return value


def candidate(value):
    require(type(value) is dict and set(value) == set(SLOTS), 'CANDIDATE_SLOTS')
    require(all(type(text) is str and text.strip() and len(text.encode('utf-8')) <= 8192
                for text in value.values()), 'CANDIDATE_TEXT')
    return decode(encode(value))


def seconds(value, ceiling):
    require(type(value) in (int, float) and math.isfinite(value) and 0 < value <= ceiling,
            'INVALID_TIMEOUT')
    return float(value)


@dataclass(frozen=True)
class Binding:
    """B-resolved existing identity, never a client-supplied login/grant."""
    scope: str
    auth_session_id: str
    ledger_id: str
    producer_id: str

    def __post_init__(self):
        for value in (self.scope, self.auth_session_id, self.ledger_id, self.producer_id):
            label(value)

    @property
    def key(self):
        return digest(self.__dict__)


@dataclass(frozen=True)
class Pins:
    """Canonical immutable bytes; mutable caller dictionaries are not retained."""
    raw: bytes

    def __post_init__(self):
        p = decode(self.raw)
        require(type(p) is dict and set(p) == {'version', 'code_sha', 'image_digest', 'adapter_sha256',
                'model', 'system_prompt_sha256', 'tool_schema_sha256', 'tool_implementation_sha256',
                'c0', 'task_version', 'task_sha256', 'score_version', 'score_sha256',
                'preregistration_sha256'}, 'PIN_FIELDS')
        require(p['version'] == VERSION, 'ADAPTER_VERSION')
        require(type(p['code_sha']) is str and re.fullmatch('[a-f0-9]{40}', p['code_sha']) is not None,
                'CODE_PIN')
        require(type(p['image_digest']) is str and
                re.fullmatch('sha256:[a-f0-9]{64}', p['image_digest']) is not None, 'IMAGE_PIN')
        for name in ('adapter_sha256', 'system_prompt_sha256', 'tool_schema_sha256',
                     'tool_implementation_sha256', 'task_sha256', 'score_sha256', 'preregistration_sha256'):
            hash256(p[name])
        require(p['task_version'] == 'G2C-dialogue-cases.2' and p['score_version'] == 'G2C-dialogue-score.2',
                'PUBLIC_INPUT_VERSION')
        model = p['model']
        require(type(model) is dict and set(model) == {'endpoint', 'id', 'parameters'}, 'MODEL_PIN')
        from cj_agent.provider import M4_BASE, M4_MODEL
        require(model['endpoint'] == M4_BASE and model['id'] == M4_MODEL and
                type(model['parameters']) is dict and model['parameters'], 'ORIGINAL_MODEL_EXIT')
        candidate(p['c0'])
        require(encode(p) == self.raw, 'CANONICAL_PINS_REQUIRED')

    @classmethod
    def from_dict(cls, value):
        return cls(encode(value))

    @property
    def value(self):
        return decode(self.raw)

    @property
    def key(self):
        return raw_digest(self.raw)

    def c0(self):
        fragments = self.value['c0']
        return dict(version=VERSION, candidate_id=digest(fragments), fragments=fragments,
                    fragment_sha256={k: raw_digest(v.encode('utf-8')) for k, v in fragments.items()},
                    pins_sha256=self.key, runtime_eligible=False)
