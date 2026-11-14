"""Bounded skeleton/wording data, used through the native4 registered model.

The host supplies accepted profile facts and exact code recipes/item IDs. Model
text cannot create source records, change the recipe or authorize publication.
"""
from dataclasses import asdict

from pydantic import ValidationError
from cj_message.lio_pipeline_schema import Wording
from cj_needs.domain import decode,InvalidInput

SKELETON_SYSTEM=(
    'Propose one complete single-city itinerary as JSON only, using the supplied schema. '
    'Copy all code-selected day ordinals, sight counts and meal periods exactly; do not omit days. '
    'Suggest one literal Chinese/English place name per stop, never keyword batches. '
    'First/last light-day stops must be near the proposed lodging area. '
    'Include the lodging area and 2 or 3 hotel suggestions, with no prices or reservations. '
    'Names and areas are unconfirmed proposals, not sourced facts. Never add coordinates, '
    'POI IDs, official opening times, dates, eligibility, booking or saved claims. '
    'Keep names concise so the entire object fits the output limit; no prose or fences.')
WORDING_SYSTEM=(
    'Rewrite only the supplied final itinerary items as JSON using the supplied schema. '
    'Return each supplied item_id exactly once, no new or missing items. '
    'For each give one concise reason sentence and one concise tip, or null if unsupported. '
    'reason_refs may only use the supplied known/memory factor keys supporting that reason. '
    'Do not describe inferred/default factors as the traveler\'s own preference. '
    'Tips may only rephrase the supplied sourced tip; without one use null. '
    'Do not add venue, transport, immigration, booking, saved, price or opening claims. '
    'Use the supplied locale; English place/food names must include their Chinese names. '
    'No internal identifiers in public wording, no prose outside JSON.')


class WordingUnavailable(ValueError):pass


def skeleton_data(effective,expected,*,locale):
    return dict(locale=locale,effective=effective,days=[asdict(recipe)for recipe in expected])


def wording_batches(items):
    """At most four deterministic batches; no hidden per-day model fan-out."""
    width=max(1,(len(items)+3)//4)
    return tuple(tuple(items[start:start+width])for start in range(0,len(items),width))


def parse_wording(raw,items,*,allowed_reason_keys):
    """Validate this exact batch; C still filters reasons after final wording."""
    try:value=Wording.model_validate(decode(raw))
    except(ValidationError,InvalidInput)as error:
        raise WordingUnavailable('complete typed wording required')from error
    expected={item['item_id']:item for item in items}
    rows={row.item_id:row for row in value.items}
    if len(rows)!=len(value.items)or rows.keys()!=expected.keys():
        raise WordingUnavailable('exact wording batch item set required')
    projected={}
    for key,row in rows.items():
        if len(set(row.reason_refs))!=len(row.reason_refs)or not set(row.reason_refs)<=allowed_reason_keys:
            raise WordingUnavailable('only existing known/memory reason factors allowed')
        # Rewording a tip does not authorize new facts: with no sourced tip the
        # host retains null, regardless of what the model proposed.
        projected[key]=dict(note=row.reason,reason_refs=list(row.reason_refs),
                            tip=row.tip if expected[key]['tip']is not None else None)
    return projected
