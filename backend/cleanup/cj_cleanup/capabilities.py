"""Purpose-bound cleanup credentials. They never authenticate ordinary business API."""
from dataclasses import dataclass
import base64,hmac,json,math,re
from hashlib import sha256
from cj_strict_json import reject_duplicates
from .core import encode,identifier,hash_value

VERSION='CLEANUP-CAPABILITY@1'
PURPOSES=('progress','device','device_receipt')
PART=re.compile(r'[A-Za-z0-9_-]+\Z')


class CapabilityUnavailable(Exception):
    def __init__(self):super().__init__('cleanup credential unavailable')


def _b64(value):return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def _unb64(value):
    if not PART.fullmatch(value):raise CapabilityUnavailable()
    try:
        raw=base64.b64decode(value+'='*(-len(value)%4),altchars=b'-_',validate=True)
        if _b64(raw)!=value:raise CapabilityUnavailable()
        return raw
    except ValueError:raise CapabilityUnavailable() from None


@dataclass(frozen=True,repr=False)
class Claims:
    subject_digest:str
    operation_id:str
    binding_id:str
    invocation_id:str|None
    purpose:str
    issued_at:int
    expires_at:int
    key_id:str


class Issuer:
    def __init__(self,*,keys,active_key_id,lifetime_seconds,clock):
        if type(active_key_id) is not str or not PART.fullmatch(active_key_id) or len(active_key_id)>64:
            raise ValueError('bounded cleanup key ID required')
        if any(type(name) is not str or not PART.fullmatch(name) or len(name)>64 for name in keys):
            raise ValueError('bounded cleanup key IDs required')
        if active_key_id not in keys or any(type(k) is not bytes or len(k)<32 for k in keys.values()):
            raise ValueError('explicit cleanup signing keys required')
        if type(lifetime_seconds) is not int or not 1<=lifetime_seconds<=365*86400:
            raise ValueError('explicit bounded cleanup credential lifetime required')
        self.keys=dict(keys);self.active_key_id=active_key_id
        self.lifetime=lifetime_seconds;self.clock=clock

    def issue(self,*,subject_digest,operation_id,binding_id,purpose,invocation_id=None):
        hash_value(subject_digest);identifier(operation_id);identifier(binding_id)
        if purpose not in PURPOSES or (purpose=='device_receipt')!=(invocation_id is not None):
            raise ValueError('exact cleanup purpose required')
        if invocation_id is not None:identifier(invocation_id)
        now=self.clock()
        if type(now) not in (int,float) or not math.isfinite(now) or now<0:raise CapabilityUnavailable()
        now=int(now)
        body=encode(dict(version=VERSION,key_id=self.active_key_id,subject_digest=subject_digest,
            operation_id=operation_id,binding_id=binding_id,invocation_id=invocation_id,
            purpose=purpose,issued_at=now,expires_at=now+self.lifetime))
        signature=hmac.new(self.keys[self.active_key_id],VERSION.encode()+b'\0'+body,sha256).digest()
        return 'ck1.'+self.active_key_id+'.'+_b64(body)+'.'+_b64(signature)

    def verify(self,token,*,purpose,operation_id=None,binding_id=None,invocation_id=None):
        try:
            if type(token) is not str or not 1<=len(token)<=4096:raise CapabilityUnavailable()
            prefix,key_id,payload,signature=token.split('.')
            if prefix!='ck1' or key_id not in self.keys:raise CapabilityUnavailable()
            body=_unb64(payload);mac=_unb64(signature)
            expected=hmac.new(self.keys[key_id],VERSION.encode()+b'\0'+body,sha256).digest()
            if not hmac.compare_digest(mac,expected):raise CapabilityUnavailable()
            value=json.loads(body.decode('utf-8'),object_pairs_hook=reject_duplicates(CapabilityUnavailable))
            if set(value)!={'version','key_id','subject_digest','operation_id','binding_id','invocation_id','purpose','issued_at','expires_at'}:
                raise CapabilityUnavailable()
            if value['version']!=VERSION or value['key_id']!=key_id or value['purpose']!=purpose or purpose not in PURPOSES:
                raise CapabilityUnavailable()
            hash_value(value['subject_digest']);identifier(value['operation_id']);identifier(value['binding_id'])
            if (purpose=='device_receipt')!=(value['invocation_id'] is not None):raise CapabilityUnavailable()
            if value['invocation_id'] is not None:identifier(value['invocation_id'])
            first,last=value['issued_at'],value['expires_at'];now=self.clock()
            if type(first) is not int or type(last) is not int or not 0<=first<last or type(now) not in (int,float) or not math.isfinite(now) or not first<=now<last:
                raise CapabilityUnavailable()
            if (operation_id is not None and value['operation_id']!=operation_id
                    or binding_id is not None and value['binding_id']!=binding_id
                    or invocation_id is not None and value['invocation_id']!=invocation_id):
                raise CapabilityUnavailable()
            return Claims(value['subject_digest'],value['operation_id'],value['binding_id'],value['invocation_id'],
                          value['purpose'],first,last,key_id)
        except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):
            raise CapabilityUnavailable() from None
