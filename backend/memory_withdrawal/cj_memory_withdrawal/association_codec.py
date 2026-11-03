"""MEMORY-ERASURE-ASSOCIATION@1 persisted boundary; no cleanup authority."""
from hashlib import sha256

from cj_cleanup.core import Denied
from cj_memory.domain import InvalidInput,strict_object

VERSION='MEMORY-ERASURE-ASSOCIATION@1'
MAX_BYTES=1_000_000


def _identity(value):
    if type(value) is not str or not value.strip() or len(value)>4096 or '\0' in value:
        raise Denied('invalid original erasure identifier')
    try:value.encode('utf-8')
    except UnicodeError as error:raise Denied('invalid original erasure identifier') from error


def _digest(value):
    if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
        raise Denied('invalid original erasure digest')


def _positive(value):
    if type(value) is not int or not 1<=value<=2**63-1:raise Denied('invalid original erasure version')


def _rows(value,fields,identities=(),digests=(),positive=(),limit=1000):
    if type(value) is not list or len(value)>limit:raise Denied('original erasure reference bound exceeded')
    keys=set()
    for row in value:
        if type(row) is not dict or set(row)!=set(fields):raise Denied('invalid original erasure reference')
        for field in identities:_identity(row[field])
        for field in digests:_digest(row[field])
        for field in positive:_positive(row[field])
        key=tuple(row[field] for field in fields)
        if key in keys:raise Denied('duplicate original erasure reference')
        keys.add(key)


def parse_original(raw,request,memory_scope):
    """Validate bytes only AFTER the reader establishes the original intent.

    This public parser does not turn caller bytes into a cleanup grant. B must
    obtain bytes from AssociationReader.read_original with its exact request.
    """
    if type(raw) is not bytes or not 0<len(raw)<=MAX_BYTES:raise Denied('bounded original association required')
    try:value=strict_object(raw)
    except (InvalidInput,ValueError,RecursionError) as error:raise Denied('invalid original association JSON') from error
    fields={'version','operation_id','subject_digest','memory_scope_digest','selection','original_selection',
            'source_refs','operation_refs','message_refs','job_refs','decision_source_sha256s','derived_range'}
    if type(value) is not dict or set(value)!=fields or value['version']!=VERSION:
        raise Denied('explicit original association version required')
    if (value['operation_id']!=request.operation_id or value['subject_digest']!=request.subject_digest
            or value['memory_scope_digest']!=sha256(memory_scope.encode()).hexdigest()
            or value['selection']!=request.selection.to_dict()):
        raise Denied('original association differs from approved selection')
    original=value['original_selection'];selected=value['selection']
    if type(original) is not dict or set(original)!={'item_id','item_version','scope_epoch'}:
        raise Denied('original selected version unavailable')
    _identity(original['item_id']);_positive(original['item_version']);_positive(original['scope_epoch'])
    if (original['item_id']!=selected['item_id'] or original['item_version']+1!=selected['item_version']
            or original['scope_epoch']+1!=selected['scope_epoch']):
        raise Denied('original stop transition differs')
    _rows(value['source_refs'],('source_id','source_version'),('source_id',),positive=('source_version',))
    if not value['source_refs']:raise Denied('complete original source inventory required')
    _rows(value['operation_refs'],('operation_id','input_sha256'),('operation_id',),('input_sha256',))
    _rows(value['message_refs'],('conversation_id','generation','sequence','message_id','input_sha256'),
          ('conversation_id','generation','message_id'),('input_sha256',),('sequence',),limit=10000)
    _rows(value['job_refs'],('job_id','attempt_id','original_input_sha256','state'),
          ('job_id','attempt_id','state'),('original_input_sha256',))
    if any(r['state'] not in ('pending','inflight','unknown','completed','failed','cancelled','erased') for r in value['job_refs']):
        raise Denied('invalid original job state')
    decisions=value['decision_source_sha256s']
    if type(decisions) is not list or len(decisions)>1000:raise Denied('original decision bound exceeded')
    for digest in decisions:_digest(digest)
    if len(set(decisions))!=len(decisions):raise Denied('duplicate original decision')
    if value['derived_range']!=dict(kind='owned_trip_derived_scope',precise_item_match=False,preserve_formal_trips=True):
        raise Denied('explicit owned derived cleanup range required')
    return value
