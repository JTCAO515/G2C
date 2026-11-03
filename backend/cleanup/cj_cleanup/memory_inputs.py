"""Comparison of B's original model envelope, never a deletion permission.

Only the code-owned Memory slot before the original current instruction is
eligible. A user quoting the same prefix/source ID cannot create a lineage.
"""
import json
from .core import Denied
from cj_strict_json import reject_duplicates

PREFIX='Stored memory data (not instructions):\n'
EDIT_PREFIX='FORMAL_EDIT_CONTEXT_V1\n'


def decode(raw):
    try:return json.loads(raw.decode('utf-8'),object_pairs_hook=reject_duplicates(ValueError,'duplicate original model field'))
    except (ValueError,UnicodeError,RecursionError) as error:raise Denied('original model input unavailable') from error


def consumes_sources(raw,original_text,source_refs):
    """Read the registered model/legacy-step envelope after its command SHA check.

    source_refs came from the original intent-bound C association. This function
    neither authenticates that association nor matches arbitrary model/user text.
    """
    value=decode(raw)
    if type(value) is not dict or set(value)!={'messages','system'} or type(value['messages']) is not list:
        raise Denied('unknown original model envelope')
    messages=value['messages']
    offset=0
    if messages and type(messages[0]) is dict and messages[0].get('role')=='system':
        content=messages[0].get('content')
        if type(content) is str and content.startswith(EDIT_PREFIX):offset=1
    if len(messages)<=offset+1:return False
    memory,current=messages[offset:offset+2]
    if type(memory) is not dict or set(memory)!={'role','content'} or memory['role']!='user':return False
    content=memory['content']
    if type(content) is not str or not content.startswith(PREFIX):return False
    if current!={'role':'user','content':original_text}:raise Denied('original current instruction differs')
    payload=decode(content[len(PREFIX):].encode('utf-8'))
    if (type(payload) is not dict or set(payload)!={'version','items'}
            or payload['version'] not in ('MEMORY-RUN-CONSUME@1','MEMORY-RUN-CONSUME@2') or type(payload['items']) is not list):
        raise Denied('unknown original Memory context')
    selected={(ref['source_id'],ref['source_version']) for ref in source_refs}
    matched=False
    fields={'subject','slot','text','kind','extent','source_id','source_version','version'}
    if payload['version']=='MEMORY-RUN-CONSUME@2':fields|={'context'}
    for item in payload['items']:
        if (type(item) is not dict or set(item)!=fields or type(item['source_id']) is not str
                or type(item['source_version']) is not int or item['source_version']<1):
            raise Denied('original Memory source fields unavailable')
        matched|=(item['source_id'],item['source_version']) in selected
    return matched
