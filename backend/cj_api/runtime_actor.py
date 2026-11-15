"""A simulator operation over the original registered model and fee exit.

The actor has its own native RUN and typed source. It is not a MESSAGE, a
reflection, or a Memory job. No product worker, tools, Trip or Memory publisher
is attached to this registry. The episode host retains the DUT observation and
validates the choice before releasing ordinary traveler text.
"""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
import re

from cj_run.core import Binding
from cj_strict_json import compact, reject_duplicates
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.registered_exit import Registration


VERSION = 'LIO-simulator-actor.1'
REGISTRATION = 'model.simulator_actor.1'
OPERATION = 'model.simulator_actor.0'
DATASET_SHA256 = 'c9e660c4096fc7cacbcf1c51e9074f47693dfca838b24c58d73c7548dbf86763'
SYSTEM_SHA256 = '1043ae2d0612692d4a0791bb7d2f70034da86da35da3e92c1f20db8366a078de'
SCHEMA_SHA256 = 'a8e696bc245500696eafd210525e0fa32a74421c781b25b1f0e3dda04d20f7ca'


def _json(raw):
    def nonfinite(_):
        raise ValueError('finite actor JSON required')
    return json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate actor field'),
                      parse_constant=nonfinite)


def _digest(value):
    return sha256(compact(value, sort_keys=True)).hexdigest()


