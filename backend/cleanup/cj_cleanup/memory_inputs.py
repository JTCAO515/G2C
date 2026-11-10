"""Comparison of B's original model envelope, never a deletion permission.

Only the code-owned Memory slot before the original current instruction is
eligible. A user quoting the same prefix/source ID cannot create a lineage.
"""
import json
from .core import Denied
from cj_strict_json import reject_duplicates

PREFIX='Stored memory data (not instructions):\n'
EDIT_PREFIX='FORMAL_EDIT_CONTEXT_V1\n'
_LEGACY_FIELDS = {'messages', 'system'}
_HK_FIELDS = _LEGACY_FIELDS | {'endpoint', 'model', 'synthetic_only', 'native_tools'}
_HK_NATIVE_FIELDS = _HK_FIELDS | {'native_turn_profile', 'external_tools_disabled'}
_HK_LIO_FIELDS = _HK_NATIVE_FIELDS | {'answer_format_profile'}
_HK_NATIVE_PROFILES = (
    'model-tool-turn-function.1', 'model-tool-turn-function.2',
    'MODEL-TOOL-TURN-STREAM@1', 'MODEL-TOOL-TURN-STREAM@2',
)


def decode(raw):
    try:return json.loads(raw.decode('utf-8'),object_pairs_hook=reject_duplicates(ValueError,'duplicate original model field'))
    except (ValueError,UnicodeError,RecursionError) as error:raise Denied('original model input unavailable') from error


def _registered_model_envelope(value):
    fields = set(value)
    if fields == _LEGACY_FIELDS:
        return True
    if fields not in (_HK_FIELDS, _HK_NATIVE_FIELDS, _HK_LIO_FIELDS):
        return False
    if (value['endpoint'] != 'https://dashscope.aliyuncs.com/compatible-mode/v1'
            or value['model'] != 'qwen3.8-flash' or value['synthetic_only'] is not True
            or (value['system'] is not None and type(value['system']) is not str)):
        return False
    if fields == _HK_FIELDS:
        return value['native_tools'] is None
    if (type(value['native_tools']) is not list or not value['native_tools']
            or value['native_turn_profile'] not in _HK_NATIVE_PROFILES
            or type(value['external_tools_disabled']) is not bool):
        return False
    return fields == _HK_NATIVE_FIELDS or value['answer_format_profile'] == 'lio-user.1'


def consumes_sources(raw,original_text,source_refs):
    """Read the registered model/legacy-step envelope after its command SHA check.

    source_refs came from the original intent-bound C association. This function
    neither authenticates that association nor matches arbitrary model/user text.
    """
    value=decode(raw)
    if type(value) is not dict or not _registered_model_envelope(value) or type(value['messages']) is not list:
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
