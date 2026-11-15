"""Native simulator DUT messages, separate from G recipes and actor inputs.

The B composition supplies actual AUTH/pins/window, fixed planned IDs, original
worker wait and a qualified observer. Missing observations never become defaults.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from time import monotonic

from cj_message.demo_dialogue import DialogueMessage, LIO_VERSION_V4
from cj_message.auth_boundary import AccessBlocked, IdentityChanged
from cj_message.domain import CommitUnknown, InputConflict, InvalidInput
from cj_strict_json import compact
from runtime_adapter.contract import Unavailable, label, decode

from .runtime_claims import CanonicalClaims
from .runtime_message_claims import MessageClaims

VERSION = 'LIO-simulator-dut.1'


@dataclass(frozen=True)
class DutSpecification:
    """Only public opening/locale and qualified resources enter the DUT host."""
    stage: str
    opening: str
    locale: str
    message_ids: tuple[str, ...]
    runtime_card: bytes

    def __post_init__(self):
        label(self.stage)
        if (self.locale not in ('zh', 'en') or type(self.opening) is not str
                or not self.opening.strip() or len(self.opening.encode()) > 12000
                or type(self.message_ids) is not tuple or not 1 <= len(self.message_ids) <= 5
                or len(set(self.message_ids)) != len(self.message_ids)
                or any(type(mid) is not str or not re.fullmatch(r'c936-[a-f0-9]{64}', mid)
                       for mid in self.message_ids)):
            raise ValueError('fixed public simulator DUT plan required')
        card = decode(self.runtime_card)
        if (type(card) is not dict or set(card) != {'code_sha', 'image_digest', 'model'}
                or type(card['code_sha']) is not str
                or re.fullmatch('[a-f0-9]{40}', card['code_sha']) is None
                or type(card['image_digest']) is not str
                or re.fullmatch('sha256:[a-f0-9]{64}', card['image_digest']) is None
                or type(card['model']) is not dict):
            raise ValueError('actual DUT runtime card required')

    @property
    def raw(self):
        return compact(dict(version=VERSION, stage=self.stage, opening=self.opening,
            locale=self.locale, message_ids=list(self.message_ids),
            runtime_card=json.loads(self.runtime_card)), sort_keys=True)

    @property
    def key(self):
        return sha256(self.raw).hexdigest()


class DutClaims(CanonicalClaims):
    def _request(self, raw):
        if type(raw) is not bytes or len(raw) > 32768:
            raise Unavailable('SIMULATOR_DUT_CLAIM_BOUND')
        value = decode(raw)
        if (type(value) is not dict or set(value) != {'version', 'step_id', 'kind',
                'binding_sha256', 'pins_sha256', 'prior_step_ids', 'native_input_utf8', 'actor_link'}
                or value['version'] != VERSION or value['kind'] != 'simulator_dut'
                or value['binding_sha256'] != self.binding.key
                or value['pins_sha256'] != self.pins.key
                or type(value['prior_step_ids']) is not list
                or type(value['native_input_utf8']) is not str):
            raise Unavailable('SIMULATOR_DUT_CLAIM_FIELDS')
        index = len(value['prior_step_ids'])
        if (index >= len(self.pins.message_ids)
                or value['prior_step_ids'] != list(self.pins.message_ids[:index])
                or value['step_id'] != self.pins.message_ids[index]
                or compact(value, sort_keys=True) != raw):
            raise Unavailable('SIMULATOR_DUT_ORIGINAL_SEQUENCE_CHANGED')
        command = DialogueMessage.parse(value['native_input_utf8'].encode(), version=LIO_VERSION_V4)
        if command.id != value['step_id'] or command.locale != self.pins.locale:
            raise Unavailable('SIMULATOR_DUT_NATIVE_INPUT_CHANGED')
        if index == 0:
            if (command.text != self.pins.opening or not command.new_conversation
                    or command.conversation_id is not None or value['actor_link'] is not None):
                raise Unavailable('SIMULATOR_DUT_OPENING_CHANGED')
        else:
            link=value['actor_link']
            if (command.conversation_id is None or command.new_conversation
                    or type(link) is not dict or set(link)!={'version','actor_id','actor_input_sha256',
                        'choice_sha256','rendered_text_sha256','observer_ref'}
                    or link['version']!='LIO-simulator-rendered.1'
                    or type(link['actor_id']) is not str or re.fullmatch('actor-[a-f0-9]{64}',link['actor_id'])is None
                    or type(link['observer_ref'])is not str or not link['observer_ref']
                    or any(type(link[k])is not str or re.fullmatch('[a-f0-9]{64}',link[k])is None
                        for k in('actor_input_sha256','choice_sha256','rendered_text_sha256'))
                    or link['rendered_text_sha256']!=sha256(command.text.encode()).hexdigest()):
                raise Unavailable('SIMULATOR_DUT_CONTINUATION_CHANGED')
        return value


class DutMessageClaims(MessageClaims):
    claim_type = DutClaims


class NativeSimulatorDut:
    def __init__(self, database, boundary, authority, specification, token_supplier,
                 directory, wait_original, observer, *, deadline, clock=monotonic):
        if authority.line != 'C':
            raise ValueError('simulator DUT uses the original C allocation')
        self.database, self.boundary, self.authority = database, boundary, authority
        self.specification, self.token_supplier = specification, token_supplier
        self.wait_original, self.observer = wait_original, observer
        self.deadline, self.clock = deadline, clock
        self.owner = authority.binding()
        self.claims = DutMessageClaims(directory, boundary, token_supplier, authority,
                                      specification, history_profile='lio.2')
        self.originals = []
        self.latest = None
        self.previous = None
        self.last_observation = None
        self.conversation_id = None
        self.generation = None
        self.pending = None
        self.stopped = False

    def release(self, text, actor_link):
        """The trusted episode bridge releases only C-rendered natural wording."""
        if self.pending is not None or self.stopped:
            raise Unavailable('SIMULATOR_DUT_RELEASE_ALREADY_PENDING_OR_STOPPED')
        self.pending = (text, actor_link)

    def reply(self, text, locale, *, first):
        index = len(self.originals)
        if self.stopped or index >= len(self.specification.message_ids):
            raise Unavailable('SIMULATOR_DUT_STOPPED_OR_EXHAUSTED')
        if (first != (index == 0) or locale != self.specification.locale
                or index == 0 and text != self.specification.opening
                or index > 0 and (self.pending is None or text != self.pending[0])):
            raise Unavailable('SIMULATOR_DUT_RENDERED_TEXT_CHANGED')
        self.authority.require(binding=self.owner, pins_sha256=self.specification.key,
            purpose='message', deadline=self.deadline, read_only=False)
        mid = self.specification.message_ids[index]
        native = dict(version=LIO_VERSION_V4, message_id=mid, text=text, locale=locale)
        if first:
            native['new_conversation'] = True
        else:
            native['conversation_id'] = self.conversation_id
        wire = compact(native)
        value = dict(version=VERSION, step_id=mid, kind='simulator_dut',
            binding_sha256=self.owner.key, pins_sha256=self.specification.key,
            prior_step_ids=list(self.specification.message_ids[:index]),
            native_input_utf8=wire.decode(), actor_link=None if first else self.pending[1])
        raw = compact(value, sort_keys=True)
        # Retain before claim/dispatch so failures remain queryable/accountable.
        self.originals.append(value)
        self.pending = None
        try:
            prepared = self.claims.claim(raw, deadline=self.deadline)
            if not prepared.fresh:
                raise Unavailable('SIMULATOR_DUT_ALREADY_CLAIMED_QUERY_ONLY')
            self.claims.consume(raw, prepared.capability, deadline=self.deadline)
            self.authority.require(binding=self.owner, pins_sha256=self.specification.key,
                purpose='message', deadline=self.deadline, read_only=False)
            previous = self.previous
            def prepare(cursor, scope):
                # receive_lio invokes this inside its original tx.lock_scope,
                # before any native admission. AUTH may have changed since the
                # prior callback, and ordinary MESSAGE writers use this lock.
                if scope != self.owner.scope:
                    raise Unavailable('SIMULATOR_DUT_ADMISSION_OWNER_CHANGED')
                if previous is not None:
                    parent = previous.receipt
                    row = cursor.execute('SELECT c.generation,c.last_sequence,r.run_id,r.input_sha256,r.raw_input '
                        'FROM cj_message_chat c JOIN cj_message_receipt r '
                        'ON r.scope=c.scope AND r.conversation_id=c.conversation_id '
                        'AND r.generation=c.generation AND r.sequence=c.last_sequence '
                        'WHERE c.scope=%s AND c.conversation_id=%s AND c.active '
                        'AND r.message_id=%s FOR UPDATE OF c',
                        (scope,parent.conversation_id,parent.message_id)).fetchone()
                    if (row is None or row[:4] != (parent.generation,parent.sequence,parent.run_id,parent.input_sha256)
                            or row[4] is None or bytes(row[4]) != previous.raw):
                        raise Unavailable('SIMULATOR_DUT_ADMISSION_SOURCE_CHANGED')
                self.database._provision_scope(cursor,scope)
            dispatch_token = self.token_supplier()
            if sha256(dispatch_token.encode()).hexdigest() != self.owner.auth_session_id:
                raise Unavailable('SIMULATOR_DUT_ADMISSION_SESSION_CHANGED')
            receipt = self.boundary.receive_lio(dispatch_token, wire,
                prepare_scope=prepare, version=LIO_VERSION_V4)
            stored = self.query(mid)
            if stored is None or (stored.receipt.run_id, stored.receipt.conversation_id) != (
                    receipt.run_id, receipt.conversation_id):
                raise Unavailable('SIMULATOR_DUT_ADMISSION_ACK_CHANGED')
            if first:
                self.conversation_id, self.generation = receipt.conversation_id, stored.receipt.generation
            elif (stored.receipt.conversation_id, stored.receipt.generation) != (
                    self.conversation_id, self.generation):
                raise Unavailable('SIMULATOR_DUT_GENERATION_CHANGED')
            self.wait_original(receipt, self.deadline)
            observation = self.observer.read(self.token_supplier(), mid, wire)
            self.authority.require(binding=self.owner, pins_sha256=self.specification.key,
                purpose='query', deadline=self.clock()+30, read_only=True)
            self.latest = mid
            self.previous = stored
            self.last_observation = observation
            return observation
        except (AccessBlocked, IdentityChanged, CommitUnknown, InputConflict, InvalidInput) as error:
            self.stopped = True
            raise Unavailable('SIMULATOR_DUT_ORIGINAL_UNAVAILABLE') from error
        except BaseException:
            self.stopped = True
            raise

    def query(self, message_id):
        """Read the same original; this never reconstructs a capability."""
        if message_id not in self.specification.message_ids:
            raise Unavailable('SIMULATOR_DUT_OUTSIDE_PLAN')
        self.authority.require(binding=self.owner, pins_sha256=self.specification.key,
            purpose='query', deadline=self.clock()+30, read_only=True)
        def read(context):
            if context.scope != self.owner.scope:
                raise Unavailable('SIMULATOR_DUT_QUERY_OWNER_CHANGED')
            original=self.claims.query(context,message_id)
            known=[item for item in self.originals if item['step_id']==message_id]
            if original is not None and known:
                receipt=context.query_lio_receipt(message_id)
                if receipt is None or receipt.input_sha256!=sha256(known[0]['native_input_utf8'].encode()).hexdigest():
                    raise Unavailable('SIMULATOR_DUT_QUERY_INPUT_CHANGED')
            return original
        result=self.boundary.with_history_context(self.token_supplier(),read)
        self.authority.require(binding=self.owner,pins_sha256=self.specification.key,
            purpose='query',deadline=self.clock()+30,read_only=True)
        return result
