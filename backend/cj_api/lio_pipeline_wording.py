"""Bounded final prose over generated stops; source and schedule stay code-owned."""
from copy import deepcopy
import re
from cj_trip.rich_reasons import filter_reason_text
from cj_trip.rich_reasons import ProfileFact
from cj_message.lio_context import display_answer
from pypinyin import lazy_pinyin
from .lio_pipeline_model import parse_wording
from .lio_exploration_policy import _ACTION_CLAIM,_CONTROL
from .lio_profile_cards import value_text

_TOOL_METADATA=re.compile(r'(?<![A-Za-z0-9_])tool_call_id(?![A-Za-z0-9_])',re.I)


def profile_facts(capture,locale):
    """Format accepted values without changing their full source or states."""
    facts=[]
    han=lambda value:any('\u3400'<=char<='\u9fff'for char in value)
    for row in capture.profile.profile['factors']:
        key,state,value=row['factor_key'],row['state'],row['value']
        display=value_text(key,value,state,locale)
        if display=='':display='未指定'if locale=='zh'else'None specified'
        if key=='city'and locale=='en'and han(str(value)):
            english=display.replace(value,'').strip(' ()（）')
            display=(english or' '.join(lazy_pinyin(value)))+' ('+value+')'
        safe=display_answer(display,locale)
        if safe is None:safe='该偏好暂无法显示'if locale=='zh'else'This preference cannot be displayed'
        if len(safe)>500:safe=safe[:499]+'…' # Presentation only; the source is intact.
        facts.append(ProfileFact(key,state,safe))
    return tuple(facts)


def wording_items(document,proposed_subjects):
    """Keep protected originals, hotel disclaimers and transport facts intact."""
    return tuple(dict(item_id=item['id'],text=item['text'],place=item['place'],tip=item['tip'])
        for item in document['items']if item['id']in proposed_subjects and item['kind']in ('sight','meal'))


def _public(value,locale):
    return value is None or (_ACTION_CLAIM.search(value.replace('’',"'"))is None
        and _CONTROL.search(value)is None and _TOOL_METADATA.search(value)is None
        and display_answer(value,locale)==value)


def apply_wording(document,batches,*,facts,locale):
    """Parse every complete response before projecting any model prose.

    The exact batches are host-owned. Only known/Memory profile keys may support
    reasons, and no supplied tip means no tip can be invented. Final source,
    date checks and the sole writer still validate the complete candidate.
    """
    allowed={fact.key for fact in facts if fact.state in ('known','memory')}
    patches={}
    for items,raw in batches:
        patches.update(parse_wording(raw,items,allowed_reason_keys=allowed))
    value=deepcopy(document)
    for item in value['items']:
        if item['id']not in patches:continue
        text=patches[item['id']]
        note,refs,_=filter_reason_text(text['note'],text['reason_refs'],facts)
        # HK run 4fb238dc (2026-11-26): the schema admits "" for a reason; an empty or blank
        # note fails the saved itinerary's bounded-text check, so it means no reason.
        if not _public(note,locale)or note is not None and not note.strip():note,refs=None,()
        tip=text['tip']if _public(text['tip'],locale)and(text['tip']is None or text['tip'].strip())else None
        item.update(note=note,reason_refs=list(refs),tip=tip)
    return value
