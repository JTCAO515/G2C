"""Importing Codex drafts: validation, Amap matching, scoring and the review table (#1986)."""
import copy
import csv
import io
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'knowledge/places'))
sys.path.insert(0, str(ROOT / 'knowledge/places/import'))
sys.path.insert(0, str(ROOT / 'backend/tests'))
import amap  # noqa: E402
import import_drafts as importer  # noqa: E402
import placelib  # noqa: E402
import score  # noqa: E402
from test_places_pipeline import C1, C7, C8_HOTEL, library_entry  # noqa: E402

TODAY = '2026-11-29'
SECRET = 'SECRET-KEY-123456'


def poi(name, ident='B000A8UIN8', address='景山前街4号', lng='116.397029', lat='39.917839'):
    return {'id': ident, 'name': name, 'address': address, 'type': '风景名胜', 'location': f'{lng},{lat}'}


def fake_fetch(pois=None, geocodes=None, calls=None):
    def fetch(path, params):
        if calls is not None:
            calls.append((path, params))
        if path == '/v3/place/text':
            return {'status': '1', 'info': 'OK', 'infocode': '10000', 'pois': pois(params['keywords']) if callable(pois) else (pois or [])}
        return {'status': '1', 'info': 'OK', 'infocode': '10000', 'geocodes': geocodes or []}
    return fetch


def inbox(tmp_path, **files):
    for name, entries in files.items():
        folder, _, file = name.partition('__')
        path = tmp_path / 'inbox' / folder / f'{file.replace("_", "-")}.json'  # C8__beijing_hotel -> C8/beijing-hotel.json
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries, ensure_ascii=False), encoding='utf-8')
    return tmp_path / 'inbox'


def second(**change):
    entry = copy.deepcopy(C1)
    entry.update(id='pl_bj_tiantan', name_zh='天坛公园', name_en='Temple of Heaven', aliases_zh=['天坛'], aliases_en=[], subcategory='park')
    entry.update(change)
    return entry


# ---------------------------------------------------------------- Amap matching

def test_exact_match_gives_a_poi_location_in_gcj02():
    location, info = amap.locate(fake_fetch([poi('故宫博物院')]), {**C1}, TODAY)
    assert info['status'] == 'exact'
    assert location == {'gcj02': {'lat': 39.917839, 'lng': 116.397029}, 'amap_id': 'B000A8UIN8', 'amap_name': '故宫博物院',
                        'method': 'amap-poi-search', 'geocoded_on': TODAY}


@pytest.mark.parametrize('found, status', [
    ([poi('故宫博物院(午门)')], 'close'),
    ([poi('故宫角楼咖啡')], 'weak'),
    ([poi('紫禁城')], 'exact'),                       # an alias counts
])
def test_match_status(found, status):
    assert amap.locate(fake_fetch(found), {**C1}, TODAY)[1]['status'] == status


def test_pois_outside_the_city_box_are_ignored():
    shanghai_namesake = poi('故宫博物院', lng='121.47', lat='31.23')
    location, info = amap.locate(fake_fetch([shanghai_namesake]), {**C1, 'address_zh': None}, TODAY)
    assert location is None and info['status'] == 'none'


def test_address_geocode_is_the_fallback_and_has_no_poi_id():
    geocodes = [{'formatted_address': '北京市东城区景山前街4号', 'location': '116.397,39.918'}]
    location, info = amap.locate(fake_fetch([], geocodes), {**C1}, TODAY)
    assert info['status'] == 'address-only' and location['method'] == 'amap-geocode' and location['amap_id'] is None
    entry = library_entry(C1, location=location)
    placelib.check_library_entry(entry, 'beijing')  # a geocode-only location is a valid library location


def test_amap_failures_never_carry_the_key():
    def refuse(path, params):
        return {'status': '0', 'info': 'INVALID_USER_KEY', 'infocode': '10001'}
    with pytest.raises(amap.AmapError) as error:
        amap.locate(refuse, {**C1}, TODAY)
    assert 'stopping' in str(error.value)
    assert amap.scrub(f'https://x?key={SECRET}&a=1', SECRET) == 'https://x?key=***&a=1'


def test_bad_coordinates_in_an_answer_are_skipped():
    assert amap.search(fake_fetch([poi('故宫博物院', lng='0', lat='0'), {'id': 'B1', 'name': 'x', 'location': 'oops'}]), 'beijing', 'x') == []


