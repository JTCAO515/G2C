"""Guangzhou business knowledge entries: each has official sources, a check day and a review deadline (#1759)."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('business_knowledge', ROOT / 'knowledge/business/validate.py')
knowledge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(knowledge)
CATALOGUE = ROOT / 'knowledge/business/guangzhou.v1.json'


def test_catalogue_is_valid_and_covers_the_four_business_topics():
    doc = knowledge.load(CATALOGUE)
    assert doc['city'] == 'guangzhou'
    assert {entry['topic'] for entry in doc['entries']} == knowledge.TOPICS
    for entry in doc['entries']:
        assert entry['source_urls'] and entry['checked_on'] < entry['expires_on'], entry['id']


def test_visa_entry_only_points_to_official_channels():
    doc = knowledge.load(CATALOGUE)
    visa = next(entry for entry in doc['entries'] if entry['topic'] == 'visa_channel')
    assert '以中国驻外使领馆和国家移民管理局的最新公布为准' in visa['text_zh']
    assert 'www.nia.gov.cn' in {url.split('/')[2] for url in visa['source_urls']}


def _broken(tmp_path, change):
    doc = json.loads(CATALOGUE.read_text(encoding='utf-8'))
    change(doc, doc['entries'][0])
    path = tmp_path / 'catalogue.json'
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
    return path


@pytest.mark.parametrize('change', [
    lambda doc, entry: entry.update(source_urls=[]),
    lambda doc, entry: entry.update(source_urls=['https://www.trip.com/travel-guide/guangzhou/canton-fair']),
    lambda doc, entry: entry.update(source_urls=['http://www.cantonfair.org.cn/en-US/posts/1']),
    lambda doc, entry: entry.update(source_urls=['https://www.cantonfair.org.cn/']),
    lambda doc, entry: entry.update(checked_on='2026-12-10'),
    lambda doc, entry: entry.update(expires_on='2027-06-01'),
    lambda doc, entry: entry.update(checked_on='2026-02-30'),
    lambda doc, entry: entry.update(topic='visa_policy'),
    lambda doc, entry: entry.update(text_en=''),
    lambda doc, entry: entry.update(text_zh='第一行\n第二行'),
    lambda doc, entry: entry['title'].pop('en'),
    lambda doc, entry: entry.update(extra=True),
    lambda doc, entry: entry.update(id='business.shenzhen.canton-fair'),
    lambda doc, entry: doc['entries'].append(dict(entry)),
    lambda doc, entry: doc.update(city='shenzhen'),
])
def test_invalid_catalogue_is_rejected(tmp_path, change):
    with pytest.raises(knowledge.Invalid):
        knowledge.load(_broken(tmp_path, change))


def test_duplicate_json_key_is_rejected(tmp_path):
    raw = CATALOGUE.read_text(encoding='utf-8').replace('{', '{"version": "g2c-business-knowledge.1", ', 1)
    path = tmp_path / 'catalogue.json'
    path.write_text(raw, encoding='utf-8')
    with pytest.raises(knowledge.Invalid):
        knowledge.load(path)
