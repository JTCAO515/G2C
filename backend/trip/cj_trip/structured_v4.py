"""Additive rich itinerary grammar; no publisher, source acquisition or solver."""
from copy import deepcopy
import json
from math import isfinite

from cj_place.models import Coordinate, identifier as provider_id
from cj_strict_json import reject_duplicates
from .domain import packed
from .rich_source import FACTORS, source_ref
from .structured import FieldRejected, SourceRejected, _fields, _text
from .structured_v3 import validate_document as validate_v3

VERSION = 'structured.4'
KINDS = ('sight', 'meal', 'hotel', 'transport', 'free_time')
MODES = ('walking', 'transit', 'taxi')
ITEM_EXTRA = {'kind', 'place', 'note', 'tip', 'reason_refs'}


def _optional_text(value):
    if value is not None:
        _text(value, 500)


def _refs(refs):
    if (type(refs) is not list or len(refs) > len(FACTORS)
            or any(type(r) is not str or r not in FACTORS for r in refs) or len(set(refs)) != len(refs)):
        raise FieldRejected('reason_refs', 'distinct declared factor keys required')


def _coordinate(value):
    _fields(value, {'raw', 'longitude', 'latitude', 'crs'}, 'place.coordinate', 'lossless provider coordinate required')
    coordinate = Coordinate(value['raw'])
    if value != dict(raw=coordinate.raw, longitude=str(coordinate.longitude),
                     latitude=str(coordinate.latitude), crs='GCJ-02'):
        raise SourceRejected('place.coordinate', 'raw GCJ-02 only; no conversion or rounding')


def _place(place):
    _fields(place, {'state', 'amap_id', 'name_zh', 'name_en', 'name_en_source', 'coordinate',
                    'coordinate_role', 'address', 'source'}, 'place', 'exact rich place required')
    _text(place['name_zh'], 500); _text(place['name_en'], 500)
    _optional_text(place['address'])
    if place['name_en_source'] is not None:
        source_ref(place['name_en_source'])
        if place['name_en_source']['kind'] != 'name':
            raise SourceRejected('place.name_en_source', 'explicit name observation required')
    if place['state'] == 'unconfirmed':
        if any(place[k] is not None for k in ('amap_id', 'coordinate', 'coordinate_role', 'address', 'source')):
            raise SourceRejected('place', 'unconfirmed place cannot invent provider fields')
    elif place['state'] == 'matched':
        provider_id(place['amap_id'])
        _coordinate(place['coordinate'])
        if place['coordinate_role'] not in ('poi_center', 'entrance', 'exit'):
            raise SourceRejected('place.coordinate_role', 'actual provider coordinate role required')
        source_ref(place['source'])
        if place['source']['provider'] != 'amap' or place['source']['kind'] != 'place':
            raise SourceRejected('place.source', 'Gaode place observation required')
    else:
        raise FieldRejected('place.state', 'matched or unconfirmed place required')


def _number(value):
    if (type(value) not in (int, float) or value < 0
            or type(value) is float and not isfinite(value)):
        raise FieldRejected('legs', 'finite nonnegative observed quantity required')