# ---------------------------------------------------------------- scoring

def test_score_orders_foreigner_friendly_and_well_matched_entries_first():
    strong = score.score(C1, 'exact')
    weak = score.score({**C1, 'foreigner_signals': None, 'confidence': 'low', 'sources': C1['sources'][:1]}, 'weak')
    assert strong['total'] > weak['total'] and 0 <= weak['total'] <= strong['total'] <= 100
    assert strong['parts']['foreigner'] == 30 and 'external' not in strong['parts']


def test_external_signals_only_count_when_enabled():
    signals = C1['external_signals']
    assert 'external' not in score.score(C1, 'exact', signals)['parts']
    on = score.score(C1, 'exact', signals, use_external=True)
    assert on['parts']['external'] == 20 and on['external_used']
    assert score.score(C1, 'exact', [{'metric': 'rating', 'value': 4.5}], use_external=True)['parts']['external'] == 18


# ---------------------------------------------------------------- import

def test_import_keeps_clean_drafts_and_rejects_bad_ones(tmp_path):
    bad_coords = second(id='pl_bj_x', lat=1.0)
    ok = second()
    dup = copy.deepcopy(C1)
    box = inbox(tmp_path, C1__beijing=[C1, ok, bad_coords, dup], C7__hubs=[C7], C8__beijing_hotel=[C8_HOTEL])
    by_city, rejected, notes = importer.process(box, TODAY, fake_fetch([poi('故宫博物院')]), library_dir=tmp_path / 'none', keep_signals=True)
    ids = [c['id'] for c in by_city['beijing']]
    assert ids == sorted(['pl_bj_gugong', 'pl_bj_tiantan', 'pl_bj_pek', 'pl_bj_hotel_demo'])
    assert sorted(r['id'] for r in rejected) == ['pl_bj_gugong', 'pl_bj_x']   # the second gugong is a duplicate id
    gugong = next(c for c in by_city['beijing'] if c['id'] == 'pl_bj_gugong')
    assert gugong['draft']['tier'] == 'main' and 'external_signals' not in gugong['draft'] and gugong['external_signals']
    assert gugong['location']['amap_id'] == 'B000A8UIN8' and gugong['status'] == 'pending'


def test_draft_is_normalised_to_the_library_fields():
    draft, signals = importer.normalise({k: v for k, v in C7.items()})
    assert set(draft) == set(placelib.fields_for('hub', library=False)) - {'external_signals'}
    assert draft['tier'] == 'main' and draft['aliases_zh'] == [] and signals == []


def test_unreadable_and_non_list_files_are_reported(tmp_path):
    box = inbox(tmp_path, C1__beijing=[C1])
    (box / 'C1' / 'shanghai.json').write_text('{oops', encoding='utf-8')
    (box / 'C1' / 'shenzhen.json').write_text('{"a": 1}', encoding='utf-8')
    (box / 'C1' / 'manifest.json').write_text('[]', encoding='utf-8')
    _, rejected, _ = importer.process(box, TODAY, library_dir=tmp_path / 'none')
    assert sorted(r['file'] for r in rejected) == ['C1/shanghai.json', 'C1/shenzhen.json']


def test_entries_already_in_the_library_are_skipped(tmp_path):
    lib = tmp_path / 'lib'
    lib.mkdir()
    (lib / 'beijing.v1.json').write_text(placelib.dumps({'version': placelib.VERSION, 'city': 'beijing', 'places': [library_entry(C1)]}), encoding='utf-8')
    by_city, _, notes = importer.process(inbox(tmp_path, C1__beijing=[C1, second()]), TODAY, library_dir=lib)
    assert [c['id'] for c in by_city['beijing']] == ['pl_bj_tiantan'] and 'pl_bj_gugong' in notes[0]


def test_offline_run_does_not_touch_the_network_and_marks_the_match_not_run(tmp_path):
    by_city, _, _ = importer.process(inbox(tmp_path, C1__beijing=[C1]), TODAY, fetch=None, library_dir=tmp_path / 'none')
    cand = by_city['beijing'][0]
    assert cand['amap']['status'] == 'not-run' and cand['location'] is None


