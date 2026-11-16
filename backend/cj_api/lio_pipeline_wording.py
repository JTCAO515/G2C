"""Bounded final prose over generated stops; source and schedule stay code-owned."""
from copy import deepcopy
from cj_trip.rich_reasons import filter_reason_text
from .lio_pipeline_model import parse_wording


def wording_items(document,proposed_subjects):
    """Keep protected originals, hotel disclaimers and transport facts intact."""
    return tuple(dict(item_id=item['id'],text=item['text'],place=item['place'],tip=item['tip'])
        for item in document['items']if item['id']in proposed_subjects and item['kind']in ('sight','meal'))


def apply_wording(document,batches,*,facts):
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
        item.update(note=note,reason_refs=list(refs),tip=text['tip'])
    return value
