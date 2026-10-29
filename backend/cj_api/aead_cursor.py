"""Optional host-configured AES-256-GCM cursor adapter. No default key/profile/clock.

The internal live-context addition was confirmed by the MESSAGE owner via Main.
Type checks only catch misuse: context must originate in the current trusted
with_history_context callback. No caller metadata object grants authorization.
"""
import base64
import json
import os
import re
from types import MappingProxyType
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .history_config import CursorBinding, CursorResyncRequired, CursorUnavailable
from cj_message.auth_boundary import HistoryReadContext
from cj_message.domain import Cursor, ChatListCursor

MAX_I64=(1<<63)-1
_LABEL=re.compile(r'[A-Za-z0-9_-]+\Z')
_FIELDS={'generation','epoch','through','after','issued_at','expires_at'}


def _integer(value,minimum=0):
    if type(value) is not int or not minimum<=value<=MAX_I64:raise ValueError('invalid integer')
    return value


def _json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def _unique(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError('duplicate field')
        result[key]=value
    return result


class AeadCursorCodec:
    def __init__(self,*,keys,active_key_id,version,clock,max_ttl_seconds,
                 max_token_bytes,max_plaintext_bytes,max_binding_bytes):
        try:
            if (not isinstance(keys,dict) or not keys or clock is None
                    or any(type(v) is not int or v<=0 for v in
                           (max_ttl_seconds,max_token_bytes,max_plaintext_bytes,max_binding_bytes))
                    or max_ttl_seconds>MAX_I64):raise ValueError()
            for label in (*keys,active_key_id,version):
                if type(label) is not str or _LABEL.fullmatch(label) is None or len(label)>max_token_bytes:
                    raise ValueError()
            if active_key_id not in keys or any(type(k) is not bytes or len(k)!=32 for k in keys.values()):
                raise ValueError()
            self._keys=MappingProxyType({kid:AESGCM(key) for kid,key in keys.items()})
        except Exception:raise CursorUnavailable() from None
        self._active=active_key_id;self._version=version;self._clock=clock
        self._max_ttl=max_ttl_seconds;self._max_token=max_token_bytes
        self._max_plain=max_plaintext_bytes;self._max_binding=max_binding_bytes

    def _now(self):
        try:return _integer(self._clock())
        except Exception:raise CursorUnavailable() from None

    def _binding(self,binding):
        # Read public owner properties while active, never a caller boolean,
        # second authentication result or decoded token scope.
        try:
            context=getattr(binding,'context',None)
            if type(binding) is not CursorBinding or type(context) is not HistoryReadContext:raise ValueError()
            principal,scope=context.principal,context.scope
            values=(binding.environment,binding.issuer,binding.subject,binding.audience,binding.scope)
            if any(type(v) is not str or not v for v in values):raise ValueError()
            if (principal.issuer,principal.subject,principal.audience,scope)!=(binding.issuer,binding.subject,binding.audience,binding.scope):raise ValueError()
            if binding.purpose not in ('conversations','message_history'):raise ValueError()
            if (binding.purpose=='conversations' and binding.conversation_id is not None
                    or binding.purpose=='message_history' and (type(binding.conversation_id) is not str or not binding.conversation_id)):
                raise ValueError()
            if sum(len(v.encode('utf-8')) for v in (*values,binding.purpose,binding.conversation_id or ''))>self._max_binding:
                raise ValueError()
            return context,(*values,binding.purpose,binding.conversation_id)
        except Exception:raise CursorUnavailable() from None

    def _aad(self,binding,kid):
        aad=_json({'domain':'CJ-HISTORY-CURSOR-AES256GCM','version':self._version,'key_id':kid,
            'environment':binding.environment,'issuer':binding.issuer,'subject':binding.subject,
            'audience':binding.audience,'scope':binding.scope,'purpose':binding.purpose,
            'conversation_id':binding.conversation_id})
        if len(aad)>self._max_binding:raise CursorUnavailable()
        return aad

    def _ttl(self,ttl):
        if type(ttl) is not int or not 1<=ttl<=self._max_ttl:raise CursorUnavailable()
        return ttl

    def encode(self,cursor,*,binding,ttl_seconds):
        context,metadata=self._binding(binding)
        try:
            ttl=self._ttl(ttl_seconds);now=self._now();expiry=_integer(now+ttl)
            expected=ChatListCursor if binding.purpose=='conversations' else Cursor
            if type(cursor) is not expected or cursor.scope!=binding.scope:raise ValueError()
            if type(cursor) is Cursor and cursor.conversation_id!=binding.conversation_id:raise ValueError()
            generation=cursor.scope_generation if type(cursor) is ChatListCursor else cursor.generation
            if type(generation) is not str or not generation or len(generation.encode('utf-8'))>self._max_plain:raise ValueError()
            epoch,through,after=(_integer(cursor.epoch),_integer(cursor.through),_integer(cursor.after))
            if after>through:raise ValueError()
            payload=_json(dict(generation=generation,epoch=epoch,through=through,after=after,issued_at=now,expires_at=expiry))
            if len(payload)>self._max_plain:raise ValueError()
            # Fresh public 96-bit OS nonce, never caller supplied; no secret generated.
            nonce=os.urandom(12)
            encrypted=self._keys[self._active].encrypt(nonce,payload,self._aad(binding,self._active))
            encoded=base64.urlsafe_b64encode(nonce+encrypted).rstrip(b'=').decode('ascii')
            token=self._version+'.'+self._active+'.'+encoded
            if len(token)>self._max_token:raise ValueError()
            current,current_metadata=self._binding(binding)
            if current is not context or current_metadata!=metadata:raise CursorUnavailable()
            return token
        except CursorUnavailable:raise
        except Exception:raise CursorUnavailable() from None

    def decode(self,token,*,binding,ttl_seconds):
        # A trusted current server context always precedes token parsing or crypto.
        context,metadata=self._binding(binding)
        try:
            ttl=self._ttl(ttl_seconds)
            if type(token) is not str or not token.isascii() or not 1<=len(token)<=self._max_token:raise ValueError()
            version,kid,encoded=token.split('.')
            if version!=self._version or kid not in self._keys or _LABEL.fullmatch(encoded) is None:raise ValueError()
            blob=base64.b64decode(encoded+'='*(-len(encoded)%4),altchars=b'-_',validate=True)
            if base64.urlsafe_b64encode(blob).rstrip(b'=').decode('ascii')!=encoded:raise ValueError()
            if not 28<=len(blob)<=self._max_plain+28:raise ValueError()
            plaintext=self._keys[kid].decrypt(blob[:12],blob[12:],self._aad(binding,kid))
            if len(plaintext)>self._max_plain:raise ValueError()
            payload=json.loads(plaintext.decode('utf-8'),object_pairs_hook=_unique,
                               parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
            if type(payload) is not dict or set(payload)!=_FIELDS:raise ValueError()
            generation=payload['generation']
            if type(generation) is not str or not generation or len(generation.encode('utf-8'))>self._max_plain:raise ValueError()
            epoch,through,after,issued,expiry=(_integer(payload[n]) for n in ('epoch','through','after','issued_at','expires_at'))
            now=self._now()
            if not (after<=through and issued<=now<expiry and 0<expiry-issued<=ttl):raise ValueError()
            current,current_metadata=self._binding(binding)
            if current is not context or current_metadata!=metadata:raise CursorUnavailable()
            # Scope/query come ONLY from live trusted context binding, never token.
            if binding.purpose=='conversations':return ChatListCursor(binding.scope,generation,epoch,through,after)
            return Cursor(binding.scope,binding.conversation_id,generation,epoch,through,after)
        except CursorUnavailable:raise
        except Exception:raise CursorResyncRequired() from None