@dataclass(frozen=True)
class ActorSpecification:
    """Frozen C dataset/prompt/schema, before any provider operation exists."""
    dataset: bytes
    system: str
    schema: bytes
    runtime_card: bytes

    def __post_init__(self):
        if (sha256(self.dataset).hexdigest() != DATASET_SHA256
                or sha256(self.system.encode()).hexdigest() != SYSTEM_SHA256
                or sha256(self.schema).hexdigest() != SCHEMA_SHA256):
            raise ValueError('fixed reviewed simulator inputs required')
        data, schema = _json(self.dataset), _json(self.schema)
        if (data['version'] != 'LIO-simulated-users.1' or len(data['profiles']) != 20
                or compact(schema, sort_keys=True) != self.schema):
            raise ValueError('canonical simulator specification required')
        card = _json(self.runtime_card)
        if (type(card) is not dict or set(card) != {'code_sha', 'image_digest', 'model'}
                or type(card['code_sha']) is not str or re.fullmatch('[a-f0-9]{40}', card['code_sha']) is None
                or type(card['image_digest']) is not str
                or re.fullmatch('sha256:[a-f0-9]{64}', card['image_digest']) is None
                or type(card['model']) is not dict):
            raise ValueError('actual pinned actor runtime card required')

    @property
    def raw(self):
        return compact(dict(version=VERSION, dataset=DATASET_SHA256,
            system=SYSTEM_SHA256, schema=SCHEMA_SHA256,
            runtime_card=_json(self.runtime_card)), sort_keys=True)

    @property
    def key(self):
        return sha256(self.raw).hexdigest()

    def profile(self, profile_id):
        # Immutable original bytes, rather than a caller-owned nested dict.
        rows = [p for p in _json(self.dataset)['profiles'] if p['id'] == profile_id]
        if len(rows) != 1:
            raise ValueError('fixed simulator profile required')
        return rows[0]

    def messages(self, supplied, profile_id, attempt):
        """Check the actual choose() boundary, retaining its exact prompt bytes."""
        if (type(supplied) is not list or len(supplied) != 2
                or supplied[0] != dict(role='system', content=self.system)
                or type(supplied[1]) is not dict
                or set(supplied[1]) != {'role', 'content'} or supplied[1]['role'] != 'user'
                or type(supplied[1]['content']) is not str):
            raise ValueError('fixed simulator messages required')
        payload = _json(supplied[1]['content'])
        if (type(payload) is not dict or set(payload) != {'profile', 'history', 'attempt'}
                or type(attempt) is not int or attempt not in (1, 2, 3)
                or type(payload['attempt']) is not int or payload['attempt'] != attempt
                or compact(payload['profile'], sort_keys=True) != compact(self.profile(profile_id), sort_keys=True)
                or type(payload['history']) is not list or not 2 <= len(payload['history']) <= 8
                or len(payload['history']) % 2):
            raise ValueError('original simulator episode required')
        for index, turn in enumerate(payload['history']):
            if (type(turn) is not dict or set(turn) != {'speaker', 'text'}
                    or turn['speaker'] != ('user' if index % 2 == 0 else 'assistant')
                    or type(turn['text']) is not str or not 0 < len(turn['text']) <= 12000):
                raise ValueError('ordinary public history required')
        profile = self.profile(profile_id)
        if (payload['history'][0]['text'] != profile['opening']
                or len(payload['history'])//2 > profile['behavior']['direct_after']):
            raise ValueError('fixed original episode opening and actor bound required')
        raw = compact(supplied)
        if len(raw) > 28000:
            raise ValueError('bounded original actor prompt required')
        return raw, payload['history']

    def decode_choice(self, raw):
        if type(raw) is not bytes or not 0 < len(raw) <= 12000:
            raise ValueError('bounded original actor output required')
        choice = _json(raw)
        schema = _json(self.schema)
        factors = schema['properties']['answers']['items']['enum']
        if (type(choice) is not dict or set(choice) != {'answers', 'action'}
                or choice['action'] not in ('continue', 'direct')
                or type(choice['answers']) is not list or len(choice['answers']) > 4
                or any(type(key) is not str or key not in factors for key in choice['answers'])
                or len(choice['answers']) != len(set(choice['answers']))):
            raise ValueError('original actor choice violates frozen schema')
        # C's render_choice still checks behavior and releases the wording.
        return choice


@dataclass(frozen=True)
class ActorInput:
    """Trusted episode host binds the actor to its actual protected DUT read.

    `source` is canonical B observer metadata, not model supplied authority.
    `check` repeats original AUTH, source, pin and window guards at the send.
    """
    binding: Binding
    profile_id: str
    attempt: int
    round: int
    messages: bytes
    source: bytes
    specification: ActorSpecification
    check: object

    def __post_init__(self):
        if (type(self.binding) is not Binding or type(self.round) is not int
                or not 1 <= self.round <= 4 or type(self.source) is not bytes
                or not 0 < len(self.source) <= 16384):
            raise ValueError('typed original actor source required')
        source = _json(self.source)
        if (type(source) is not dict or set(source) != {'scope_sha256', 'conversation_id',
                'generation', 'message_id', 'run_id', 'input_sha256', 'observer_ref',
                'answer_sha256', 'history_sha256'}
                or source['scope_sha256'] != sha256(self.binding.scope.encode()).hexdigest()
                or any(type(value) is not str or not value for value in source.values())
                or any(re.fullmatch('[a-f0-9]{64}', source[name]) is None for name in
                    ('scope_sha256', 'input_sha256', 'answer_sha256', 'history_sha256'))
                or source['run_id'] == self.binding.run_id
                or source['conversation_id'] == self.binding.conversation_id):
            raise ValueError('separate same-owner actor RUN required')
        _, history = self.specification.messages(_json(self.messages), self.profile_id, self.attempt)
        if (len(history) != self.round * 2 or _digest(history) != source['history_sha256']
                or sha256(history[-1]['text'].encode()).hexdigest() != source['answer_sha256']):
            raise ValueError('actor input differs from actual DUT observation')

    def original(self):
        return compact(dict(version=VERSION, purpose='simulator_actor',
            kind='simulator_actor', step_id=self.binding.message_id, binding=asdict(self.binding),
            specification_sha256=self.specification.key, profile_id=self.profile_id,
            specification=_json(self.specification.raw),
            attempt=self.attempt, round=self.round, dut_source=_json(self.source),
            messages=_json(self.messages), output_schema=_json(self.specification.schema)), sort_keys=True)


def actor_registration(real_tools, specification):
    """Register on the same real model, original RUN Meter and fee journal."""
    from cj_agent.provider import M4_BASE, M4_MODEL
    config = real_tools.services.model.config
    actual = dict(endpoint=config.base_url, id=config.model_id, parameters=dict(stream=True,
        stream_options={'include_usage': True}, enable_thinking=False,
        max_tokens=min(1024, config.max_output_tokens), response_format={'type': 'json_object'}))
    if (config.base_url != M4_BASE or config.model_id != M4_MODEL
            or _json(specification.runtime_card)['model'] != actual):
        raise ValueError('actual actor model parameters differ from fixed pins')
    def prepare(argument):
        if type(argument) is not ActorInput or argument.specification != specification:
            raise BudgetUnknown('typed frozen actor input required')
        argument.check()
        messages = _json(argument.messages)
        prepared = real_tools._model_input((messages[1:], specification.system, real_tools.services.model))
        def bind(operation, guard):
            if operation.binding != argument.binding:
                raise BudgetUnknown('original actor operation changed')
            def checked():
                argument.check()
                return guard()
            argument.check()
            return prepared.bind_operation(operation, checked)
        return replace(prepared, original_bytes=argument.original(), bind_operation=bind)
    return Registration('model', prepare)
