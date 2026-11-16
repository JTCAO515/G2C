"""Bounded final prose over generated stops; source and schedule stay code-owned."""
from copy import deepcopy
import re
from cj_trip.rich_reasons import filter_reason_text
from cj_message.lio_context import display_answer
from .lio_pipeline_model import parse_wording
from .lio_exploration_policy import _ACTION_CLAIM,_CONTROL

_TOOL_METADATA=re.compile(r'(?<![A-Za-z0-9_])tool_call_id(?![A-Za-z0-9_])',re.I)


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
        if not _public(note,locale):note,refs=None,()
        tip=text['tip']if _public(text['tip'],locale)else None
        item.update(note=note,reason_refs=list(refs),tip=tip)
    return value
