"""The place library: field rules, drafts in the Codex formats, and the byte-identical copies (#1985)."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'knowledge/places'))
import generate  # noqa: E402
import placelib  # noqa: E402

_spec = importlib.util.spec_from_file_location('places_validate', ROOT / 'knowledge/places/validate.py')
validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate)

# C1 sample with its "a | b" alternatives resolved: what Codex is asked to deliver.
C1 = {
    'id': 'pl_bj_gugong', 'city': 'beijing', 'category': 'attraction', 'subcategory': 'history', 'tier': 'main',
    'name_zh': '故宫博物院', 'name_en': 'The Palace Museum (Forbidden City)', 'aliases_zh': ['故宫', '紫禁城'],
    'aliases_en': ['Forbidden City'], 'address_zh': '北京市东城区景山前街4号', 'address_en': None,
    'district_zh': '东城区',
    'nearest_metro': {'station_zh': '天安门东', 'station_en': "Tian'anmen East", 'line': '1号线', 'exit': None},
    'hours_zh': '8:30–17:00（旺季），周一闭馆', 'hours_source': 'https://www.dpm.org.cn/tickets.html',
    'ticket': {'booking': 'required', 'passport_required': True, 'price_cny': 60, 'closed_weekdays': [1],
               'booking_channel_zh': '故宫博物院官网或官方小程序实名预约', 'booking_url': 'https://www.dpm.org.cn/'},
    'intro_short_zh': '明清两代皇宫，世界最大的古代宫殿建筑群。',
    'intro_short_en': 'The imperial palace of the Ming and Qing dynasties, now a museum.',
    'intro_long_zh': '故宫是明清两代的皇宫，沿中轴线布局，保存着大量宫殿和文物。',
    'intro_long_en': 'The Forbidden City was the imperial palace for almost five centuries and is laid out along the central axis.',
    'visit_minutes': 180, 'best_time_zh': '上午开门即入，避开周末',
    'foreigner_signals': {'english_signage': True, 'foreign_cards': None, 'english_service': True,
                          'evidence': ['https://en.dpm.org.cn/']},
    'external_signals': [{'source': 'tripadvisor', 'metric': 'rank_in_city', 'value': 1, 'as_of': '2026-11-28',
                          'url': 'https://www.tripadvisor.com/Attraction_Review-g294212-d325811'}],
    'official_url': 'https://www.dpm.org.cn/', 'sources': ['https://www.dpm.org.cn/tickets.html'],
    'checked_on': '2026-11-28', 'confidence': 'high', 'notes': None,
}
C7 = {
    'id': 'pl_bj_pek', 'city': 'beijing', 'category': 'hub', 'hub_type': 'airport',
    'name_zh': '北京首都国际机场', 'name_en': 'Beijing Capital International Airport', 'code': 'PEK',
    'terminals': [{'name': 'T3', 'note_zh': '国际航班主要在 T3'}],
    'to_city_zh': ['机场快轨到东直门约 20 分钟'], 'to_city_en': ['Airport Express to Dongzhimen, about 20 minutes'],
    'foreigner_tips_zh': ['入境后可在到达厅办理外币兑换'], 'official_url': 'https://www.bcia.com.cn/',
    'sources': ['https://www.bcia.com.cn/'], 'checked_on': '2026-11-28', 'confidence': 'high',
}
C8_HOTEL = {
    'id': 'pl_bj_hotel_demo', 'city': 'beijing', 'category': 'hotel', 'subcategory': 'international_brand',
    'tier': 'main', 'name_zh': '北京示例酒店', 'name_en': 'Beijing Demo Hotel', 'aliases_zh': [], 'aliases_en': [],
    'address_zh': '北京市朝阳区示例路1号', 'star': 5, 'price_band': '>2000', 'accepts_foreigners': True,
    'foreign_service': {'english_front_desk': True, 'foreign_guest_share': None, 'foreign_guest_experience': '长期接待外籍客人',
                        'international_brand': None, 'evidence_zh': '官网英文页列出英文前台。', 'evidence': ['https://www.example-hotel.com.cn/en/']},
    'foreigner_signals': {'english_signage': True, 'foreign_cards': True, 'english_service': True,
                          'evidence': ['https://www.example-hotel.com.cn/en/']},
    'intro_short_zh': '朝阳区的国际品牌酒店。', 'intro_short_en': 'An international-brand hotel in Chaoyang.',
    'intro_long_zh': '位于朝阳区，设有英文前台，方便外国游客入住。',
    'intro_long_en': 'In Chaoyang, with an English-speaking front desk that suits foreign guests.',
    'official_url': 'https://www.example-hotel.com.cn/', 'sources': ['https://www.example-hotel.com.cn/en/'],
    'checked_on': '2026-11-28', 'confidence': 'medium',
}


def library_entry(draft, **extra):
    """What an approved draft becomes: normalised, without internal signals, located and reviewed."""
    entry = {key: draft.get(key) for key in placelib.fields_for(draft['category'], library=True)}
    for key in ('aliases_zh', 'aliases_en'):
        entry[key] = draft.get(key) or []
    entry.pop('external_signals', None)
    entry['tier'] = draft.get('tier', 'main')
    entry['rank'] = 1
    entry['location'] = {'gcj02': {'lat': 39.916345, 'lng': 116.397155}, 'amap_id': 'B000A8UIN8',
                         'amap_name': '故宫博物院', 'method': 'amap-poi-search', 'geocoded_on': '2026-11-29'}
    entry['review'] = {'status': 'approved', 'reviewer': 'JT', 'reviewed_on': '2026-11-30', 'note': None}
    entry.update(extra)
    return entry


def city_doc(*places, city='beijing'):
    return {'version': placelib.VERSION, 'city': city, 'places': sorted(places, key=lambda p: p['id'])}


def write_city(tmp_path, doc):
    path = tmp_path / 'places' / f'{doc["city"]}.v1.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(placelib.dumps(doc), encoding='utf-8')
    return path


def layout(tmp_path):
    return generate.Layout(tmp_path / 'places', tmp_path / 'server', tmp_path / 'app' / 'LioPlaces.v1.json')


# ---------------------------------------------------------------- drafts in the Codex formats

@pytest.mark.parametrize('draft', [C1, C7, C8_HOTEL], ids=['C1', 'C7', 'C8'])
def test_codex_samples_are_valid_drafts(draft):
    assert placelib.check_draft(draft) == ([], [])


def test_a_null_field_from_another_category_is_dropped_silently():
    assert placelib.check_draft({**C8_HOTEL, 'ticket': None, 'visit_minutes': None, 'best_time_zh': None}) == ([], [])
    assert placelib.check_draft({**C8_HOTEL, 'visit_minutes': 90})[1]


def test_draft_with_unknown_field_is_kept_with_a_warning():
    errors, warnings = placelib.check_draft({**C1, 'mood': 'calm'})
    assert errors == [] and any('mood' in w for w in warnings)


@pytest.mark.parametrize('change', [
    lambda e: e.update(lat=39.9),                                   # coordinates come from Amap, not the draft
    lambda e: e.update(location={'lat': 1, 'lng': 2}),
    lambda e: e.update(id='gugong'),
    lambda e: e.update(id='pl_sh_gugong'),                          # abbreviation of another city
    lambda e: e.update(city='tokyo'),
    lambda e: e.update(category='museum'),
    lambda e: e.update(subcategory='castle'),
    lambda e: e.update(sources=[]),
    lambda e: e.update(official_url='http://www.dpm.org.cn/'),          # user-facing links must be https
    lambda e: e.update(sources=['https://www.tripadvisor.com/Attraction_Review-1']),
    lambda e: e.update(hours_source='https://www.mafengwo.cn/poi/1.html'),
    lambda e: e.update(sources=['https://www.ctrip.com./x']),          # trailing dot is the same host
    lambda e: e.update(sources=['https://WWW.DIANPING.COM./shop/1']),
    lambda e: e.update(sources=['https://xhslink.com/abc']),
    lambda e: e.update(checked_on='2026-02-30'),
    lambda e: e.update(confidence='certain'),
    lambda e: e.update(intro_short_zh='长' * 41),
    lambda e: e.update(intro_long_en='x' * 451),
    lambda e: e.update(intro_short_zh='两行\n文字'),
    lambda e: e.update(visit_minutes='三小时'),
    lambda e: e['ticket'].update(closed_weekdays=[0]),
    lambda e: e['ticket'].update(booking='maybe'),
    lambda e: e['foreigner_signals'].update(evidence=[]),           # a stated signal needs evidence
    lambda e: e['nearest_metro'].update(station_zh=None),
    lambda e: e.pop('name_en'),
])
def test_invalid_c1_draft_is_rejected(change):
    entry = copy.deepcopy(C1)
    change(entry)
    errors, _ = placelib.check_draft(entry)
    assert errors


def test_hotel_draft_must_accept_foreigners_with_evidence():
    assert placelib.check_draft({**C8_HOTEL, 'accepts_foreigners': False})[0]
    assert placelib.check_draft({**C8_HOTEL, 'foreigner_signals': None})[0]
    assert placelib.check_draft({**C8_HOTEL, 'price_band': '100'})[0]


def test_hub_draft_needs_type_and_code():
    assert placelib.check_draft({**C7, 'hub_type': 'port'})[0]
    assert placelib.check_draft({**C7, 'code': None})[0]                           # an airport needs its code
    assert placelib.check_draft({**C7, 'hub_type': 'rail', 'code': None}) == ([], [])  # a railway station has none


def test_http_is_accepted_for_reference_sources_but_not_for_user_facing_links():
    old_site = 'http://wglj.gz.gov.cn/mdjl/cjwt/jdjq/content/post_10878687.html'
    assert placelib.check_draft({**C1, 'sources': [old_site]}) == ([], [])
    assert placelib.check_draft({**C1, 'foreigner_signals': {**C1['foreigner_signals'], 'evidence': [old_site]}}) == ([], [])
    assert placelib.check_draft({**C1, 'official_url': old_site})[0]
    assert placelib.check_draft({**C1, 'hours_source': old_site})[0]
    assert placelib.check_draft({**C1, 'ticket': {**C1['ticket'], 'booking_url': old_site}})[0]
    assert placelib.check_draft({**C1, 'sources': ['ftp://example.org/x']})[0]


def test_http_does_not_get_a_third_party_site_past_the_blacklist():
    for bad in ('http://www.tripadvisor.com/x', 'http://www.ctrip.com./x', 'http://www.booking.com/h'):
        assert placelib.check_draft({**C1, 'sources': [bad]})[0], bad
        assert placelib.check_draft({**C1, 'foreigner_signals': {**C1['foreigner_signals'], 'evidence': [bad]}})[0], bad


def test_library_hub_rules_match_the_draft_rules(tmp_path):
    airport, station = library_entry(C7), library_entry(C7, id='pl_bj_beijingnan', hub_type='rail', code=None,
                                                         name_zh='北京南站', name_en='Beijing South', aliases_zh=[], aliases_en=[], rank=2)
    assert placelib.load_city(write_city(tmp_path, city_doc(airport, station)))
    with pytest.raises(placelib.Invalid):
        placelib.load_city(write_city(tmp_path, city_doc(library_entry(C7, code=None))))      # an airport without its code


def test_hotel_foreign_service_is_the_structured_object_codex_delivers():
    assert placelib.check_draft({**C8_HOTEL, 'foreign_service': {'english_front_desk': None, 'foreign_guest_share': None,
                                'foreign_guest_experience': None, 'international_brand': 'Marriott Bonvoy',
                                'evidence_zh': '官网列出。', 'evidence': ['https://www.marriott.com/en-us/hotels/x/']}}) == ([], [])
    assert placelib.check_draft({**C8_HOTEL, 'foreign_service': '英文前台'})[0]                 # the old free-text shape
    assert placelib.check_draft({**C8_HOTEL, 'foreign_service': {'english_front_desk': 'yes'}})[0]
    assert placelib.check_draft({**C8_HOTEL, 'foreign_service': None}) == ([], [])


def test_a_malformed_entry_is_an_error_not_a_crash():
    assert placelib.check_draft('not an object')[0]
    assert placelib.check_draft({**C1, 'ticket': 'free'})[0]
    assert placelib.check_draft({**C1, 'sources': 'https://www.dpm.org.cn/'})[0]


# ---------------------------------------------------------------- the library shape

def test_library_entry_from_a_c1_draft_is_valid_and_drops_internal_signals(tmp_path):
    entry = library_entry(C1)
    assert 'external_signals' not in entry
    doc = placelib.load_city(write_city(tmp_path, city_doc(entry)))
    assert doc['places'][0]['location']['amap_id'] == 'B000A8UIN8'


def test_every_category_has_a_valid_library_shape(tmp_path):
    hub = library_entry(C7)
    doc = placelib.load_city(write_city(tmp_path, city_doc(library_entry(C1), hub, library_entry(C8_HOTEL, rank=1))))
    assert {p['category'] for p in doc['places']} == {'attraction', 'hub', 'hotel'}


def _library_with(tmp_path, change):
    entry = library_entry(C1)
    change(entry)
    return write_city(tmp_path, city_doc(entry))


@pytest.mark.parametrize('change', [
    lambda e: e['location']['gcj02'].update(lat=0, lng=0),                       # (0,0) was once accepted (#1943)
    lambda e: e['location']['gcj02'].update(lat=31.23, lng=121.47),              # Shanghai point in the Beijing file
    lambda e: e['location']['gcj02'].update(lat=39.9163451),                      # more than six decimals
    lambda e: e['location'].update(amap_id=None),                                 # an Amap match needs its id
    lambda e: e['location'].update(method='guess'),
    lambda e: e.pop('location'),
    lambda e: e.pop('review'),
    lambda e: e['review'].update(status='pending'),
    lambda e: e['review'].update(reviewer=''),
    lambda e: e.update(external_signals=[]),                                      # never in the library
    lambda e: e.update(aliases_zh=None),
    lambda e: e.update(intro_long_zh=None),
    lambda e: e.update(rank=0),
    lambda e: e.update(extra=True),
    lambda e: e.update(city='shanghai'),
])
def test_invalid_library_entry_is_rejected(tmp_path, change):
    with pytest.raises(placelib.Invalid):
        placelib.load_city(_library_with(tmp_path, change))


def test_manual_location_does_not_need_an_amap_id(tmp_path):
    def manual(entry):
        entry['location'].update(method='manual', amap_id=None, amap_name=None)
    assert placelib.load_city(_library_with(tmp_path, manual))


def test_city_file_rules(tmp_path):
    first, second = library_entry(C1), library_entry(C1, id='pl_bj_other', name_zh='别处', name_en='Elsewhere', aliases_zh=[], aliases_en=[], rank=2)
    assert placelib.load_city(write_city(tmp_path, city_doc(first, second)))
    duplicate_id = library_entry(C1, name_zh='重名', name_en='Same id', aliases_zh=[], aliases_en=[])
    shared_alias = library_entry(C1, id='pl_bj_shared', name_zh='另一个', name_en='Another', rank=2)  # keeps the aliases of first
    same_rank = library_entry(C1, id='pl_bj_rank', name_zh='排名重复', name_en='Same rank', aliases_zh=[], aliases_en=[])
    for broken in (city_doc(first, duplicate_id), city_doc(first, shared_alias), city_doc(first, same_rank)):
        with pytest.raises(placelib.Invalid):
            placelib.load_city(write_city(tmp_path, broken))
    unsorted = {'version': placelib.VERSION, 'city': 'beijing', 'places': [second, first]}
    with pytest.raises(placelib.Invalid):
        placelib.load_city(write_city(tmp_path, unsorted))


def test_file_name_and_keys_must_match(tmp_path):
    path = write_city(tmp_path, city_doc(library_entry(C1)))
    path.rename(path.with_name('shanghai.v1.json'))
    with pytest.raises(placelib.Invalid):
        placelib.load_city(path.with_name('shanghai.v1.json'))
    raw = placelib.dumps(city_doc(library_entry(C1))).replace('"version"', '"version": "x", "version"', 1)
    path.write_text(raw, encoding='utf-8')
    with pytest.raises(placelib.Invalid):
        placelib.load_city(path)  # duplicate JSON key


# ---------------------------------------------------------------- booking rules stay the one source

def _rule(requirement, closed):
    return {'id': 'beijing.gugong', 'name': {'zh': '故宫博物院', 'en': 'The Palace Museum'}, 'aliases': ['故宫'],
            'requirement': requirement, 'closed_weekdays': closed}


def test_places_may_not_contradict_the_booking_rule_table():
    docs = [city_doc(library_entry(C1))]
    assert validate.booking_conflicts(docs, [_rule('required', ['monday'])]) == []
    assert validate.booking_conflicts(docs, [_rule('required', None)]) == []
    assert validate.booking_conflicts(docs, [_rule('not_required', ['monday'])])
    assert validate.booking_conflicts(docs, [_rule('required', ['tuesday'])])
    assert validate.booking_conflicts(docs, [{**_rule('required', None), 'name': {'zh': 'x', 'en': 'y'}, 'aliases': []}]) == []


def test_validate_reports_an_id_used_in_two_city_files(tmp_path):
    lay = layout(tmp_path)
    write_city(tmp_path, city_doc(library_entry(C1)))
    shanghai = library_entry(C1, city='shanghai', location={**library_entry(C1)['location'], 'gcj02': {'lat': 31.2304, 'lng': 121.4737}})
    write_city(tmp_path, city_doc(shanghai, city='shanghai'))
    with pytest.raises(placelib.Invalid):
        validate.validate(lay, rules=[])  # id pl_bj_gugong has the Beijing abbreviation inside the Shanghai file


# ---------------------------------------------------------------- generated copies

def test_copies_are_generated_and_checked_byte_for_byte(tmp_path):
    lay = layout(tmp_path)
    source = write_city(tmp_path, city_doc(library_entry(C1), library_entry(C7)))
    assert [p.name for p in generate.stale(lay)] == ['places_beijing.v1.json', 'LioPlaces.v1.json']
    generate.write(lay)
    assert generate.stale(lay) == []
    assert generate.server_copy(lay, 'beijing').read_bytes() == source.read_bytes()
    app = json.loads(lay.app_path.read_text(encoding='utf-8'))
    assert app['version'] == placelib.APP_VERSION
    gugong = next(p for p in app['places'] if p['id'] == 'pl_bj_gugong')
    assert gugong['kind'] == 'history' and gugong['lat'] == 39.916345 and gugong['thumb'] is None
    assert list(gugong) == list(generate.APP_KEYS)
    assert 'ticket' not in gugong and 'review' not in gugong and 'external_signals' not in gugong
    assert [p['category'] for p in app['places']] == ['attraction', 'hub']


def test_app_copy_carries_a_hotels_filter_fields_and_every_places_amap_id():
    located = lambda amap_id: {**library_entry(C1)['location'], 'amap_id': amap_id}   # noqa: E731
    hotel = library_entry(C8_HOTEL, id='pl_bj_hotel_demo', rank=3, location=located('B0HOTEL'))
    text = generate.render_app([city_doc(library_entry(C1, location=located('B0GUGONG')), hotel)])
    places = {p['id']: p for p in json.loads(text)['places']}
    stay = places['pl_bj_hotel_demo']
    assert (stay['price_band'], stay['star'], stay['accepts_foreigners']) == ('>2000', 5, True)
    assert stay['amap_id'] == 'B0HOTEL' and places['pl_bj_gugong']['amap_id'] == 'B0GUGONG'
    sight = places['pl_bj_gugong']                                   # not a hotel: the three fields are null
    assert (sight['price_band'], sight['star'], sight['accepts_foreigners']) == (None, None, None)
    assert list(stay) == list(generate.APP_KEYS) == list(sight)


@pytest.mark.parametrize('damage', ['server', 'app', 'source'])
def test_a_changed_fact_without_regeneration_is_detected(tmp_path, damage):
    lay = layout(tmp_path)
    source = write_city(tmp_path, city_doc(library_entry(C1)))
    generate.write(lay)
    target = {'server': generate.server_copy(lay, 'beijing'), 'app': lay.app_path, 'source': source}[damage]
    target.write_text(target.read_text(encoding='utf-8').replace('故宫博物院', '故宫博物馆', 1), encoding='utf-8')
    assert generate.stale(lay), f'a changed {damage} must be reported'


def test_a_copy_without_a_source_is_stale_and_write_removes_it(tmp_path):
    lay = layout(tmp_path)
    write_city(tmp_path, city_doc(library_entry(C1)))
    generate.write(lay)
    (tmp_path / 'places' / 'beijing.v1.json').unlink()
    assert sorted(p.name for p in generate.stale(lay)) == ['LioPlaces.v1.json', 'places_beijing.v1.json']
    generate.write(lay)
    assert generate.stale(lay) == [] and not lay.app_path.exists()


def test_a_non_canonical_source_is_rejected(tmp_path):
    lay = layout(tmp_path)
    path = write_city(tmp_path, city_doc(library_entry(C1)))
    path.write_text(json.dumps(json.loads(path.read_text(encoding='utf-8')), ensure_ascii=False), encoding='utf-8')
    with pytest.raises(placelib.Invalid):
        generate.stale(lay)
    generate.write(lay)  # --write canonicalises
    assert generate.stale(lay) == []


def test_app_copy_orders_by_city_category_rank():
    first = library_entry(C1, rank=2)
    second = library_entry(C1, id='pl_bj_a_park', name_zh='公园', name_en='A Park', aliases_zh=[], aliases_en=[], rank=1)
    third = library_entry(C1, id='pl_bj_unranked', name_zh='无名', name_en='Unranked', aliases_zh=[], aliases_en=[], rank=None)
    text = generate.render_app([city_doc(first, second, third)], {'pl_bj_a_park': 'pl_bj_a_park_thumb.png'})
    places = json.loads(text)['places']
    assert [p['id'] for p in places] == ['pl_bj_a_park', 'pl_bj_gugong', 'pl_bj_unranked']
    assert places[0]['thumb'] == 'pl_bj_a_park_thumb.png'


# ---------------------------------------------------------------- the hubs copy for the 大交通 page

def _hub_layout(tmp_path):
    return generate.Layout(tmp_path / 'places', tmp_path / 'server', tmp_path / 'app' / 'LioPlaces.v1.json', None,
                           tmp_path / 'app' / 'LioTransportHubs.v1.json')


def _rail(**change):
    return library_entry({**C7, 'id': 'pl_bj_beijingnan', 'name_zh': '北京南站', 'name_en': 'Beijing South Railway Station',
                          'hub_type': 'rail', 'code': None, 'terminals': None}, **change)


def test_the_hubs_copy_has_the_shape_the_transport_page_reads_and_orders_airports_first(tmp_path):
    lay = _hub_layout(tmp_path)
    airport = library_entry({**C7, 'terminals': [{'name': 'T3', 'note_zh': '国际航班', 'note_en': 'International flights'}, {'name': 'T2', 'note_zh': None}]}, rank=2)
    write_city(tmp_path, city_doc(library_entry(C1), _rail(rank=1), airport))
    generate.write(lay)
    doc = json.loads(lay.hubs_path.read_text(encoding='utf-8'))
    assert doc['version'] == 'g2c-transport-hubs.1' and doc['status'] == 'approved'
    assert [p['id'] for p in doc['places']] == ['pl_bj_pek', 'pl_bj_beijingnan']              # airport before rail whatever the rank
    pek = doc['places'][0]
    assert list(pek) == list(generate.HUB_KEYS) and pek['code'] == 'PEK' and pek['hub_type'] == 'airport'
    assert pek['terminals'] == [{'name': 'T3', 'note_zh': '国际航班', 'note_en': 'International flights'},
                                {'name': 'T2', 'note_zh': None, 'note_en': None}]
    assert doc['places'][1]['terminals'] is None and doc['places'][1]['code'] is None
    assert all('review' not in p and 'location' not in p and 'rank' not in p for p in doc['places'])
    assert generate.stale(lay) == []


def test_no_approved_hub_means_no_hubs_copy_and_the_transport_lines_draft_is_left_alone(tmp_path):
    lay = _hub_layout(tmp_path)
    lay.hubs_path.parent.mkdir(parents=True)
    draft = json.dumps({'version': 'g2c-transport-hubs.1', 'status': 'draft', 'places': []})
    lay.hubs_path.write_text(draft, encoding='utf-8')
    write_city(tmp_path, city_doc(library_entry(C1)))                                          # a library with no hub at all
    generate.write(lay)
    assert lay.hubs_path.read_text(encoding='utf-8') == draft and generate.stale(lay) == []
    retired = library_entry(C7, review={'status': 'retired', 'reviewer': 'JT', 'reviewed_on': '2026-11-30', 'note': None})
    write_city(tmp_path, city_doc(library_entry(C1), retired))                                 # a retired hub does not count
    generate.write(lay)
    assert lay.hubs_path.read_text(encoding='utf-8') == draft


def test_an_approved_hubs_copy_without_an_approved_hub_behind_it_is_stale_and_removed(tmp_path):
    lay = _hub_layout(tmp_path)
    write_city(tmp_path, city_doc(library_entry(C1), library_entry(C7)))
    generate.write(lay)
    assert lay.hubs_path.is_file()
    write_city(tmp_path, city_doc(library_entry(C1)))
    assert lay.hubs_path in generate.stale(lay)
    generate.write(lay)
    assert not lay.hubs_path.exists() and generate.stale(lay) == []


def test_a_changed_hubs_copy_is_detected(tmp_path):
    lay = _hub_layout(tmp_path)
    write_city(tmp_path, city_doc(library_entry(C7)))
    generate.write(lay)
    lay.hubs_path.write_text(lay.hubs_path.read_text(encoding='utf-8').replace('PEK', 'XXX'), encoding='utf-8')
    assert generate.stale(lay) == [lay.hubs_path]


@pytest.mark.parametrize('code', [None, 'pek', 'PE', 'PEKK'])
def test_an_airport_the_app_would_refuse_is_refused_here_first(tmp_path, code):
    lay = _hub_layout(tmp_path)
    write_city(tmp_path, city_doc(library_entry({**C7, 'code': code})))
    with pytest.raises(placelib.Invalid):
        generate.expected(lay)


def test_terminal_notes_may_carry_an_english_line_and_nothing_else_extra():
    assert placelib.check_draft({**C7, 'terminals': [{'name': 'T1', 'note_zh': None, 'note_en': 'Domestic'}]})[0] == []
    assert placelib.check_draft({**C7, 'terminals': [{'name': 'T1', 'note_zh': None}]})[0] == []
    assert placelib.check_draft({**C7, 'terminals': [{'name': 'T1', 'note_zh': None, 'note_fr': 'x'}]})[0]


# ---------------------------------------------------------------- the repository itself

def test_committed_library_and_copies_are_in_step():
    docs, problems = validate.validate()
    assert problems == []
    assert generate.stale() == [], 'run python3 -B knowledge/places/validate.py --write'
    assert generate.LAYOUT.app_path == ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/Resources/LioPlaces.v1.json'
    assert [d['city'] for d in docs] == [c for c in placelib.CITIES if (placelib.PLACES_DIR / f'{c}.v1.json').is_file()]


def test_the_app_package_declares_the_copy_once_it_exists():
    """SwiftPM lists resources one by one: a generated App copy that Package.swift does not name is never bundled."""
    if generate.LAYOUT.app_path.is_file():
        package = (ROOT / 'ios/Modules/CJShell/Package.swift').read_text(encoding='utf-8')
        assert 'Resources/LioPlaces.v1.json' in package, 'add .process("Resources/LioPlaces.v1.json") to the CJLioUser target'
