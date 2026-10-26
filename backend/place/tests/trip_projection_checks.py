"""Pure reference encoding checks for the review-only TRIP JSON candidate.

Not imported by product code, not a public decoder/admission/dispatch interface.
All fixtures are synthetic. No I/O beyond reading the local golden fixture.
"""
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import copy
import json
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

from cj_place import (Config, Coordinate, Departure, Detail, Endpoint, FieldState, Observed,
                      ORIGIN, Outcome, Place, Result, Route, RouteQuery, Search, Source, prepare)

VERSION = "CJ-PLACE-TRIP-JSON@0.1.0-rc.1"
FIXTURE = Path(__file__).resolve().parents[3] / "contracts/place/trip-projection-examples.json"


def encode_value(value):
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("aware_time_required")
        return {"iso8601": value.isoformat(timespec="microseconds"), "fold": value.fold}
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {item.name: encode_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, tuple):
        return [encode_value(item) for item in value]
    return value


def project_fixture(result):
    if result.routes:
        raise ValueError("route_results_out_of_scope")
    value = encode_value(result)
    del value["routes"]  # only an empty tuple may be omitted by this narrow profile
    value["query"]["kind"] = type(result.query).__name__
    return {"projection_version": VERSION, "result": value}


def examples():
    def obs(state, value=None):
        return Observed(state, value)
    place = Place("SYNTH_EAST", "合成酒店", obs(FieldState.PRESENT, "合成东路一号"),
                  obs(FieldState.PRESENT, Coordinate("116.100000,39.100000")),
                  obs(FieldState.PRESENT, Coordinate("116.100100,39.100100")),
                  obs(FieldState.MISSING), obs(FieldState.EMPTY_ARRAY), obs(FieldState.EMPTY_STRING),
                  obs(FieldState.NULL))
    other = Place("SYNTH_WEST", "合成酒店", obs(FieldState.INVALID),
                  obs(FieldState.UNKNOWN), obs(FieldState.MISSING), obs(FieldState.EMPTY_ARRAY),
                  obs(FieldState.MISSING), obs(FieldState.MISSING), obs(FieldState.MISSING))
    zone = ZoneInfo("America/New_York")
    config = Config(ORIGIN, 4096, 16384, 3, 60)  # synthetic test setup, never serialized as permission
    cases = []
    for fold, query in ((0, Search("合成酒店", "合成城市", 1, 20)), (1, Detail("SYNTH_EAST"))):
        start = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=fold)
        req = prepare(config, query, "synthetic-trip-projection", start)
        source = Source(ORIGIN + req.path, start, start.replace(second=1), req.request_ref,
                        req.binding_digest, "synthetic")
        result = Result(Outcome.OK, query, "page_results", source,
                        places=(place, other) if fold == 0 else (place,), provider_code="10000",
                        provider_count=2 if fold == 0 else 1)
        cases.append({"id": "synthetic-fold-" + str(fold), "projection": project_fixture(result),
                      "expected": "format_valid_consumer_adoption_deferred"})
    endpoint = Endpoint("SYNTH_EAST", Coordinate("116.100100,39.100100"), "entrance")
    route_query = RouteQuery(endpoint, Endpoint("SYNTH_WEST", Coordinate("116.2,39.2"), "poi_center"),
                             "walking", Departure("at_query_time", None))
    unavailable = Result(Outcome.UNAVAILABLE, route_query, "canonical_dispatch_not_connected")
    cases.append({"id": "unavailable-route-query-diagnostic", "projection": project_fixture(unavailable),
                  "expected": "format_valid_no_place_no_adoption"})
    negative = [
        {"id":"decimal-number-loss", "path":["result","places",0,"coordinate","value","longitude"], "value":116.1, "expected":"reject_decimal_number"},
        {"id":"coordinate-disagrees-with-raw", "path":["result","places",0,"coordinate","value","longitude"], "value":"116.2", "expected":"reject_coordinate_association"},
        {"id":"invented-wgs84", "path":["result","places",0,"coordinate","value","crs"], "value":"WGS84", "expected":"reject_crs"},
        {"id":"absent-field-zero-filled", "path":["result","places",0,"exit_coordinate","value"], "value":{"raw":"0,0","longitude":"0","latitude":"0","crs":"GCJ-02"}, "expected":"reject_nonpresent_value"},
        {"id":"timestamp-without-offset", "path":["result","source","query_started_at","iso8601"], "value":"2026-11-01T01:30:00.000000", "expected":"reject_naive_time"},
        {"id":"invalid-fold", "path":["result","source","received_at","fold"], "value":2, "expected":"reject_fold"},
        {"id":"promoted-provider-evidence", "path":["result","source","evidence"], "value":"verified_provider", "expected":"reject_evidence_enum"},
        {"id":"client-ttl-claim", "path":["result","max_age_seconds"], "value":999999999, "expected":"reject_extra_field_no_freshness_grant"},
        {"id":"invented-acceptance", "path":["result","user_accepted"], "value":True, "expected":"reject_extra_field_no_acceptance_grant"},
    ]
    return {"fixture_kind":"synthetic_only_not_for_trip_adoption", "positive":cases, "negative":negative}


