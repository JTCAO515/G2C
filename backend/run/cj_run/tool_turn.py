"""MODEL-TOOL-TURN@1: untrusted model data, never owner/budget authority."""
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: bytes


@dataclass(frozen=True)
class ToolTurn:
    answer_zh: str | None
    answer_en: str | None
    calls: tuple[ToolCall,...]


def parse_turn(raw:bytes,allowed_tools):
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('duplicate_tool_turn_field')
            value[key]=item
        return value
    def constant(value):raise ValueError('non_json_number')
    if type(raw) is not bytes or len(raw)>65536:raise ValueError('bounded_tool_turn_required')
    try:value=json.loads(raw.decode('utf8'),object_pairs_hook=pairs,parse_constant=constant)
    except (ValueError,UnicodeError,RecursionError):raise ValueError('invalid_tool_turn') from None
    if (type(value) is not dict or set(value)!={'version','kind','answer','calls'}
            or value['version']!='MODEL-tool-turn.1'):
        raise ValueError('unsupported_tool_turn')
    if value['kind']=='answer':
        answer=value['answer']
        if (type(answer) is not dict or set(answer)!={'zh','en'} or value['calls']!=[]
                or any(type(answer[k]) is not str or not answer[k].strip() for k in ('zh','en'))):
            raise ValueError('invalid_bilingual_answer')
        answer['zh'].encode('utf8');answer['en'].encode('utf8')
        return ToolTurn(answer['zh'],answer['en'],())
    if value['kind']!='tool' or value['answer'] is not None or type(value['calls']) is not list or not 1<=len(value['calls'])<=16:
        raise ValueError('invalid_tool_calls')
    calls=[]
    for call in value['calls']:
        if (type(call) is not dict or set(call)!={'name','arguments'}
                or type(call['name']) is not str or call['name'] not in allowed_tools
                or type(call['arguments']) is not dict):
            raise ValueError('unregistered_tool')
        original=json.dumps(call['arguments'],ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')
        calls.append(ToolCall(call['name'],original))
    return ToolTurn(None,None,tuple(calls))
