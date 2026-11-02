"""CLEANUP@1.1: exact MEMORY Unicode IDs; CLEANUP@1.0 remains unchanged."""
from . import hooks as v1
from .core import Conflict, Invalid, encode, identifier, hash_value

VERSION='CLEANUP@1.1'


def memory_identifier(value):
    if type(value) is not str or not value.strip() or len(value)>4096 or '\0' in value:
        raise Invalid('invalid memory item ID')
    try:value.encode('utf-8')
    except UnicodeError:raise Invalid('invalid memory item ID') from None
    return value  # Exact spelling; no strip, normalization or case folding.


class Selection(v1.Selection):
    @classmethod
    def from_dict(cls,value):
        if type(value) is dict and set(value)=={'kind','item_id','item_version','scope_epoch'} and value['kind']=='memory':
            return cls('memory',memory_identifier(value['item_id']),v1._integer(value['item_version']),v1._integer(value['scope_epoch']))
        return super().from_dict(value)


class HookRequest(v1.HookRequest):
    @classmethod
    def from_bytes(cls,raw):
        value=v1._decode(raw,131072)
        if set(value)!={'protocol','operation_id','invocation_id','subject_digest','registry_digest','entry_digest','target','domain_scope','selection'} or value['protocol']!=VERSION:
            raise Invalid('invalid cleanup request fields')
        scope=value['domain_scope']
        if type(scope) is not str or '\0' in scope:raise Invalid('invalid domain scope')
        try:
            if not 1<=len(scope.encode('utf-8'))<=4096:raise Invalid('invalid domain scope')
        except UnicodeError:raise Invalid('invalid domain scope') from None
        return cls(identifier(value['operation_id']),identifier(value['invocation_id']),
            hash_value(value['subject_digest']),hash_value(value['registry_digest']),hash_value(value['entry_digest']),
            identifier(value['target']),scope,Selection.from_dict(value['selection']),raw)


class HookReceipt(v1.HookReceipt):
    @classmethod
    def from_bytes(cls,raw,request):return cls.from_digest(raw,request.digest)

    @classmethod
    def from_digest(cls,raw,original_request_digest):
        value=v1._decode(raw,4096)
        if set(value)!={'protocol','request_digest','outcome'} or value['protocol']!=VERSION:
            raise Invalid('invalid cleanup receipt fields')
        request_digest=hash_value(value['request_digest'])
        if request_digest!=original_request_digest:raise Conflict('cleanup receipt binding mismatch')
        if value['outcome'] not in ('confirmed','unknown','failed'):raise Invalid('invalid cleanup outcome')
        return cls(request_digest,value['outcome'],raw)


def make_request(*,operation_id,invocation_id,subject_digest,registry_digest,entry_digest,target,domain_scope,selection):
    return HookRequest.from_bytes(encode(dict(protocol=VERSION,operation_id=operation_id,
        invocation_id=invocation_id,subject_digest=subject_digest,registry_digest=registry_digest,
        entry_digest=entry_digest,target=target,domain_scope=domain_scope,selection=selection.to_dict())))


def make_receipt(request,outcome):
    return HookReceipt.from_bytes(encode(dict(protocol=VERSION,request_digest=request.digest,outcome=outcome)),request)