def test_an_amap_stop_aborts_the_run_but_a_single_miss_does_not(tmp_path):
    box = inbox(tmp_path, C1__beijing=[C1, second()])

    def quota(path, params):
        return {'status': '0', 'info': 'DAILY_QUERY_OVER_LIMIT', 'infocode': '10003'}
    with pytest.raises(amap.AmapError):
        importer.process(box, TODAY, quota, library_dir=tmp_path / 'none')

    def flaky(path, params):
        if params['keywords'] == '天坛公园':
            return {'status': '0', 'info': 'SERVICE_NOT_AVAILABLE', 'infocode': '20000'}
        return fake_fetch([poi('故宫博物院')])(path, params)
    by_city, _, _ = importer.process(box, TODAY, flaky, library_dir=tmp_path / 'none')
    assert {c['id']: c['amap']['status'] for c in by_city['beijing']} == {'pl_bj_gugong': 'exact', 'pl_bj_tiantan': 'error'}


def test_decided_entries_survive_a_rerun_and_pending_ones_are_refreshed(tmp_path):
    box = inbox(tmp_path, C1__beijing=[C1, second()])
    out, review = tmp_path / 'out', tmp_path / 'review'
    first, rejected, notes = importer.process(box, TODAY, library_dir=tmp_path / 'none')
    importer.write_outputs(first, rejected, notes, TODAY, out, review, 25)
    doc = json.loads((out / 'beijing.cand.json').read_text(encoding='utf-8'))
    doc['candidates'][0]['status'] = 'accepted'
    (out / 'beijing.cand.json').write_text(importer.dumps(doc), encoding='utf-8')
    again, _, _ = importer.process(box, '2026-11-30', fake_fetch([poi('天坛公园')]), library_dir=tmp_path / 'none', existing=importer.load_existing(out))
    by_id = {c['id']: c for c in again['beijing']}
    assert by_id['pl_bj_gugong']['status'] == 'accepted' and by_id['pl_bj_gugong']['amap']['status'] == 'not-run'  # untouched
    assert by_id['pl_bj_tiantan']['status'] == 'pending' and by_id['pl_bj_tiantan']['amap']['status'] == 'exact'


def test_a_pending_entry_codex_took_out_is_dropped_and_a_decided_one_stays(tmp_path):
    box = inbox(tmp_path, C1__beijing=[C1, second()])
    out, review = tmp_path / 'out', tmp_path / 'review'
    first, rejected, notes = importer.process(box, TODAY, library_dir=tmp_path / 'none')
    importer.write_outputs(first, rejected, notes, TODAY, out, review, 25)
    doc = json.loads((out / 'beijing.cand.json').read_text(encoding='utf-8'))
    next(c for c in doc['candidates'] if c['id'] == 'pl_bj_gugong')['status'] = 'accepted'
    (out / 'beijing.cand.json').write_text(importer.dumps(doc), encoding='utf-8')
    box = inbox(tmp_path, C1__beijing=[second(id='pl_bj_other', name_zh='别处', name_en='Elsewhere', aliases_zh=[], aliases_en=[])])
    again, _, notes = importer.process(box, '2026-11-30', library_dir=tmp_path / 'none', existing=importer.load_existing(out))
    ids = {c['id']: c['status'] for c in again['beijing']}
    assert ids == {'pl_bj_gugong': 'accepted', 'pl_bj_other': 'pending'}      # pl_bj_tiantan was pending and is gone
    assert any('pl_bj_tiantan' in note and 'dropped' in note for note in notes)


