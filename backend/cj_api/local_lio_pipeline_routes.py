"""Original routes for frozen adjacency; no scheduling or publication grant.

The caller preflights the complete graph and freezes ordering before dispatch.
Only a definite original unavailable transit result permits one taxi alternative.
All attempts use the same PipelineCalls allocation and provider source reader.
UNKNOWN propagates; neither this result nor its capture authorizes publication.
"""
import json

from .local_lio_pipeline_places import route_calls,taxi_fallback_calls,apply_routes


def retrieve_routes(document,*,calls,city,origin,providers):
    initial,references=route_calls(document,city=city,origin=origin,sources=providers)
    # These are code-owned registered results, already parsed and receipt-bound
    # by the provider adapter. Final Source4 publication still holds/rereads them.
    replies={packet.argument.request_ref:json.loads(raw)
        for packet,raw in zip(initial,calls.parallel(initial),strict=True)}
    alternative,references=taxi_fallback_calls(initial,references,replies)
    replies.update((packet.argument.request_ref,json.loads(raw))
        for packet,raw in zip(alternative,calls.parallel(alternative),strict=True))
    captured=providers.capture(origin.binding)
    return apply_routes(document,references,replies),captured
