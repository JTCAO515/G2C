"""Explicit national.2 host baseline; the adapter's national.1 stays unchanged.

Only two original text spans are replaced. Their original offsets are captured
before inserting candidate text, so a candidate cannot manufacture a new match.
The authority clause following the reply span is never part of the text slot.
"""
from hashlib import sha256
from pathlib import Path

from runtime_adapter.configuration import source_c0
from runtime_adapter.contract import Pins,candidate,decode,digest,encode,require
from runtime_adapter.profiles import C0


REPLY_ANCHOR='reply is concise and useful'
C0_NATIONAL_V2={**C0,'example.clarification':REPLY_ANCHOR}


def render_national_intake(system,fragments):
    fragments=candidate(fragments)
    spans=[]
    for name in ('prompt.answer_style','example.clarification'):
        anchor=C0_NATIONAL_V2[name]
        require(system.count(anchor)==1,'NATIONAL_V2_BASELINE_ANCHOR_DRIFT')
        start=system.index(anchor)
        spans.append((start,start+len(anchor),fragments[name]))
    spans.sort()
    require(spans[0][1]<=spans[1][0],'NATIONAL_V2_ANCHOR_OVERLAP')
    for start,end,text in reversed(spans):system=system[:start]+text+system[end:]
    return system


def source_c0_national_v2(*,resource_root=None):
    source=source_c0(resource_root=resource_root)
    implementation=sha256(Path(__file__).read_bytes()).hexdigest()
    return {**source,'configuration':'C0-source-national.2','c0':C0_NATIONAL_V2,
        'candidate_id':digest(C0_NATIONAL_V2),
        'fragment_sha256':{name:sha256(text.encode()).hexdigest() for name,text in C0_NATIONAL_V2.items()},
        'host_files':{'backend/cj_api/runtime_text_slots.py':implementation},
        'system_prompt_sha256':digest(dict(base=source['system_prompt_sha256'],
            reply_anchor=REPLY_ANCHOR,national_v2_renderer_sha256=implementation)),
        'national_clarification_hook':'REPLY_ONLY_ORIGINAL_TEXT_SPAN',
        # A source manifest is not a deployed/eligible runtime card.
        'slot_host_status':dict.fromkeys(C0_NATIONAL_V2,'UNRUN')}


def freeze_national_v2(runtime_card,*,resource_root=None):
    require(type(runtime_card) is dict and set(runtime_card)=={'code_sha','image_digest','model'},
        'B_ACTUAL_RUNTIME_CARD_REQUIRED')
    source=source_c0_national_v2(resource_root=resource_root)
    require(encode(runtime_card['model'])==encode(source['model']),'B_MODEL_PROFILE_REQUIRES_EXPLICIT_REVISION')
    fields=('version','adapter_sha256','system_prompt_sha256','tool_schema_sha256',
        'tool_implementation_sha256','c0','task_version','task_sha256','score_version','score_sha256','preregistration_sha256')
    return Pins.from_dict({**{name:source[name] for name in fields},**decode(encode(runtime_card))})
