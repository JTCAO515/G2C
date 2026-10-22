"""All data here is SYNTHETIC, not returned by a provider or a real city search."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import io
import json
from contextlib import redirect_stderr, redirect_stdout
import unittest

from cj_place import (
    ORIGIN, Config, Coordinate, Departure, Detail, Endpoint, FieldState, Outcome,
    PreparationError, Response, RouteQuery, Search, execute, parse_response, prepare, endpoint_from_place,
)
from cj_place.synthetic import run_synthetic

AT = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
CONFIG = Config(ORIGIN, 4096, 65536, 3, 60)  # fixture limits, NOT product defaults
SEARCH = Search("合成同名酒店", "合成城市", 1, 20)


def poi(pid="SYNTH_A", **extra):
    return dict(id=pid, name="合成同名酒店", address="合成路一号", location="116.1,39.1", **extra)


def pois(*items):
    return dict(status="1", info="OK", infocode="10000", count=str(len(items)), pois=list(items))


def route_query(mode="walking"):
    return RouteQuery(Endpoint("SYNTH_A", Coordinate("116.1,39.1"), "entrance"),
                      Endpoint("SYNTH_B", Coordinate("116.2,39.2"), "poi_center"),
                      mode, Departure("at_query_time", None))


def route_body(**path):
    return dict(status="1", info="OK", infocode="10000", count="1",
                route=dict(origin="116.100000,39.100000", destination="116.2,39.2",
                           paths=[dict(distance="123.5", duration="60", **path)]))


def response(request, body, status=200, received=None):
    raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
    return Response(request.binding_digest, request.origin, request.path, status, raw,
                    received or request.started_at + timedelta(seconds=1))


def parse(body, query=SEARCH, *, config=CONFIG, **kwargs):
    request = prepare(config, query, "synthetic-request", AT)
    return parse_response(config, request, response(request, body, **kwargs), now=AT + timedelta(seconds=2))


class PlaceTests(unittest.TestCase):
    def test_search_keeps_same_name_branches_and_entrances(self):
        a = poi(entr_location="116.1001,39.1001", parent="SYNTH_PARENT", navi_poiid="SYNTH_NAV")
        b = poi("SYNTH_B", entr_location="116.1002,39.1002")
        result = parse(pois(a, b))
        self.assertEqual(result.outcome, Outcome.OK)
        self.assertEqual([p.provider_id for p in result.places], ["SYNTH_A", "SYNTH_B"])
        first, second = result.places
        self.assertEqual(first.name_zh, second.name_zh)
        self.assertNotEqual(first.entrance_coordinate.value, second.entrance_coordinate.value)
        self.assertEqual(first.parent_id.value, "SYNTH_PARENT")
        self.assertEqual(first.navigation_id.value, "SYNTH_NAV")
        self.assertEqual(first.coordinate.value.crs, "GCJ-02")
        self.assertEqual(result.source.query_started_at, AT)
        self.assertEqual(result.source.provider_updated_at, None)
        self.assertEqual(result.source.evidence, "unverified_bytes")

    def test_official_english_is_unknown_and_unicode_unmodified(self):
        item = poi()
        item.update(name="合成𠮷 café e\u0301 🏨", address="合成Ａ座  １２号")
        result = parse(pois(item))
        self.assertEqual(result.places[0].name_zh, item["name"])
        self.assertEqual(result.places[0].address_zh.value, item["address"])
        self.assertEqual(result.places[0].official_name_en.state, FieldState.UNKNOWN)
        self.assertIsNone(result.places[0].official_address_en.value)

    def test_missing_array_null_empty_invalid_are_distinct(self):
        for key, attr in (("address", "address_zh"), ("location", "coordinate"), ("entr_location", "entrance_coordinate")):
            for value, expected in (([], FieldState.EMPTY_ARRAY), ("", FieldState.EMPTY_STRING),
                                    (None, FieldState.NULL), (0, FieldState.INVALID),
                                    (["x"], FieldState.INVALID), ({}, FieldState.INVALID)):
                with self.subTest(key=key, value=value):
                    item = poi()
                    item[key] = value
                    observed = getattr(parse(pois(item)).places[0], attr)
                    self.assertEqual(observed.state, expected)
                    self.assertIsNone(observed.value)
            item = poi()
            item.pop(key, None)
            self.assertEqual(getattr(parse(pois(item)).places[0], attr).state, FieldState.MISSING)

    def test_invalid_coordinates_never_zero_filled(self):
        for value in ("0", "181,39", "116,91", "NaN,39", "1e2,39", "116,39,40", "116, 39", "１１６,３９", True):
            with self.subTest(value=value):
                item = poi()
                item["location"] = value
                result = parse(pois(item))
                self.assertEqual(result.places[0].coordinate.state, FieldState.INVALID)
                self.assertIsNone(result.places[0].coordinate.value)
        item = poi()
        item["location"] = "0,0"
        actual_zero = parse(pois(item)).places[0].coordinate
        self.assertEqual(actual_zero.state, FieldState.PRESENT)
        self.assertEqual(actual_zero.value.longitude, Decimal(0))

    def test_empty_success_is_not_failure_and_missing_pois_is_invalid(self):
        self.assertEqual(parse(pois()).outcome, Outcome.NO_RESULTS)
        for value in (None, {}, 0, ""):
            body = pois()
            body["pois"] = value
            self.assertEqual(parse(body).outcome, Outcome.INVALID_RESPONSE)
        body = pois()
        del body["pois"]
        self.assertEqual(parse(body).outcome, Outcome.INVALID_RESPONSE)

    def test_count_and_list_consistency(self):
        for value in (None, [], 0, True, "-1", "1.0", ""):
            body = pois(poi())
            body["count"] = value
            self.assertEqual(parse(body).outcome, Outcome.INVALID_RESPONSE)
        body = pois(poi())
        body["count"] = "0"
        self.assertEqual(parse(body).outcome, Outcome.INVALID_RESPONSE)
        body = pois()
        body["count"] = "2"
        result = parse(body, replace(SEARCH, page=2))
        self.assertEqual(result.reason, "empty_page")
        self.assertEqual(result.provider_count, 2)

    def test_detail_requires_exact_identity(self):
        good = parse(pois(poi()), Detail("SYNTH_A"))
        self.assertEqual(good.outcome, Outcome.OK)
        self.assertEqual(parse(pois(poi("SYNTH_B")), Detail("SYNTH_A")).outcome, Outcome.BINDING_MISMATCH)
        self.assertEqual(parse(pois(), Detail("SYNTH_A")).outcome, Outcome.NO_RESULTS)
        self.assertEqual(parse(pois(poi(), poi("SYNTH_B")), Detail("SYNTH_A")).outcome, Outcome.INVALID_RESPONSE)

    def test_endpoint_projection_preserves_identity_without_fallback(self):
        item = poi(entr_location="116.11,39.11")
        place = parse(pois(item)).places[0]
        endpoint = endpoint_from_place(place, "entrance")
        self.assertEqual(endpoint.provider_id, place.provider_id)
        self.assertEqual(endpoint.coordinate.raw, "116.11,39.11")
        self.assertEqual(endpoint.coordinate_role, "entrance")
        with self.assertRaisesRegex(ValueError, "coordinate_unavailable"):
            endpoint_from_place(place, "exit")
        for value in ([], None, "bad"):
            item["entr_location"] = value
            with self.assertRaisesRegex(ValueError, "coordinate_unavailable"):
                endpoint_from_place(parse(pois(item)).places[0], "entrance")

    def test_duplicate_identity_and_missing_name_are_rejected(self):
        self.assertEqual(parse(pois(poi(), poi())).outcome, Outcome.INVALID_RESPONSE)
        for key in ("id", "name"):
            for value in (None, "", [], 0):
                item = poi()
                item[key] = value
                self.assertEqual(parse(pois(item)).outcome, Outcome.INVALID_RESPONSE)


class RequestAndRouteTests(unittest.TestCase):
    def test_documented_paths_and_parameters(self):
        request = prepare(CONFIG, SEARCH, "synthetic-request", AT)
        self.assertEqual(request.path, "/v3/place/text")
        self.assertEqual(dict(request.params)["citylimit"], "true")
        self.assertEqual(dict(request.params)["children"], "0")
        self.assertNotIn("key", dict(request.params))
        detail = prepare(CONFIG, Detail("SYNTH_A"), "synthetic-request", AT)
        self.assertEqual(dict(detail.params)["id"], "SYNTH_A")
        for mode, id_key in (("walking", "origin_id"), ("driving", "originid")):
            req = prepare(CONFIG, route_query(mode), "synthetic-request", AT)
            self.assertEqual(req.path, "/v3/direction/" + mode)
            self.assertEqual(dict(req.params)[id_key], "SYNTH_A")
            self.assertNotIn("departure", dict(req.params))

    def test_route_units_identity_role_and_original_coordinate_text(self):
        for mode in ("walking", "driving"):
            query = route_query(mode)
            result = parse(route_body(), query)
            self.assertEqual(result.outcome, Outcome.OK)
            route = result.routes[0]
            self.assertEqual(route.query, query)
            self.assertEqual(route.distance.value.raw, "123.5")
            self.assertEqual(route.distance.value.unit, "m")
            self.assertEqual(route.duration.value.value, 60)
            self.assertEqual(route.duration.value.unit, "s")
            self.assertEqual(route.query.origin.coordinate_role, "entrance")
            self.assertEqual(route.query.origin.coordinate.raw, "116.1,39.1")
            self.assertFalse(route.future_guaranteed)

    def test_route_wrong_swapped_missing_coordinate_is_not_accepted(self):
        for key in ("origin", "destination"):
            body = route_body()
            body["route"][key] = "116.3,39.3"
            self.assertEqual(parse(body, route_query()).outcome, Outcome.BINDING_MISMATCH)
            body["route"][key] = []
            self.assertEqual(parse(body, route_query()).outcome, Outcome.INVALID_RESPONSE)

    def test_route_quantity_zero_is_present_missing_is_not_zero(self):
        for value, expected in (("0", FieldState.PRESENT), ([], FieldState.EMPTY_ARRAY),
                                (None, FieldState.NULL), (0, FieldState.INVALID),
                                ("-1", FieldState.INVALID), ("NaN", FieldState.INVALID)):
            body = route_body()
            body["route"]["paths"][0]["duration"] = value
            field = parse(body, route_query()).routes[0].duration
            self.assertEqual(field.state, expected)
            if value == "0":
                self.assertEqual(field.value.value, 0)
            else:
                self.assertIsNone(field.value)
        body = route_body()
        del body["route"]["paths"][0]["distance"]
        self.assertEqual(parse(body, route_query()).routes[0].distance.state, FieldState.MISSING)

    def test_no_routes_and_invalid_route_have_different_results(self):
        body = route_body()
        body["route"]["paths"] = []
        body["count"] = "0"
        self.assertEqual(parse(body, route_query()).outcome, Outcome.NO_RESULTS)
        for value in (None, [], {}):
            body["route"] = value
            self.assertEqual(parse(body, route_query()).outcome, Outcome.INVALID_RESPONSE)

    def test_future_and_past_specific_departure_are_not_downgraded(self):
        for delta in (-1, 1, 100):
            query = replace(route_query(), departure=Departure("specified_time", AT + timedelta(days=delta)))
            with self.assertRaisesRegex(PreparationError, "departure_not_supported"):
                prepare(CONFIG, query, "synthetic-request", AT)

    def test_input_bounds_and_exact_precision(self):
        for keyword in ("", "a|b", "x" * 257, "a\n", "\ud800"):
            with self.assertRaises(ValueError):
                Search(keyword, "合成城市", 1, 20)
        for page, size in ((0, 20), (1, 0), (1, 26), (11, 20), (True, 20)):
            with self.assertRaises(ValueError):
                Search("合成", "合成", page, size)
        for pid in ("a|b", "../x", "", "a&key=secret"):
            with self.assertRaises(ValueError):
                Detail(pid)
        with self.assertRaises(ValueError):
            Endpoint("SYNTH_A", Coordinate("116.1234567,39"), "entrance")
        with self.assertRaises(ValueError):
            Departure("specified_time", AT.replace(tzinfo=None))

    def test_host_limits_config_and_request_size(self):
        for host in ("http://restapi.amap.com", ORIGIN + "/", ORIGIN + ".evil", "https://user@restapi.amap.com"):
            with self.assertRaises(ValueError):
                replace(CONFIG, origin=host)
        for key in ("timeout_seconds", "max_age_seconds"):
            for value in (0, -1, float("nan"), float("inf"), True):
                with self.assertRaises(ValueError):
                    replace(CONFIG, **{key: value})
        for value in (0, True, -1, 1.5):
            with self.assertRaises(ValueError):
                replace(CONFIG, max_response_bytes=value)
        with self.assertRaisesRegex(PreparationError, "configuration_required"):
            prepare(None, SEARCH, "synthetic-request", AT)
        with self.assertRaisesRegex(PreparationError, "request_too_large"):
            prepare(replace(CONFIG, max_request_bytes=10), SEARCH, "synthetic-request", AT)

    def test_binding_covers_query_role_mode_ids_limits_and_time(self):
        query = route_query()
        original = prepare(CONFIG, query, "synthetic-request", AT)
        variations = (
            replace(query, mode="driving"),
            replace(query, origin=replace(query.origin, provider_id="SYNTH_OTHER")),
            replace(query, origin=replace(query.origin, coordinate_role="poi_center")),
            replace(query, destination=replace(query.destination, coordinate=Coordinate("116.21,39.2"))),
        )
        for altered in variations:
            self.assertNotEqual(prepare(CONFIG, altered, "synthetic-request", AT).binding_digest, original.binding_digest)
        self.assertNotEqual(prepare(CONFIG, query, "other-request", AT).binding_digest, original.binding_digest)
        self.assertNotEqual(prepare(CONFIG, query, "synthetic-request", AT + timedelta(seconds=1)).binding_digest, original.binding_digest)
        self.assertNotEqual(prepare(replace(CONFIG, max_age_seconds=61), query, "synthetic-request", AT).binding_digest, original.binding_digest)


class FailureTests(unittest.TestCase):
    def test_documented_rate_limit_and_provider_error_codes(self):
        for code in ("10003", "10004", "10010", "10014", "10015", "10019", "10020", "10021", "10029", "10044", "10045"):
            result = parse(dict(status="0", infocode=code, info="ignored sensitive prose"))
            self.assertEqual(result.outcome, Outcome.RATE_LIMITED)
            self.assertEqual(result.provider_code, code)
        for code in ("10001", "10002", "10016", "20801", "20802", "20003", "40000", "99999"):
            result = parse(dict(status="0", infocode=code, info="ignored sensitive prose"))
            self.assertEqual(result.outcome, Outcome.PROVIDER_ERROR)
            self.assertNotIn("ignored sensitive", repr(result))

    def test_status_failure_never_becomes_empty_success(self):
        for status, code in ((0, "10000"), (1, "10000"), (True, "10000"),
                             ("0", "10000"), ("1", "10003"), ("1", None), ("2", "10000")):
            body = pois()
            body.update(status=status, infocode=code)
            self.assertEqual(parse(body).outcome, Outcome.INVALID_RESPONSE)

    def test_http_failures_and_redirects_are_not_followed(self):
        self.assertEqual(parse(b"ignored", status=429).outcome, Outcome.RATE_LIMITED)
        for code in (301, 302, 307, 308, 401, 403, 404, 500, 503):
            self.assertEqual(parse(b"ignored", status=code).outcome, Outcome.PROVIDER_ERROR)

    def test_malformed_duplicate_keys_and_non_json(self):
        for body in (b"", b"[]", b"null", b"<html>", b"\xff", b'{"status":"1","status":"0"}',
                     b'{"a":{"id":1,"id":2}}', b'{"n":NaN}', b'{"n":Infinity}',
                     b'{"a":"\\ud800"}', b'{"a":"\\udfff"}', b'{} trailing', b'[' * 1500):
            with self.subTest(body=body[:50]):
                self.assertEqual(parse(body).outcome, Outcome.INVALID_RESPONSE)
        nested = 0
        for _ in range(40):
            nested = [nested]
        body = pois()
        body["unknown"] = nested
        self.assertEqual(parse(body).outcome, Outcome.INVALID_RESPONSE)

    def test_oversize_is_rejected_before_decode(self):
        self.assertEqual(parse(b"x" * 65537).outcome, Outcome.INVALID_RESPONSE)
        self.assertEqual(parse(b"x" * 65537, status=429).reason, "response_bytes_limit")

    def test_extreme_json_exponent_is_invalid_without_parser_exception(self):
        self.assertEqual(parse(b'{"unknown":1e9999999999999999999999999999999999999999999}').outcome,
                         Outcome.INVALID_RESPONSE)

    def test_wrong_envelope_and_tampered_preparation(self):
        request = prepare(CONFIG, SEARCH, "synthetic-request", AT)
        good = response(request, pois(poi()))
        for key, value in (("binding_digest", "0" * 64), ("origin", ORIGIN + ".evil"),
                           ("path", "/v3/place/detail")):
            result = parse_response(CONFIG, request, replace(good, **{key: value}), now=AT + timedelta(seconds=2))
            self.assertEqual(result.outcome, Outcome.BINDING_MISMATCH)
        altered = replace(request, params=(("key", "must-not-dispatch"),))
        self.assertEqual(parse_response(CONFIG, altered, good, now=AT + timedelta(seconds=2)).outcome, Outcome.BINDING_MISMATCH)

    def test_stale_timeout_and_invalid_time(self):
        request = prepare(CONFIG, SEARCH, "synthetic-request", AT)
        good = response(request, pois())
        self.assertEqual(parse_response(CONFIG, request, good, now=AT + timedelta(seconds=61)).outcome, Outcome.STALE)
        self.assertEqual(parse_response(CONFIG, request, good, now=AT).outcome, Outcome.INVALID_RESPONSE)
        late = replace(good, received_at=AT + timedelta(seconds=4))
        self.assertEqual(parse_response(CONFIG, request, late, now=AT + timedelta(seconds=4)).outcome, Outcome.UNKNOWN)
        naive = replace(good, received_at=AT.replace(tzinfo=None))
        self.assertEqual(parse_response(CONFIG, request, naive, now=AT).outcome, Outcome.INVALID_RESPONSE)

    def test_production_entry_is_closed_with_or_without_configuration(self):
        self.assertEqual(execute(SEARCH).reason, "configuration_required")
        self.assertEqual(execute(SEARCH, config=CONFIG).reason, "canonical_dispatch_not_connected")
        self.assertEqual(execute(SEARCH, config=CONFIG).outcome, Outcome.UNAVAILABLE)


class SyntheticTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_injected_response_not_authenticated_or_real(self):
        calls = []
        async def fixture(request):
            calls.append(request)
            return response(request, pois(poi()), received=datetime.now(timezone.utc))
        result = await run_synthetic(CONFIG, SEARCH, request_ref="synthetic-request", transport=fixture)
        self.assertEqual(result.outcome, Outcome.OK)
        self.assertEqual(result.source.evidence, "synthetic")
        self.assertEqual(len(calls), 1)

    async def test_unknown_transport_no_retry_no_logs_or_exception_body(self):
        calls = []
        async def fixture(request):
            calls.append(request)
            raise OSError("synthetic-secret-must-not-appear")
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            result = await run_synthetic(CONFIG, SEARCH, request_ref="synthetic-request", transport=fixture)
        self.assertEqual(result.outcome, Outcome.UNKNOWN)
        self.assertEqual(len(calls), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("synthetic-secret", repr(result))

    async def test_timeout_cancels_cooperative_fixture_without_retry(self):
        stopped = []
        async def fixture(request):
            try:
                await asyncio.sleep(1)
            finally:
                stopped.append(True)
        result = await run_synthetic(replace(CONFIG, timeout_seconds=0.01), SEARCH,
                                     request_ref="synthetic-request", transport=fixture)
        self.assertEqual(result.outcome, Outcome.UNKNOWN)
        self.assertEqual(stopped, [True])

    async def test_missing_configuration_and_future_do_not_invoke_transport(self):
        calls = []
        async def fixture(request):
            calls.append(request)
            raise AssertionError("should not run")
        self.assertEqual((await run_synthetic(None, SEARCH, request_ref="synthetic-request", transport=fixture)).outcome, Outcome.UNAVAILABLE)
        self.assertEqual((await run_synthetic(CONFIG, SEARCH, request_ref="synthetic-request", transport=None)).outcome, Outcome.UNAVAILABLE)
        future = replace(route_query(), departure=Departure("specified_time", AT + timedelta(days=10)))
        self.assertEqual((await run_synthetic(CONFIG, future, request_ref="synthetic-request", transport=fixture)).outcome, Outcome.UNSUPPORTED)
        self.assertEqual(calls, [])

    async def test_caller_cancellation_propagates(self):
        entered = asyncio.Event()
        stopped = []
        async def fixture(request):
            entered.set()
            try:
                await asyncio.sleep(1)
            finally:
                stopped.append(True)
        task = asyncio.create_task(run_synthetic(CONFIG, SEARCH, request_ref="synthetic-request", transport=fixture))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(stopped, [True])


if __name__ == "__main__":
    unittest.main()
