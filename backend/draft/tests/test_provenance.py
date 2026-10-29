"""L0 source-shape regressions; synthetic PLACE bytes, never provider evidence."""
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from cj_agent.draft import document_from_model
from cj_draft.provenance import build_document
from cj_message.domain import Receipt, Stored
from cj_place import (ORIGIN, Config, Coordinate, Departure, Endpoint, Response,
                      RouteQuery, Search, parse_response, prepare)
from cj_trip.domain import Proposal, packed

AT = datetime(2026, 10, 29, 9, tzinfo=timezone.utc)
CONFIG = Config(ORIGIN, 4096, 65536, 3, 60)


def message():
    raw = packed({'version': 'MESSAGE-send.1', 'conversation_id': 'c', 'message_id': 'm',
                  'text': '我还没有决定出行日期 / Dates not decided', 'trip_id': None,
                  'creation_intent': 'consider_trip', 'expected_generation': 'g', 'expected_sequence': 0})
    return Stored(raw, Receipt('m', 'c', 'g', 1, 'r', hashlib.sha256(raw).hexdigest()))


def parsed(query, body, ref):
    request = prepare(CONFIG, query, ref, AT)
    response = Response(request.binding_digest, request.origin, request.path, 200,
                        packed(body), AT + timedelta(seconds=1))
    return parse_response(CONFIG, request, response, now=AT + timedelta(seconds=2), evidence='synthetic')


def observations():
    search = parsed(Search('合成公园', '合成城市', 1, 20), {
        'status': '1', 'info': 'OK', 'infocode': '10000', 'count': '1',
        'pois': [{'id': 'SYNTH_A', 'name': '合成公园', 'address': '合成路', 'location': '116.1,39.1'}]}, 'search-1')
    query = RouteQuery(Endpoint('SYNTH_A', Coordinate('116.1,39.1'), 'entrance'),
                       Endpoint('SYNTH_B', Coordinate('116.2,39.2'), 'poi_center'),
                       'walking', Departure('at_query_time', None))
    route = parsed(query, {'status': '1', 'info': 'OK', 'infocode': '10000', 'count': '1',
                          'route': {'origin': '116.1,39.1', 'destination': '116.2,39.2',
                                    'paths': [{'distance': '123.50', 'duration': '60'}]}}, 'route-1')
    return search, route


def document(results=None, now=AT + timedelta(seconds=3)):
    original = document_from_model('{"title":"Draft","items":["Check opening hours"]}')
    return build_document(original, message(), observations() if results is None else results,
                          now=now, max_age_seconds=60)


def proposal(raw):
    return Proposal('p-r', 'trip-r', 0, 'run-r', 2000000000, raw)


def test_four_categories_have_original_records_and_never_claim_verification():
    raw = document()
    proposal(raw)
    value = json.loads(raw)
    assert {i['source_category'] for i in value['items']} == {'user_provided', 'queried', 'estimated', 'unknown'}
    assert all(i['verification'] == 'pending' and i['evidence'] == [] for i in value['items'])
    assert value['decisions'] == {'travel_dates': 'unknown', 'prompt': 'decide_travel_dates'}
    assert value['items'][0]['text'] == json.loads(message().raw)['text']
    assert value['items'][-1]['text'] == 'Check opening hours'
    assert [i['text'] for i in value['items'] if i['source_category'] == 'estimated'] == ['123.50 m', '60 s']
    for source in value['sources']:
        snapshot = base64.b64decode(source['snapshot_utf8_base64'])
        assert hashlib.sha256(snapshot).hexdigest() == source['snapshot_sha256']
        assert json.loads(snapshot)['display_text'] == source['text']
    assert all(s['evidence_level'] == 'synthetic' for s in value['sources'][1:])


def test_no_query_does_not_invent_query_or_estimate_sources():
    value = json.loads(document(()))
    assert [i['source_category'] for i in value['items']] == ['user_provided', 'unknown']
    assert len(value['sources']) == 1


def test_supplied_stale_query_rejects_whole_candidate():
    with pytest.raises(ValueError, match='stale'):
        document(now=AT + timedelta(seconds=61))


@pytest.mark.parametrize('mutation', ['verified', 'forged-category', 'missing-ref', 'borrowed-ref',
                                     'text-substitution', 'snapshot-tamper', 'structured-time', 'duplicate-source'])
def test_source_claims_cannot_be_repaired_or_silently_downgraded(mutation):
    value = deepcopy(json.loads(document()))
    if mutation == 'verified': value['items'][0]['verification'] = 'verified'
    elif mutation == 'forged-category': value['items'][0]['source_category'] = 'queried'
    elif mutation == 'missing-ref': value['items'][0]['source_refs'] = ['missing']
    elif mutation == 'borrowed-ref': value['items'][-1]['source_refs'] = ['source-1']
    elif mutation == 'text-substitution': value['items'][1]['text'] = 'A model claim not in the source'
    elif mutation == 'snapshot-tamper': value['sources'][0]['snapshot_sha256'] = '0' * 64
    elif mutation == 'structured-time': value['items'][0]['start'] = '09:00'
    elif mutation == 'duplicate-source': value['sources'].append(value['sources'][0])
    with pytest.raises(ValueError): proposal(packed(value))


def test_legacy_document_is_unchanged_and_source_bytes_change_the_candidate_hash():
    legacy = document_from_model('{"title":"Draft","items":["09:00 description"]}')
    assert proposal(legacy).content == legacy
    current = document()
    changed = json.loads(current)
    changed['decisions']['travel_dates'] = 'undecided'
    assert proposal(current).digest('scope') != proposal(packed(changed)).digest('scope')


def test_missing_query_freshness_budget_is_not_treated_as_zero_or_success():
    original = document_from_model('{"title":"Draft","items":["Unknown suggestion"]}')
    with pytest.raises(ValueError, match='budget missing'):
        build_document(original, message(), observations(), now=AT, max_age_seconds=None)
    assert json.loads(build_document(original, message(), (), now=AT, max_age_seconds=None))['sources'][0]['kind'] == 'message'
