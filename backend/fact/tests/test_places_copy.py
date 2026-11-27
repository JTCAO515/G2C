"""The server copies of the place library are the sources, byte for byte, and read back strictly (#1985)."""
import importlib.util
import json
from pathlib import Path

import pytest

from cj_fact import places
from cj_fact.policy import FactFailure

ROOT = Path(__file__).resolve().parents[3]


def generator():
    spec = importlib.util.spec_from_file_location('places_generate', ROOT / 'knowledge/places/generate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_server_copy_is_byte_identical_to_its_source():
    module = generator()
    assert module.LAYOUT.server_dir == ROOT / 'backend/fact/cj_fact'
    for city in places.CITIES:
        source, copy = ROOT / f'knowledge/places/{city}.v1.json', places.path_for(city)
        assert source.is_file() == copy.is_file(), f'{city}: run python3 -B knowledge/places/validate.py --write'
        if source.is_file():
            assert copy.read_bytes() == source.read_bytes()
            assert places.load_city(city)['city'] == city


def test_city_tables_agree_with_the_generator():
    module = generator()
    assert module.placelib.CITIES == places.CITIES
    assert module.placelib.VERSION == places.VERSION
    assert set(module.placelib.CATEGORIES) == places.CATEGORIES


def _doc(**change):
    entry = {'id': 'pl_bj_a', 'city': 'beijing', 'category': 'attraction', 'rank': 2, 'name_zh': '甲', 'name_en': 'Alpha',
             'aliases_zh': ['甲地'], 'aliases_en': ['The Alpha']}
    return {'version': places.VERSION, 'city': 'beijing',
            'places': [entry, {**entry, 'id': 'pl_bj_b', 'rank': 1, 'name_zh': '乙', 'name_en': 'Beta', 'aliases_zh': [], 'aliases_en': []},
                       {**entry, 'id': 'pl_bj_c', 'rank': None, 'name_zh': '丙', 'name_en': 'Gamma', 'aliases_zh': [], 'aliases_en': [], 'category': 'food'}],
            **change}


def write(tmp_path, doc, name='places_beijing.v1.json'):
    path = tmp_path / name
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
    return path


def test_selectors(tmp_path):
    doc = places.load_city('beijing', write(tmp_path, _doc()))
    assert places.by_id(doc, 'pl_bj_b')['name_en'] == 'Beta' and places.by_id(doc, 'pl_bj_x') is None
    assert [p['id'] for p in places.by_category(doc, 'attraction')] == ['pl_bj_b', 'pl_bj_a']
    assert places.match_name(doc, 'the alpha')['id'] == 'pl_bj_a'
    assert places.match_name(doc, '甲地')['id'] == 'pl_bj_a'
    assert places.match_name(doc, 'Alph') is None


@pytest.mark.parametrize('mutate', [
    lambda d: d.update(version='g2c-places.2'),
    lambda d: d.update(city='shanghai'),
    lambda d: d.update(extra=1),
    lambda d: d.update(places={}),
    lambda d: d['places'][0].update(id='pl_sh_a'),
    lambda d: d['places'][1].update(id='pl_bj_a'),   # duplicate id
    lambda d: d['places'][0].update(category='museum'),
    lambda d: d['places'][0].update(city='shanghai'),
])
def test_a_reshaped_copy_fails_closed(tmp_path, mutate):
    doc = _doc()
    mutate(doc)
    with pytest.raises(FactFailure):
        places.load_city('beijing', write(tmp_path, doc))


def test_missing_oversized_or_duplicate_key_copy_fails_closed(tmp_path):
    with pytest.raises(FactFailure):
        places.load_city('beijing', tmp_path / 'absent.json')
    with pytest.raises(FactFailure):
        places.load_city('atlantis')
    path = write(tmp_path, _doc())
    path.write_text(path.read_text(encoding='utf-8').replace('"version"', '"version": "x", "version"', 1), encoding='utf-8')
    with pytest.raises(FactFailure):
        places.load_city('beijing', path)