def test_a_pending_entry_with_an_edit_or_a_typed_answer_or_an_unreadable_file_is_not_dropped(tmp_path):
    box = inbox(tmp_path, C1__beijing=[C1, second(), second(id='pl_bj_c', name_zh='丙', name_en='C', aliases_zh=[], aliases_en=[]),
                                         second(id='pl_bj_d', name_zh='丁', name_en='D', aliases_zh=[], aliases_en=[])])
    out, review = tmp_path / 'out', tmp_path / 'review'
    first, rejected, notes = importer.process(box, TODAY, library_dir=tmp_path / 'none')
    importer.write_outputs(first, rejected, notes, TODAY, out, review, 25)
    doc = json.loads((out / 'beijing.cand.json').read_text(encoding='utf-8'))
    next(c for c in doc['candidates'] if c['id'] == 'pl_bj_tiantan')['review_note'] = 'fix the hours'          # apply_review's `edit`
    (out / 'beijing.cand.json').write_text(importer.dumps(doc), encoding='utf-8')
    existing = importer.load_existing(out)
    nothing_left = inbox(tmp_path, C1__beijing=[second(id='pl_bj_e', name_zh='戊', name_en='E', aliases_zh=[], aliases_en=[])])
    again, _, notes = importer.process(nothing_left, TODAY, library_dir=tmp_path / 'none', existing=existing, protected={'pl_bj_c'})
    assert {c['id'] for c in again['beijing']} == {'pl_bj_tiantan', 'pl_bj_c', 'pl_bj_e'}          # gugong and d were plain pending: gone
    assert {n.split(':')[0] for n in notes} == {'pl_bj_gugong', 'pl_bj_d'}
    (tmp_path / 'inbox' / 'C1' / 'beijing.json').write_text('not json', encoding='utf-8')            # the file cannot be read: nothing is dropped
    unreadable, rejected, notes = importer.process(tmp_path / 'inbox', TODAY, library_dir=tmp_path / 'none', existing=existing)
    assert {c['id'] for c in unreadable['beijing']} == {'pl_bj_gugong', 'pl_bj_tiantan', 'pl_bj_c', 'pl_bj_d'} and rejected and not notes


def test_one_bad_alias_or_one_unlisted_field_does_not_cost_the_entry(tmp_path):
    box = inbox(tmp_path, C1__beijing=[C1])
    _side(tmp_path, 'aliases.json', [{'id': 'pl_bj_gugong', 'aliases_zh': ['好别名', 'tab\tbad'], 'aliases_en': ['Good Alias']}])
    _side(tmp_path, 'recheck.json', [{'id': 'pl_bj_gugong', 'field': 'category', 'old': 'attraction', 'new': 'food', 'source': 'https://www.dpm.org.cn/', 'checked_on': '2026-11-28'}])
    by_city, rejected, notes = importer.process(box, TODAY, library_dir=tmp_path / 'none')
    gugong = by_city['beijing'][0]
    assert not rejected and '好别名' in gugong['draft']['aliases_zh'] and 'Good Alias' in gugong['draft']['aliases_en']
    assert not any('tab' in a for a in gugong['draft']['aliases_zh'])
    assert gugong['draft']['category'] == 'attraction'
    assert any('not added' in n for n in notes) and any("recheck of 'category' skipped" in n for n in notes)


def _side(tmp_path, name, rows):
    path = tmp_path / 'inbox' / 'C1' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')


def test_c1_aliases_are_added_to_the_drafts_own_and_their_evidence_is_kept(tmp_path):
    box = inbox(tmp_path, C1__beijing=[C1])
    own = C1['aliases_zh']
    _side(tmp_path, 'aliases.json', [{'id': 'pl_bj_gugong', 'aliases_zh': [*own, '紫禁城', ' 紫禁城 ', '故宮'], 'aliases_en': ['Forbidden City', 'forbidden city'],
                                      'evidence': [{'alias': '紫禁城', 'lang': 'zh', 'url': 'https://www.dpm.org.cn/Visit.html'}]},
                                     {'id': 'pl_bj_nobody', 'aliases_zh': ['x'], 'aliases_en': []}])
    by_city, rejected, notes = importer.process(box, TODAY, library_dir=tmp_path / 'none')
    gugong = by_city['beijing'][0]
    assert gugong['draft']['aliases_zh'] == [*dict.fromkeys([*own, '紫禁城', '故宮'])]            # the draft's own first, no repeats
    assert gugong['draft']['aliases_en'][-1:] == ['Forbidden City'] and len({a.casefold() for a in gugong['draft']['aliases_en']}) == len(gugong['draft']['aliases_en'])
    assert gugong['alias_evidence'][0]['url'].startswith('https://www.dpm.org.cn') and not rejected


