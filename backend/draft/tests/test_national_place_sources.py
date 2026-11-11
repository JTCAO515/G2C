"""City names are query data, never a C-side resolver or synthetic authority."""
import json
from types import SimpleNamespace

import pytest

from cj_place import Config, ORIGIN
from cj_place.local_source import LocalPlaceProducer
from cj_trip.domain import packed
from cj_draft.place_plan import build, choices
from test_place_plan import Capture, batch, model, stored


CITIES = [('chengdu', '成都', '104.000100,30.000100'), ('xian', '西安', '108.000100,34.000100'),
          ('shanghai', '上海', '121.000100,31.000100'), ('hangzhou', '杭州', '120.000100,30.000100'),
          ('chongqing', '重庆', '106.000100,29.000100'), ('shenzhen', '深圳', '114.000100,22.000100')]


class SyntheticCityPlaces(LocalPlaceProducer):
    def __init__(self, coordinate, tag):
        super().__init__(Config(ORIGIN, 4096, 16384, 5, 60))
        self.coordinate, self.tag = coordinate, tag

    def _response(self, query):
        return 200, dict(status='1', info='OK', infocode='10000', count='2', pois=[
            dict(id=f'SYNTH_{self.tag}_{index}', name='合成同名公园', location=self.coordinate,
                 address=query.city + '合成地址') for index in (1, 2)])


@pytest.mark.parametrize(('tag', 'city', 'coordinate'), CITIES)
def test_exact_offered_sources_keep_original_city_and_coordinates(tag, city, coordinate):
    capture = Capture()
    available = choices(batch(ref=tag, city=city, producer=SyntheticCityPlaces(coordinate, tag)))
    content, _, report = build(packed(model(capture, available)), capture, available, 'structured.2')
    document = json.loads(content)
    _, first = stored(document, 'b')
    _, second = stored(document, 'c')
    assert first['query']['city'] == second['query']['city'] == city
    assert first['place']['coordinate']['value']['raw'] == coordinate
    assert first['place']['provider_id'] != second['place']['provider_id']
    assert first['place']['official_name_en'] == {'state': 'unknown', 'value': None}
    assert document['items'][0]['fixed'] == {'state': 'known', 'value': True}
    assert report.status == 'UNKNOWN' and all(s['evidence_level'] == 'synthetic' for s in document['sources'])


def test_same_name_in_two_cities_is_not_merged_or_used_as_city_confirmation():
    batches = [batch(ref=tag, city=city, producer=SyntheticCityPlaces(point, tag))
               for tag, city, point in (CITIES[0], CITIES[2])]
    observations = tuple(SimpleNamespace(operation_key=f'tool.0.{index}', request_ref=row.request_ref,
                                         result=row.result)
                         for index, one in enumerate(batches) for row in one.observations)
    offered = choices(SimpleNamespace(observations=observations))
    available = (offered[0], offered[2])
    capture = Capture()
    content, _, _ = build(packed(model(capture, available)), capture, available, 'structured.2')
    document = json.loads(content)
    source_a, a = stored(document, 'b')
    source_b, b = stored(document, 'c')
    assert a['place']['name_zh'] == b['place']['name_zh']
    assert (a['query']['city'], b['query']['city']) == ('成都', '上海')
    assert source_a['id'] != source_b['id']
    # Destination/city disambiguation remains the host's responsibility.
    changed = model(capture, available)
    changed['items'][1]['text'] = 'Synthetic English alias'
    with pytest.raises(ValueError, match='exact provider name'):
        build(packed(changed), capture, available, 'structured.2')