def parse(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 1_000_000:
        raise FieldRejected('document', 'bounded rich content bytes required')
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate rich field'))
    except (ValueError, RecursionError):
        raise FieldRejected('document', 'strict complete rich JSON required') from None
    validate_document(value)
    return value


def calendar_validation_view(document):
    """Private validation copy only; never store/project S4 as an older version."""
    result = {k: deepcopy(document[k]) for k in
              ('title', 'calendar', 'days', 'items', 'sources', 'date_checks')}
    result['content_version'] = 'structured.3'
    for day in result['days']:
        for key in ('theme', 'area'):
            day.pop(key)
    for item in result['items']:
        for key in ITEM_EXTRA:
            item.pop(key)
    return result


def adjacent_pairs(document):
    pairs = []
    for day in document['days']:
        ids = [i['id'] for i in document['items'] if i['schedule']['start']['day_index'] == day['day_index']]
        pairs.extend((day['day_index'], a, b) for a, b in zip(ids, ids[1:]))
    return pairs


def validate_document(document):
    """Shape/internal consistency only. Conditional provenance is checked below."""
    _fields(document, {'content_version', 'title', 'calendar', 'days', 'items', 'sources',
                       'date_checks', 'legs', 'lodging'}, 'document', 'exact structured.4 document required')
    if document['content_version'] != VERSION:
        raise FieldRejected('content_version', 'structured.4 required')
    if type(document['calendar']) is not dict:
        raise FieldRejected('calendar', 'explicit calendar required')
    if type(document['days']) is not list or not document['days'] or type(document['items']) is not list:
        raise FieldRejected('document', 'explicit calendar days and items required')
    for day in document['days']:
        expected = {'day_index', 'theme', 'area'} | ({'date'} if document['calendar'].get('state') == 'dated' else set())
        _fields(day, expected, 'days', 'exact rich day required')
        _text(day['theme'], 500); _text(day['area'], 500)
    for item in document['items']:
        _fields(item, {'id', 'text', 'verification', 'evidence', 'schedule', 'fixed', 'source_category', 'source_refs'} | ITEM_EXTRA,
                'items', 'exact rich item required')
        if item['kind'] not in KINDS:
            raise FieldRejected('items.kind', 'explicit proposed item kind required')
        _place(item['place']); _optional_text(item['note']); _refs(item['reason_refs'])
        tip = item['tip']
        if tip is not None:
            _fields(tip, {'text', 'source'}, 'items.tip', 'exact tip required')
            _text(tip['text'], 500)
            if tip['source'] is not None:
                source_ref(tip['source'])
                if tip['source']['provider'] != 'visitor' or tip['source']['kind'] != 'tip':
                    raise SourceRejected('items.tip', 'H entry source required')
    validate_v3(calendar_validation_view(document))
    legs = document['legs']
    if type(legs) is not list or len(legs) > 60:
        raise FieldRejected('legs', 'bounded explicit adjacent legs required')
    actual = []
    for leg in legs:
        _fields(leg, {'day_index', 'from_item_id', 'to_item_id', 'state', 'mode', 'duration_seconds',
                      'distance_m', 'source', 'time_semantics', 'future_guaranteed'}, 'legs', 'exact leg required')
        actual.append((leg['day_index'], leg['from_item_id'], leg['to_item_id']))
        if type(leg['day_index']) is not int or leg['time_semantics'] != 'provider_estimate_at_query_time' or leg['future_guaranteed'] is not False:
            raise SourceRejected('legs', 'explicit day and non-guaranteed estimate semantics required')
        if leg['state'] == 'unconfirmed':
            if any(leg[k] is not None for k in ('mode', 'duration_seconds', 'distance_m', 'source')):
                raise SourceRejected('legs', 'unconfirmed leg cannot invent a route or estimate')
        elif leg['state'] == 'estimated':
            if leg['mode'] not in MODES:
                raise FieldRejected('legs.mode', 'supported observed route mode required')
            _number(leg['duration_seconds']); _number(leg['distance_m']); source_ref(leg['source'])
            if leg['source']['provider'] != 'amap' or leg['source']['kind'] != 'route':
                raise SourceRejected('legs.source', 'Gaode route observation required')
        else:
            raise FieldRejected('legs.state', 'estimated or unconfirmed route required')
    if actual != adjacent_pairs(document):
        raise SourceRejected('legs', 'all and only consecutive same-day item pairs required in order')
    lodging = document['lodging']
    _fields(lodging, {'area', 'recommendations'}, 'lodging', 'area and hotel recommendations only')
    _text(lodging['area'], 500)
    if type(lodging['recommendations']) is not list or not 2 <= len(lodging['recommendations']) <= 3:
        raise FieldRejected('lodging.recommendations', 'two or three recommendations required')
    for hotel in lodging['recommendations']:
        _fields(hotel, {'place', 'note', 'reason_refs'}, 'lodging.recommendations', 'no price or booking fields permitted')
        _place(hotel['place']); _optional_text(hotel['note']); _refs(hotel['reason_refs'])
    if len(packed(document)) > 1_000_000:
        raise FieldRejected('document', 'bounded Trip content required')


def validate_candidate(document, source):
    """Check model claims against the separate captured inputs before publication.

    The actual publisher must still hold original AUTH/source/Trip/clock/Meter
    eligibility and sole commit. This function grants none of those capabilities.
    """
    validate_document(document)
    for check in document['date_checks']:
        source.date_check(check)
    def check_place(place):
        if place['state'] == 'matched':
            payload = source.observation(place['source'], 'place')
            expected = {k: place[k] for k in ('amap_id', 'name_zh', 'coordinate', 'coordinate_role', 'address')}
            if packed(payload) != packed(expected):
                raise SourceRejected('place', 'place fields differ from captured provider observation')
        if place['name_en_source'] is not None:
            names = source.observation(place['name_en_source'], 'name')
            if names != {k: place[k] for k in ('name_zh', 'name_en')}:
                raise SourceRejected('place.name_en', 'name fields differ from captured reviewed names')
    items = {i['id']: i for i in document['items']}
    for item in document['items']:
        base = {k: v for k, v in item.items() if k not in ITEM_EXTRA}
        if (item['verification'] != 'pending' or item['evidence']) and not source.retained_base(base):
            raise SourceRejected('items.verification', 'new model content cannot grant factual verification')
        if (item['fixed'] == {'state': 'known', 'value': True} or item['source_category'] != 'unknown') and not source.protected_base(base):
            raise SourceRejected('items.source_category', 'original protected fixed/retained item required')
        check_place(item['place'])
        for factor in item['reason_refs']: source.reason(factor)
        if item['tip'] is not None and item['tip']['source'] is not None:
            tip = source.observation(item['tip']['source'], 'tip')
            if item['id'] not in tip['item_ids'] or tip['subject_key'] is not None and (
                    item['place']['state'] != 'matched' or item['place']['amap_id'] not in tip['amap_ids']):
                raise SourceRejected('items.tip', 'H entry does not apply to this item/provider identity')
    for hotel in document['lodging']['recommendations']:
        check_place(hotel['place'])
        for factor in hotel['reason_refs']: source.reason(factor)
    for leg in document['legs']:
        if leg['state'] != 'estimated': continue
        a, b = (items[leg[k]]['place'] for k in ('from_item_id', 'to_item_id'))
        if a['state'] != 'matched' or b['state'] != 'matched':
            raise SourceRejected('legs', 'observed routes need actual matched endpoints')
        expected = dict(from_amap_id=a['amap_id'], to_amap_id=b['amap_id'],
            from_coordinate=a['coordinate'], to_coordinate=b['coordinate'],
            from_coordinate_role=a['coordinate_role'], to_coordinate_role=b['coordinate_role'],
            mode=leg['mode'], duration_seconds=leg['duration_seconds'], distance_m=leg['distance_m'])
        if packed(source.observation(leg['source'], 'route')) != packed(expected):
            raise SourceRejected('legs', 'route endpoints, roles, mode or estimate differ from original')