def test_c1_rechecks_apply_only_what_still_matches_and_flag_what_is_unconfirmed(tmp_path):
    box = inbox(tmp_path, C1__beijing=[C1])
    ticket_old = C1['ticket']['price_cny'] if C1.get('ticket') else None
    _side(tmp_path, 'recheck.json', [
        {'id': 'pl_bj_gugong', 'field': 'hours_zh', 'old': C1['hours_zh'], 'new': '周二至周日08:30–17:00', 'source': 'https://www.dpm.org.cn/Visit.html', 'checked_on': '2026-11-28'},
        {'id': 'pl_bj_gugong', 'field': 'ticket.price_cny', 'old': ticket_old, 'new': 60, 'source': 'https://www.dpm.org.cn/Visit.html', 'checked_on': '2026-11-28'},
        {'id': 'pl_bj_gugong', 'field': 'official_url', 'old': 'https://not-what-it-held/', 'new': 'https://www.dpm.org.cn/', 'source': 'https://www.dpm.org.cn/', 'checked_on': '2026-11-28'},
        {'id': 'pl_bj_gugong', 'field': 'ticket.booking', 'old': C1['ticket']['booking'], 'new': 'required', 'source': 'https://www.tripadvisor.com/x', 'checked_on': '2026-11-28'},
        {'id': 'pl_bj_gugong', 'field': 'hours_source', 'old': C1.get('hours_source'), 'new': None, 'source': 'https://www.dpm.org.cn/', 'checked_on': '2026-11-28'},
    ])
    by_city, rejected, notes = importer.process(box, TODAY, library_dir=tmp_path / 'none')
    gugong = by_city['beijing'][0]
    assert gugong['draft']['hours_zh'] == '周二至周日08:30–17:00' and gugong['draft']['ticket']['price_cny'] == 60
    assert gugong['draft']['official_url'] == C1['official_url']                    # the draft no longer held the old value
    assert gugong['draft']['ticket']['booking'] == C1['ticket']['booking']          # a third-party source is not applied
    assert any('official_url' in n and 'skipped' in n for n in notes) and any('ticket.booking' in n and 'not applied' in n for n in notes)
    assert any('hours_source' in f and 'by hand' in f for f in gugong['flags'])
    assert 'https://www.dpm.org.cn/Visit.html' in gugong['draft']['sources'] and gugong['draft']['checked_on'] == '2026-11-28'
    assert not rejected


def test_a_hotel_without_a_price_band_is_flagged_for_the_reviewer(tmp_path):
    box = inbox(tmp_path, C8__beijing_hotel=[C8_HOTEL, {**C8_HOTEL, 'id': 'pl_bj_hotel_demo2', 'name_zh': '第二家', 'name_en': 'Second', 'price_band': None}])
    by_city, _, _ = importer.process(box, TODAY, library_dir=tmp_path / 'none')
    flags = {c['id']: c['flags'] for c in by_city['beijing']}
    assert not any('price band' in f for f in flags['pl_bj_hotel_demo'])
    assert any('no price band' in f for f in flags['pl_bj_hotel_demo2'])


def test_pictures_are_marked_in_the_review_table_and_the_local_preview_names_them(tmp_path):
    box = inbox(tmp_path, C1__beijing=[C1, second()])
    images = tmp_path / 'inbox' / 'C2'
    images.mkdir(parents=True)
    (images / 'manifest.json').write_text(json.dumps([{'id': 'pl_bj_gugong', 'file': 'pl_bj_gugong.png', 'thumb': 'pl_bj_gugong_thumb.png'},
                                                      {'id': 'pl_bj_tiantan', 'file': 'pl_bj_tiantan.png', 'thumb': 'pl_bj_tiantan_thumb.png'}]), encoding='utf-8')
    for name in ('pl_bj_gugong.png', 'pl_bj_gugong_thumb.png', 'pl_bj_tiantan.png'):   # the Tiantan thumbnail is missing
        (images / name).write_bytes(b'x')
    assert importer.read_image_ids(images) == {'pl_bj_gugong'}
    assert importer.read_image_ids(tmp_path / 'nowhere') == set()
    by_city, rejected, notes = importer.process(box, TODAY, library_dir=tmp_path / 'none')
    out, review, preview = tmp_path / 'out', tmp_path / 'review', tmp_path / 'preview'
    importer.write_outputs(by_city, rejected, notes, TODAY, out, review, 25, importer.read_image_ids(images), images, preview)
    rows = list(csv.DictReader(io.StringIO((review / 'beijing.review.csv').read_text(encoding='utf-8-sig'))))
    assert {row['id']: row['示意图'] for row in rows} == {'pl_bj_gugong': '有', 'pl_bj_tiantan': ''}
    assert '示意图：有' in (review / 'beijing.review.md').read_text(encoding='utf-8')
    page = (preview / 'beijing.preview.html').read_text(encoding='utf-8')
    assert page.count('_thumb.png') == 1 and 'pl_bj_gugong_thumb.png' in page and '示意图' in page
    assert str(tmp_path) not in (review / 'beijing.review.md').read_text(encoding='utf-8')      # the repository files name no local path


