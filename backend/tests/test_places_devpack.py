"""The unreviewed development pack: reproducible from the candidates, validated, and never wired into production (#1985)."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'knowledge/places'))
sys.path.insert(0, str(ROOT / 'backend/tests'))
import devpack  # noqa: E402
import placelib  # noqa: E402
from cj_fact import places_dev  # noqa: E402
from cj_fact.policy import FactFailure  # noqa: E402
from test_places_import import C1, TODAY, fake_fetch, inbox, poi, second  # noqa: E402
import import_drafts as importer  # noqa: E402


def candidates(tmp_path, entries, fetch=None):
    by_city, rejected, notes = importer.process(inbox(tmp_path, C1__beijing=entries), TODAY, fetch, library_dir=tmp_path / 'none')
    importer.write_outputs(by_city, rejected, notes, TODAY, tmp_path / 'cand', tmp_path / 'review', 25)
    return tmp_path / 'cand'


def test_pack_is_built_from_pending_candidates_only(tmp_path):
    cand = candidates(tmp_path, [C1, second()], fake_fetch([poi('故宫博物院')]))
    path = cand / 'beijing.cand.json'
    doc = json.loads(path.read_text(encoding='utf-8'))
    doc['candidates'][1]['status'] = 'rejected'
    path.write_text(importer.dumps(doc), encoding='utf-8')
    pack = devpack.build(cand)
    assert [p['id'] for p in pack['places']] == ['pl_bj_gugong'] and pack['warning'] == devpack.WARNING
    entry = pack['places'][0]
    assert entry['review'] == devpack.UNREVIEWED and entry['rank'] is None and entry['location']['amap_id'] == 'B000A8UIN8'
    assert 'external_signals' not in entry
    devpack.validate(pack)


def test_candidates_without_amap_have_a_null_location_and_still_validate(tmp_path):
    pack = devpack.build(candidates(tmp_path, [C1]))
    assert pack['places'][0]['location'] is None
    devpack.validate(pack)


@pytest.mark.parametrize('change', [
    lambda p: p['places'][0].update(review={'status': 'approved', 'reviewer': 'JT', 'reviewed_on': '2026-11-30', 'note': None}),
    lambda p: p['places'][0].update(rank=3),
    lambda p: p['places'][0].update(extra=1),
    lambda p: p.update(warning='fine'),
    lambda p: p['places'][0].update(sources=['https://www.tripadvisor.com/x']),
    lambda p: p['places'][0].update(location={'gcj02': {'lat': 0, 'lng': 0}, 'amap_id': None, 'amap_name': None, 'method': 'manual', 'geocoded_on': '2026-11-27'}),
    lambda p: p.update(places=list(reversed(p['places']))),
])
def test_pack_validation_rejects_anything_that_looks_reviewed_or_malformed(tmp_path, change):
    pack = devpack.build(candidates(tmp_path, [C1, second()]))
    change(pack)
    with pytest.raises(placelib.Invalid):
        devpack.validate(pack)


def test_stale_detection_and_write(tmp_path):
    cand = candidates(tmp_path, [C1])
    pack = tmp_path / 'dev' / 'pack.json'
    assert devpack.stale(pack, cand)                       # missing
    devpack.write(pack, cand)
    assert devpack.stale(pack, cand) == []
    pack.write_text(pack.read_text(encoding='utf-8').replace('故宫博物院', '故宫博物馆', 1), encoding='utf-8')
    assert devpack.stale(pack, cand)
    shutil_empty = tmp_path / 'none'
    assert devpack.write(pack, shutil_empty) is None and not pack.exists()    # no candidates: no pack


# ---------------------------------------------------------------- the server reader needs two opt-ins

def _pack_file(tmp_path):
    pack = devpack.build(candidates(tmp_path, [C1, second()]))
    path = tmp_path / 'pack.json'
    path.write_text(devpack.dumps(pack), encoding='utf-8')
    return path


@pytest.mark.parametrize('environ', [{}, {'CJ_PLACES_DEV_ENABLED': '1'}, {'CJ_PLACES_DEV_ENABLED': 'true', 'CJ_PLACES_DEV_PACK': 'x'},
                                      {'CJ_PLACES_DEV_PACK': 'x'}])
def test_reader_is_off_without_both_opt_ins(environ):
    with pytest.raises(FactFailure) as error:
        places_dev.load(environ)
    assert str(error.value).endswith('places_dev_disabled') or 'places_dev_disabled' in repr(error.value)


def test_reader_selectors_and_refusals(tmp_path):
    path = _pack_file(tmp_path)
    doc = places_dev.load({'CJ_PLACES_DEV_ENABLED': '1', 'CJ_PLACES_DEV_PACK': str(path)})
    assert places_dev.by_id(doc, 'pl_bj_tiantan')['name_en'] == 'Temple of Heaven'
    assert places_dev.match_name(doc, '紫禁城', city='beijing')['id'] == 'pl_bj_gugong'
    assert places_dev.match_name(doc, '紫禁城', city='shanghai') is None
    assert len(places_dev.by_city(doc, 'beijing', 'attraction')) == 2
    broken = json.loads(path.read_text(encoding='utf-8'))
    broken['places'][0]['review']['status'] = 'approved'
    path.write_text(json.dumps(broken, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(FactFailure):
        places_dev.load({'CJ_PLACES_DEV_ENABLED': '1', 'CJ_PLACES_DEV_PACK': str(path)})
    with pytest.raises(FactFailure):
        places_dev.load({'CJ_PLACES_DEV_ENABLED': '1', 'CJ_PLACES_DEV_PACK': str(tmp_path / 'absent.json')})


# ---------------------------------------------------------------- never in production

def test_the_pack_is_not_shipped_with_the_server_or_the_app():
    pack_name = devpack.PACK.name
    shipped = ROOT / 'backend/fact/cj_fact'
    assert not list(shipped.glob('*dev*pack*')) and not list(shipped.glob('places_dev*.json'))
    package = (ROOT / 'ios/Modules/CJShell/Package.swift').read_text(encoding='utf-8')
    assert 'PlacesDev' not in package and pack_name not in package, 'the development pack must not be a bundled App resource'
    assert not list((ROOT / 'ios').rglob(pack_name))


def test_xcode_project_and_backend_code_do_not_reference_the_development_pack():
    project = (ROOT / 'ios/CJProbeApp.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
    assert 'places-dev' not in project and 'LioPlacesDev' not in project.replace('LioPlacesDevPack.swift', '')
    for path in (ROOT / 'backend').rglob('*.py'):
        relative = path.relative_to(ROOT).as_posix()
        if '/tests/' in relative or path.name in ('places_dev.py', 'test_places_devpack.py'):
            continue
        assert 'places_dev' not in path.read_text(encoding='utf-8'), f'{relative} must not use the development place reader'


def test_candidates_carry_no_third_party_scores():
    for path in devpack.CANDIDATES.glob('*.cand.json'):
        for cand in json.loads(path.read_text(encoding='utf-8'))['candidates']:
            assert cand['external_signals'] == [], f'{cand["id"]}: external signals must stay in the inbox until the terms are settled'


def test_no_deploy_file_enables_the_development_reader():
    for folder in ('deploy', '.github', 'tooling'):
        for path in (ROOT / folder).rglob('*'):
            if path.is_file() and path.stat().st_size < 2_000_000:
                try:
                    text = path.read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    continue
                assert 'CJ_PLACES_DEV' not in text, f'{path} must not enable the development place pack'


def test_committed_pack_is_in_step_with_the_candidates():
    assert devpack.stale() == [], 'run python3 -B knowledge/places/validate.py --write'