class ProjectionChecks(unittest.TestCase):
    def test_nonempty_route_results_cannot_be_silently_dropped(self):
        point = Endpoint("SYNTH_EAST", Coordinate("116.1,39.1"), "poi_center")
        query = RouteQuery(point, point, "walking", Departure("at_query_time", None))
        route = Route(query, Observed(FieldState.UNKNOWN), Observed(FieldState.UNKNOWN))
        with self.assertRaisesRegex(ValueError, "route_results_out_of_scope"):
            project_fixture(Result(Outcome.OK, query, "route_estimates", routes=(route,)))

    def test_golden_matches_existing_types_and_json_roundtrip(self):
        actual = examples()
        self.assertEqual(json.loads(FIXTURE.read_text()), actual)
        self.assertEqual(json.loads(json.dumps(actual, ensure_ascii=False, allow_nan=False)), actual)

    def test_decimal_text_preserves_original_coordinate_association(self):
        coord = examples()["positive"][0]["projection"]["result"]["places"][0]["coordinate"]["value"]
        native = Coordinate(coord["raw"])
        self.assertEqual(coord["longitude"], str(native.longitude))
        self.assertEqual(coord["latitude"], str(native.latitude))
        self.assertEqual(coord["longitude"], "116.100000")
        self.assertEqual(coord["crs"], native.crs)

    def test_offsets_and_folds_preserve_distinct_instants(self):
        def decode(value):
            return datetime.fromisoformat(value["iso8601"]).replace(fold=value["fold"])
        values = [case["projection"]["result"]["source"]["query_started_at"] for case in examples()["positive"][:2]]
        first, second = map(decode, values)
        self.assertEqual((second.astimezone(timezone.utc)-first.astimezone(timezone.utc)).total_seconds(), 3600)
        self.assertEqual([v["fold"] for v in values], [0, 1])
        self.assertEqual(first.utcoffset().total_seconds(), -14400)
        self.assertEqual(second.utcoffset().total_seconds(), -18000)

    def test_observed_states_and_no_client_freshness_or_acceptance_field(self):
        value = examples()["positive"][0]["projection"]["result"]
        states = set()
        for place in value["places"]:
            for item in place.values():
                if isinstance(item, dict) and "state" in item:
                    states.add(item["state"])
                    self.assertEqual(item["state"] == "present", item["value"] is not None)
        self.assertEqual(states, {state.value for state in FieldState})
        self.assertNotIn("max_age_seconds", value)
        self.assertNotIn("user_accepted", value)
        self.assertEqual(set(value), {"contract_version","outcome","reason","query","source","places","provider_code","provider_count"})

    def test_negative_vectors_identify_exact_format_or_authority_violation(self):
        data = examples()
        cases = {}
        for case in data["negative"]:
            value = copy.deepcopy(data["positive"][0]["projection"])
            target = value
            for key in case["path"][:-1]:
                target = target[key]
            target[case["path"][-1]] = case["value"]
            cases[case["id"]] = value["result"]
        self.assertIsInstance(cases["decimal-number-loss"]["places"][0]["coordinate"]["value"]["longitude"], float)
        coord = cases["coordinate-disagrees-with-raw"]["places"][0]["coordinate"]["value"]
        self.assertNotEqual(coord["longitude"], str(Coordinate(coord["raw"]).longitude))
        self.assertNotEqual(cases["invented-wgs84"]["places"][0]["coordinate"]["value"]["crs"], "GCJ-02")
        self.assertIsNotNone(cases["absent-field-zero-filled"]["places"][0]["exit_coordinate"]["value"])
        self.assertIsNone(datetime.fromisoformat(cases["timestamp-without-offset"]["source"]["query_started_at"]["iso8601"]).tzinfo)
        self.assertNotIn(cases["invalid-fold"]["source"]["received_at"]["fold"], (0,1))
        self.assertNotIn(cases["promoted-provider-evidence"]["source"]["evidence"], ("synthetic","unverified_bytes"))
        self.assertIn("max_age_seconds", cases["client-ttl-claim"])
        self.assertIn("user_accepted", cases["invented-acceptance"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