# ---------------------------------------------------------------- review table

def _many(count):
    return [second(id=f'pl_bj_p{i:03d}', name_zh=f'地点{i}', name_en=f'Place {i}', aliases_zh=[], aliases_en=[],
                   tier='main' if i % 5 else 'backup') for i in range(count)]


def test_review_table_batches_main_first_and_by_score(tmp_path):
    box = inbox(tmp_path, C1__beijing=_many(60))
    by_city, _, _ = importer.process(box, TODAY, library_dir=tmp_path / 'none')
    rows = importer.review_rows(by_city['beijing'], 25)
    assert [r['batch'] for r in rows] == [1] * 25 + [2] * 25 + [3] * 10
    tiers = [r['tier'] for r in rows]
    assert tiers == sorted(tiers, key=lambda t: t != 'main')                  # all main entries come before any backup


def test_review_csv_is_safe_to_open_in_a_spreadsheet(tmp_path):
    evil = second(name_zh='=HYPERLINK("http://x")', name_en='+cmd', id='pl_bj_evil', aliases_zh=[], notes=None)
    by_city, _, _ = importer.process(inbox(tmp_path, C1__beijing=[evil]), TODAY, library_dir=tmp_path / 'none')
    rows = list(csv.reader(io.StringIO(importer.render_csv(importer.review_rows(by_city['beijing'], 25)))))
    assert rows[0][-3:] == ['decision', 'rank', 'note'] and rows[1][-3:] == ['', '', '']
    assert rows[1][6].startswith("'=") and rows[1][7].startswith("'+")


def test_outputs_are_written_and_the_markdown_lists_each_entry(tmp_path):
    by_city, rejected, notes = importer.process(inbox(tmp_path, C1__beijing=[C1, second(lat=3)]), TODAY, fake_fetch([poi('故宫博物院')]),
                                                library_dir=tmp_path / 'none')
    written = importer.write_outputs(by_city, rejected, notes, TODAY, tmp_path / 'out', tmp_path / 'review', 25)
    assert written == [('beijing', 1, 1)]
    md = (tmp_path / 'review' / 'beijing.review.md').read_text(encoding='utf-8')
    assert '故宫博物院' in md and '名称一致' in md and '- [ ] accept' in md and '第 1 批' in md
    assert (tmp_path / 'review' / 'beijing.review.csv').read_bytes().startswith(b'\xef\xbb\xbf')   # Excel reads UTF-8
    assert json.loads((tmp_path / 'out' / f'rejected-{TODAY}.json').read_text(encoding='utf-8'))['rejected'][0]['id'] == 'pl_bj_tiantan'


def test_live_run_needs_the_key_in_the_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('CJ_AMAP_WEB_KEY', raising=False)
    assert importer.main(['--inbox', str(tmp_path), '--today', TODAY, '--live', '--out', str(tmp_path / 'o'), '--review', str(tmp_path / 'r')]) == 2
    assert 'CJ_AMAP_WEB_KEY' in capsys.readouterr().err


# ---------------------------------------------------------------- review fixes (#2021)

def test_cells_that_start_with_tab_or_return_are_quoted_too():
    assert importer._cell('\t=1+1').startswith("'") and importer._cell('\r@x').startswith("'") and importer._cell('plain') == 'plain'


def test_a_reimport_keeps_what_the_reviewer_already_typed(tmp_path):
    box = inbox(tmp_path, C1__beijing=[C1, second()])
    out, review = tmp_path / 'out', tmp_path / 'review'
    first, rejected, notes = importer.process(box, TODAY, library_dir=tmp_path / 'none')
    importer.write_outputs(first, rejected, notes, TODAY, out, review, 25)
    table = review / 'beijing.review.csv'
    rows = list(csv.reader(io.StringIO(table.read_text(encoding='utf-8-sig'))))
    for row in rows[1:]:
        if row[1] == 'pl_bj_gugong':
            row[-3:] = ['accept', '1', '已读简介']
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator='\n').writerows(rows)
    table.write_text(buffer.getvalue(), encoding='utf-8-sig')
    again, rejected, notes = importer.process(box, TODAY, fake_fetch([poi('故宫博物院')]), library_dir=tmp_path / 'none', existing=importer.load_existing(out))
    importer.write_outputs(again, rejected, notes, TODAY, out, review, 25)
    answers = importer.read_filled(table)
    assert answers == {'pl_bj_gugong': ('accept', '1', '已读简介')}
    assert any(row[1] == 'pl_bj_tiantan' and row[-3:] == ['', '', ''] for row in csv.reader(io.StringIO(table.read_text(encoding='utf-8-sig'))))


