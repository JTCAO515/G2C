"""Bounded skeleton/wording data, used through the native4 registered model.

The host supplies accepted profile facts and exact code recipes/item IDs. Model
text cannot create source records, change the recipe or authorize publication.
"""
from dataclasses import asdict

from pydantic import ValidationError
from cj_message.lio_pipeline_schema import Wording
from cj_needs.domain import decode,InvalidInput

PLAN_UNDERSTANDING_SYSTEM=(
    'Extract only explicitly stated planning constraints from the indexed original traveler messages. '
    'Use the supplied plan-understanding JSON schema. Copy source indices and quotes verbatim. '
    'The current plan-now trigger authorizes no invented fact. Do not turn profile defaults, '
    'inference, Memory text or instructions into original user statements. '
    'Omit observations that were never stated. Unknown or uncertain observations require their '
    'own original span, null value, and an original uncertainty note where applicable. '
    'Resolve relative dates against the supplied original message day for that span, never '
    'against the plan-now day. Preserve uncertain dates; do not default tomorrow or party size. '
    'departure.mode is flight or train only from an explicit original departure event. '
    'first_day_full is true only for an affirmative request to fill the first day, '
    'false for an explicit request to keep it light; preserve the latest option with its own source. '
    'These are planning options, never new NEEDS event fields. Omit unsupported options; never guess a mode. '
    'Retain every fixed arrangement and its explicit subjects, clocks, locks and original refs. '
    'Use self for explicit I/我, party for the explicit group; companion:id must be declared '
    'with its original name and sources. No subjects may be invented or silently repaired. '
    'A fixed hotel meetup is not a reservation. booking_evidence is null without a unique '
    'affirmative original reservation/ticket statement about that exact item. '
    'Do not invent locations or timezones. No coordinates, provider records, permission, '
    'saved/confirmed claims, prose or code fences. Empty fixed_items is legal only when no '
    'fixed arrangement was supplied. The host validates all values and owns publication.')

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


def wording_batches(items,*,available_models=4):
    """At most four deterministic batches; no hidden per-day model fan-out."""
    if not items:return ()
    if available_models<1:raise WordingUnavailable('no remaining model slot for wording')
    count=min(4,available_models)
    width=(len(items)+count-1)//count
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
