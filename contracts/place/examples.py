"""Executable SYNTHETIC consumer examples, not an alternate wire/API definition."""
from datetime import datetime, timedelta, timezone
import json
from cj_place import (
    ORIGIN, Config, Departure, Detail, FieldState, Outcome, Response, RouteQuery,
    Search, endpoint_from_place, execute, parse_response, prepare,
)


def examples():
    at = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
    config = Config(ORIGIN, 4096, 16384, 3, 60)  # explicitly synthetic limits

    def consume(query, payload):
        request = prepare(config, query, "synthetic-consumer", at)
        response = Response(request.binding_digest, request.origin, request.path, 200,
                            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                            at + timedelta(seconds=1))
        return parse_response(config, request, response, now=at + timedelta(seconds=2), evidence="synthetic")

    query = Search("合成地点", "合成城市", 1, 20)
    payload = {"status": "1", "info": "OK", "infocode": "10000", "count": "2", "pois": [
        {"id": "SYNTH_EAST", "name": "合成酒店", "address": "合成东路一号",
         "location": "116.1,39.1", "entr_location": "116.1001,39.1001"},
        {"id": "SYNTH_WEST", "name": "合成酒店", "address": [], "location": "116.2,39.2"},
    ]}
    search = consume(query, payload)
    assert search.outcome is Outcome.OK and len(search.places) == 2
    assert search.places[1].address_zh.state is FieldState.EMPTY_ARRAY
    assert search.places[0].official_name_en.state is FieldState.UNKNOWN
    origin = endpoint_from_place(search.places[0], "entrance")
    destination = endpoint_from_place(search.places[1], "poi_center")
    route_query = RouteQuery(origin, destination, "walking", Departure("at_query_time", None))
    route = consume(route_query, {"status": "1", "info": "OK", "infocode": "10000", "count": "1",
                                 "route": {"origin": origin.coordinate.raw,
                                           "destination": destination.coordinate.raw,
                                           "paths": [{"distance": "100", "duration": "90"}]}})
    assert route.routes[0].duration.value.unit == "s"
    assert route.routes[0].query.origin == origin
    assert route.source.evidence == "synthetic"
    wrong = consume(Detail("SYNTH_OTHER"), {**payload, "count": "1", "pois": payload["pois"][:1]})
    assert wrong.outcome is Outcome.BINDING_MISMATCH
    empty = consume(query, {**payload, "count": "0", "pois": []})
    assert empty.outcome is Outcome.NO_RESULTS
    limited = consume(query, {"status": "0", "infocode": "10044", "info": "synthetic quota"})
    assert limited.outcome is Outcome.RATE_LIMITED
    closed = execute(query, config=config)
    assert closed.outcome is Outcome.UNAVAILABLE
    return search, route, wrong, empty, limited, closed


if __name__ == "__main__":
    values = examples()
    print("6 synthetic consumer examples PASS; real provider/auth/usage UNRUN")