class _Response:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def test_a_refusal_is_not_cached_and_the_key_is_scrubbed_everywhere(tmp_path, monkeypatch):
    answers = [{'status': '0', 'info': 'DAILY_QUERY_OVER_LIMIT', 'infocode': '10003'}, {'status': '1', 'pois': []}]
    seen = []

    def fake_urlopen(request, timeout=0):
        seen.append(request.full_url)
        return _Response(json.dumps(answers[min(len(seen) - 1, 1)]).encode('utf-8'))
    monkeypatch.setattr(amap, 'urlopen', fake_urlopen)
    fetch = amap.make_fetch(SECRET, cache_dir=tmp_path / 'cache', pause=0)
    assert fetch('/v3/place/text', {'keywords': 'x'})['status'] == '0'
    assert list((tmp_path / 'cache').glob('*.json')) == []                 # the quota refusal was not remembered
    assert fetch('/v3/place/text', {'keywords': 'x'})['status'] == '1'     # the same request asks Amap again
    assert len(list((tmp_path / 'cache').glob('*.json'))) == 1
    assert SECRET not in ''.join(p.read_text(encoding='utf-8') for p in (tmp_path / 'cache').glob('*.json'))


def test_network_errors_and_encoded_keys_never_reach_the_message(tmp_path, monkeypatch):
    odd_key = 'a b/c+d'

    def boom(request, timeout=0):
        raise OSError(f'cannot reach {request.full_url}')
    monkeypatch.setattr(amap, 'urlopen', boom)
    with pytest.raises(amap.AmapError) as error:
        amap.make_fetch(odd_key, pause=0)('/v3/place/text', {'keywords': 'x'})
    assert odd_key not in str(error.value) and 'a%20b%2Fc%2Bd' not in str(error.value)


def test_external_signals_are_not_written_into_candidates_unless_asked(tmp_path):
    """The repository is public and the terms for Tripadvisor-style numbers are not settled: they stay in the inbox."""
    box = inbox(tmp_path, C1__beijing=[C1])
    plain = importer.process(box, TODAY, library_dir=tmp_path / 'none')[0]['beijing'][0]
    assert plain['external_signals'] == [] and 'tripadvisor' not in json.dumps(plain)
    kept = importer.process(box, TODAY, library_dir=tmp_path / 'none', keep_signals=True)[0]['beijing'][0]
    assert kept['external_signals'] and kept['external_signals'][0]['source'] == 'tripadvisor'
    used = importer.process(box, TODAY, library_dir=tmp_path / 'none', use_external=True)[0]['beijing'][0]
    assert used['external_signals'] and used['score']['external_used']


def test_side_files_in_the_draft_folders_are_not_drafts(tmp_path):
    box = inbox(tmp_path, C1__beijing=[C1], C8__beijing_hotel=[], C8__intro_rewrite_sources=[{'id': 'pl_bj_x', 'urls': ['https://x.example/'], 'checked_on': TODAY}])
    (box / 'C1' / 'notes.json').write_text('{"not": "a list of places"}', encoding='utf-8')
    by_city, rejected, _ = importer.process(box, TODAY, library_dir=tmp_path / 'none')
    assert rejected == [] and [c['id'] for c in by_city['beijing']] == ['pl_bj_gugong']


def test_a_clean_rerun_removes_the_old_rejected_report(tmp_path):
    out, review = tmp_path / 'out', tmp_path / 'review'
    bad = importer.process(inbox(tmp_path, C1__beijing=[C1, second(lat=3)]), TODAY, library_dir=tmp_path / 'none')
    importer.write_outputs(*bad, TODAY, out, review, 25)
    assert (out / f'rejected-{TODAY}.json').is_file()
    good = importer.process(inbox(tmp_path, C1__beijing=[C1, second()]), TODAY, library_dir=tmp_path / 'none')
    importer.write_outputs(*good, TODAY, out, review, 25)
    assert not (out / f'rejected-{TODAY}.json').exists()
