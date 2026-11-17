"""Original routes for frozen adjacency; no scheduling or publication grant.

The caller preflights the complete graph and freezes ordering before dispatch.
Only a definite original unavailable transit result permits one taxi alternative.
All attempts use the same PipelineCalls allocation and provider source reader.
UNKNOWN propagates; neither this result nor its capture authorizes publication.
"""
import json

from .local_lio_pipeline_places import route_calls,taxi_fallback_calls,apply_routes


def _within_budget(packets,before,proposed,remaining):
    selected=packets[:remaining]
    requested={packet.argument.request_ref for packet in selected}
    # An unrequested route is not an unavailable supplier result. Retain the
    # original unconfirmed leg (or prior observed attempt), with no new source.
    return selected,{pair:reference if reference in requested else before[pair]
        for pair,reference in proposed.items()}


def retrieve_routes(document,*,calls,city,origin,providers):
    initial,references=route_calls(document,city=city,origin=origin,sources=providers)
    initial,references=_within_budget(initial,{pair:None for pair in references},references,calls.gaode_slots_left)
    # These are code-owned registered results, already parsed and receipt-bound
    # by the provider adapter. Final Source4 publication still holds/rereads them.
    replies={packet.argument.request_ref:json.loads(raw)
        for packet,raw in zip(initial,calls.parallel(initial),strict=True)}
    alternative,proposed=taxi_fallback_calls(initial,references,replies)
    alternative,references=_within_budget(alternative,references,proposed,calls.gaode_slots_left)
    replies.update((packet.argument.request_ref,json.loads(raw))
        for packet,raw in zip(alternative,calls.parallel(alternative),strict=True))
    captured=providers.capture(origin.binding)
    return apply_routes(document,references,replies),captured
