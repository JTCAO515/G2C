"""Shared field rules for the place library (#1985, F-3).

Two shapes live here:

* the **draft** shape: what Codex writes into `codex-inbox/C1|C7|C8/*.json` (field names and types are
  exactly `coord/codex/C1-attractions.md`, `C7-hubs-and-trains.md`, `C8-food-shop-hotel.md`). A draft is
  never trusted: `check_draft` reports problems, and the importer (`import/`, #1986) only carries the
  clean entries into a candidate file.
* the **library** shape: `knowledge/places/<city>.v1.json`, every field present, written only after a
  human review. It is the draft shape minus `external_signals` (internal scores never leave the
  candidate files) plus `location` (GCJ-02 + amap_id from the importer), `rank` and `review`.

Nothing here reads a clock or the network: calendar-day expiry is `scripts/fact_expiry.py`'s job.
"""
from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
PLACES_DIR = ROOT / 'knowledge/places'
VERSION = 'g2c-places.1'
APP_VERSION = 'g2c-places-app.1'

# City -> id abbreviation, and a generous GCJ-02 box (suburbs and day trips included) to catch a
# geocoder that answered with a namesake in another city. (south, north, west, east)
CITIES = {
    'beijing': 'bj', 'shanghai': 'sh', 'guangzhou': 'gz', 'shenzhen': 'sz', 'chengdu': 'cd', 'chongqing': 'cq',
}
CITY_BOXES = {
    'beijing': (39.40, 41.10, 115.40, 117.60),
    'shanghai': (30.60, 31.90, 120.80, 122.20),
    'guangzhou': (22.40, 24.00, 112.90, 114.20),
    'shenzhen': (22.35, 22.95, 113.70, 114.70),
    'chengdu': (30.00, 31.50, 102.90, 104.95),
    'chongqing': (28.10, 32.25, 105.20, 110.25),
}
CATEGORIES = ('attraction', 'food', 'shopping', 'hotel', 'hub')
ATTRACTION_SUBCATEGORIES = frozenset({'history', 'museum', 'park', 'street', 'landmark', 'experience'})
HUB_TYPES = frozenset({'airport', 'rail'})
PRICE_BANDS = frozenset({'<500', '500-1000', '1000-2000', '>2000'})
CONFIDENCE = frozenset({'high', 'medium', 'low'})
TIERS = frozenset({'main', 'backup'})
BOOKING = frozenset({'required', 'recommended', 'none'})
LOCATION_METHODS = frozenset({'amap-poi-search', 'amap-geocode', 'manual'})
REVIEW_STATUS = frozenset({'approved', 'retired'})

# Length limits are in characters and come from C1.
LIMITS = {'intro_short_zh': 40, 'intro_short_en': 90, 'intro_long_zh': 200, 'intro_long_en': 450}

# Travel, review and aggregator sites: a lead for a researcher, never an official source (C1 rule:
# "开放时间、门票、预约规则，只认官方来源"). The reviewer still confirms that what is left is official.
THIRD_PARTY_HOSTS = (
    'tripadvisor.', 'trip.com', 'ctrip.com', 'mafengwo.', 'dianping.com', 'meituan.com', 'xiaohongshu.com',
    'zhihu.com', 'wikipedia.org', 'baike.baidu.com', 'baike.com', 'google.', 'booking.com', 'agoda.com',
    'expedia.', 'klook.com', 'getyourguide.', 'viator.com', 'lonelyplanet.com', 'fliggy.com', 'qunar.com',
    'qyer.com', 'douban.com', 'yelp.com', 'facebook.com', 'instagram.com', 'youtube.com', 'reddit.com',
    'tiktok.com', 'douyin.com', 'xhslink.com', 'sohu.com', 'sina.com', 'toutiao.com', 'amap.com',
)

# Fields common to every category (draft shape). `external_signals` is draft-only.
BASE = (
    'id', 'city', 'category', 'tier', 'name_zh', 'name_en', 'aliases_zh', 'aliases_en', 'address_zh',
    'address_en', 'district_zh', 'nearest_metro', 'foreigner_signals', 'external_signals', 'official_url',
    'sources', 'checked_on', 'confidence', 'notes',
)
INTRO = ('intro_short_zh', 'intro_short_en', 'intro_long_zh', 'intro_long_en')
CATEGORY_FIELDS = {
    'attraction': ('subcategory', 'hours_zh', 'hours_source', 'ticket', *INTRO, 'visit_minutes', 'best_time_zh'),
    'food': ('subcategory', 'hours_zh', 'hours_source', *INTRO, 'cuisine_zh', 'price_per_person_cny',
             'english_menu', 'halal', 'vegetarian_friendly', 'reservation_needed'),
    'shopping': ('subcategory', 'hours_zh', 'hours_source', *INTRO),
    'hotel': ('subcategory', *INTRO, 'star', 'price_band', 'accepts_foreigners', 'foreign_service'),
    'hub': ('hub_type', 'code', 'terminals', 'to_city_zh', 'to_city_en', 'foreigner_tips_zh', 'foreigner_tips_en'),
}
# A draft must carry at least these (the rest default to null); the library carries everything.
DRAFT_REQUIRED = frozenset({'id', 'city', 'category', 'name_zh', 'name_en', 'sources', 'checked_on', 'confidence'})
LIBRARY_ONLY = ('location', 'rank', 'review')
LIBRARY_NONNULL = {
    'attraction': ('subcategory', 'address_zh', *INTRO),
    'food': ('subcategory', 'address_zh', *INTRO),
    'shopping': ('subcategory', 'address_zh', *INTRO),
    'hotel': ('subcategory', 'address_zh', 'price_band', 'accepts_foreigners', *INTRO),
    'hub': ('hub_type',),
}


class Invalid(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise Invalid(message)


def fields_for(category, library):
    """The ordered key list of one entry in the draft or library shape."""
    base = [key for key in BASE if not (library and key == 'external_signals')]
    keys = base + list(CATEGORY_FIELDS[category])
    if category == 'hub':
        keys = [k for k in keys if k != 'subcategory']
    return keys + (list(LIBRARY_ONLY) if library else [])


# ---------------------------------------------------------------- scalar rules

def text(value, where, limit=None, nullable=False):
    if value is None and nullable:
        return None
    _require(type(value) is str and value != '' and value.strip() == value
             and not any(ord(c) < 32 or ord(c) == 127 for c in value), f'{where}: one trimmed, non-empty line of text')
    _require(limit is None or len(value) <= limit, f'{where}: longer than {limit} characters')
    return value


def day(value, where, nullable=False):
    if value is None and nullable:
        return None
    _require(type(value) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) is not None, f'{where}: YYYY-MM-DD')
    try:
        date.fromisoformat(value)
    except ValueError:
        raise Invalid(f'{where}: not a calendar day') from None
    return value


def boolean(value, where, nullable=True):
    _require(type(value) is bool or (nullable and value is None), f'{where}: true, false or null')


def integer(value, where, low=0, high=None, nullable=True):
    if value is None and nullable:
        return
    _require(type(value) is int and value >= low and (high is None or value <= high), f'{where}: integer {low}..{high}')


def url(value, where, nullable=False, official=True, allow_http=False):
    """A plain https page (http too when `allow_http`: reference-only links nobody opens, such as an older
    government site that has no https). `official` also refuses the travel, review and aggregator hosts."""
    if value is None and nullable:
        return None
    text(value, where)
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise Invalid(f'{where}: not a URL') from None
    _require(parts.scheme in (('https', 'http') if allow_http else ('https',)) and bool(parts.hostname) and port is None and not parts.username
             and not parts.password and not parts.fragment and ' ' not in value, f'{where}: a plain {"http(s)" if allow_http else "https"} URL')
    if official:
        host = '.' + parts.hostname.lower().rstrip('.')  # a trailing dot is the same host
        for bad in THIRD_PARTY_HOSTS:
            hit = ('.' + bad) in host if bad.endswith('.') else host.endswith('.' + bad)
            _require(not hit, f'{where}: {parts.hostname} is a third-party site, not an official source')
    return value


def text_list(value, where, nullable=False, unique=True):
    if value is None and nullable:
        return
    _require(type(value) is list, f'{where}: a list')
    items = [text(item, f'{where}[{i}]') for i, item in enumerate(value)]
    _require(not unique or len({i.casefold() for i in items}) == len(items), f'{where}: duplicates')


def url_list(value, where, nullable=False, minimum=0, allow_http=False):
    if value is None and nullable:
        return
    _require(type(value) is list and len(value) >= minimum, f'{where}: a list of at least {minimum}')
    for i, item in enumerate(value):
        url(item, f'{where}[{i}]', allow_http=allow_http)
    _require(len(set(value)) == len(value), f'{where}: duplicates')


# ---------------------------------------------------------------- nested blocks

def _object(value, keys, where, nullable=False):
    if value is None and nullable:
        return False
    _require(type(value) is dict, f'{where}: an object')
    extra, missing = set(value) - set(keys), set(keys) - set(value)
    _require(not extra and not missing, f'{where}: keys must be exactly {sorted(keys)} (extra {sorted(extra)}, missing {sorted(missing)})')
    return True


def metro(value, where):
    if _object(value, ('station_zh', 'station_en', 'line', 'exit'), where, nullable=True):
        for key in ('station_zh', 'station_en', 'line', 'exit'):
            text(value[key], f'{where}.{key}', nullable=True)
        _require(value['station_zh'] is not None, f'{where}.station_zh: required when nearest_metro is given')


def foreigner_signals(value, where):
    if _object(value, ('english_signage', 'foreign_cards', 'english_service', 'evidence'), where, nullable=True):
        for key in ('english_signage', 'foreign_cards', 'english_service'):
            boolean(value[key], f'{where}.{key}')
        url_list(value['evidence'], f'{where}.evidence', nullable=True, allow_http=True)
        known = any(value[k] is not None for k in ('english_signage', 'foreign_cards', 'english_service'))
        _require(not known or value['evidence'], f'{where}: a stated signal needs an evidence URL')


def ticket(value, where):
    if _object(value, ('booking', 'passport_required', 'price_cny', 'closed_weekdays', 'booking_channel_zh', 'booking_url'),
               where, nullable=True):
        _require(value['booking'] is None or value['booking'] in BOOKING, f'{where}.booking')
        boolean(value['passport_required'], f'{where}.passport_required')
        integer(value['price_cny'], f'{where}.price_cny', 0, 100000)
        days = value['closed_weekdays']
        _require(days is None or (type(days) is list and len(set(days)) == len(days) and all(type(d) is int and 1 <= d <= 7 for d in days)),
                 f'{where}.closed_weekdays: ISO weekday numbers 1 (Monday) to 7 (Sunday) or null')
        text(value['booking_channel_zh'], f'{where}.booking_channel_zh', nullable=True)
        url(value['booking_url'], f'{where}.booking_url', nullable=True)


def foreign_service(value, where):
    """Hotel: what makes it ready for foreign guests (C8's `foreign_service`, as Codex delivers it)."""
    keys = ('english_front_desk', 'foreign_guest_share', 'foreign_guest_experience', 'international_brand', 'evidence_zh', 'evidence')
    if _object(value, keys, where, nullable=True):
        boolean(value['english_front_desk'], f'{where}.english_front_desk')
        for key in ('foreign_guest_share', 'foreign_guest_experience', 'international_brand', 'evidence_zh'):
            text(value[key], f'{where}.{key}', nullable=True)
        url_list(value['evidence'], f'{where}.evidence', nullable=True, allow_http=True)


def terminals(value, where):
    if value is None:
        return
    _require(type(value) is list, f'{where}: a list')
    for i, item in enumerate(value):
        # `note_en` is optional (C7 drafts have only the Chinese note; the App reads it when it is there)
        _object(item, ('name', 'note_zh', 'note_en') if type(item) is dict and 'note_en' in item else ('name', 'note_zh'), f'{where}[{i}]')
        text(item['name'], f'{where}[{i}].name')
        text(item['note_zh'], f'{where}[{i}].note_zh', nullable=True)
        if 'note_en' in item:
            text(item['note_en'], f'{where}[{i}].note_en', nullable=True)


def location(value, where, city):
    _object(value, ('gcj02', 'amap_id', 'amap_name', 'method', 'geocoded_on'), where)
    point = value['gcj02']
    _object(point, ('lat', 'lng'), f'{where}.gcj02')
    for key in ('lat', 'lng'):
        _require(type(point[key]) in (int, float) and not isinstance(point[key], bool), f'{where}.gcj02.{key}: a number')
    south, north, west, east = CITY_BOXES[city]
    _require(south <= point['lat'] <= north and west <= point['lng'] <= east,
             f'{where}.gcj02: ({point["lat"]}, {point["lng"]}) is outside the {city} box; the geocoder probably matched another place')
    _require(round(point['lat'], 6) == point['lat'] and round(point['lng'], 6) == point['lng'], f'{where}.gcj02: at most 6 decimals')
    _require(value['method'] in LOCATION_METHODS, f'{where}.method')
    if value['method'] == 'amap-poi-search':
        _require(type(value['amap_id']) is str and re.fullmatch(r'[0-9A-Za-z]{6,32}', value['amap_id']) is not None, f'{where}.amap_id: Amap id required for a POI match')
        text(value['amap_name'], f'{where}.amap_name')
    elif value['method'] == 'amap-geocode':
        _require(value['amap_id'] is None, f'{where}.amap_id: a geocode result has no POI id')
        text(value['amap_name'], f'{where}.amap_name', nullable=True)
    else:
        _require(value['amap_id'] is None or type(value['amap_id']) is str, f'{where}.amap_id')
        text(value['amap_name'], f'{where}.amap_name', nullable=True)
    day(value['geocoded_on'], f'{where}.geocoded_on')


def review(value, where):
    _object(value, ('status', 'reviewer', 'reviewed_on', 'note'), where)
    _require(value['status'] in REVIEW_STATUS, f'{where}.status')
    text(value['reviewer'], f'{where}.reviewer')
    day(value['reviewed_on'], f'{where}.reviewed_on')
    text(value['note'], f'{where}.note', nullable=True)


def external_signals(value, where):
    """Draft-only scores: kept in candidate files, never in the library."""
    if value is None:
        return
    _require(type(value) is list, f'{where}: a list')
    for i, item in enumerate(value):
        _object(item, ('source', 'metric', 'value', 'as_of', 'url'), f'{where}[{i}]')
        text(item['source'], f'{where}[{i}].source')
        text(item['metric'], f'{where}[{i}].metric')
        _require(type(item['value']) in (int, float) and not isinstance(item['value'], bool), f'{where}[{i}].value: a number')
        day(item['as_of'], f'{where}[{i}].as_of')
        url(item['url'], f'{where}[{i}].url', official=False)


# ---------------------------------------------------------------- one entry

def _check_fields(entry, category, where):
    """Type-check every field that is present (null is allowed unless a rule below says otherwise)."""
    names = ('name_zh', 'name_en', 'address_zh', 'address_en', 'district_zh', 'hours_zh', 'best_time_zh',
             'cuisine_zh', 'notes', 'subcategory', 'code')
    for key in names:
        if key in entry:
            text(entry[key], f'{where}.{key}', nullable=key not in ('name_zh', 'name_en'))
    for key, limit in LIMITS.items():
        if key in entry:
            text(entry[key], f'{where}.{key}', limit=limit, nullable=True)
    for key in ('aliases_zh', 'aliases_en'):
        if key in entry:
            text_list(entry[key], f'{where}.{key}', nullable=True)
    if 'official_url' in entry:
        url(entry['official_url'], f'{where}.official_url', nullable=True)
    if 'hours_source' in entry:
        url(entry['hours_source'], f'{where}.hours_source', nullable=True)
    if 'nearest_metro' in entry:
        metro(entry['nearest_metro'], f'{where}.nearest_metro')
    if 'foreigner_signals' in entry:
        foreigner_signals(entry['foreigner_signals'], f'{where}.foreigner_signals')
    if 'ticket' in entry:
        ticket(entry['ticket'], f'{where}.ticket')
    if 'external_signals' in entry:
        external_signals(entry['external_signals'], f'{where}.external_signals')
    if 'foreign_service' in entry:
        foreign_service(entry['foreign_service'], f'{where}.foreign_service')
    if 'terminals' in entry:
        terminals(entry['terminals'], f'{where}.terminals')
    for key in ('to_city_zh', 'to_city_en', 'foreigner_tips_zh', 'foreigner_tips_en'):
        if key in entry:
            text_list(entry[key], f'{where}.{key}', nullable=True)
    if 'visit_minutes' in entry:
        integer(entry['visit_minutes'], f'{where}.visit_minutes', 1, 1440)
    if 'price_per_person_cny' in entry:
        integer(entry['price_per_person_cny'], f'{where}.price_per_person_cny', 0, 100000)
    if 'star' in entry:
        integer(entry['star'], f'{where}.star', 1, 5)
    for key in ('english_menu', 'halal', 'vegetarian_friendly', 'reservation_needed', 'accepts_foreigners'):
        if key in entry:
            boolean(entry[key], f'{where}.{key}')
    if 'price_band' in entry:
        _require(entry['price_band'] is None or entry['price_band'] in PRICE_BANDS, f'{where}.price_band')
    if 'hub_type' in entry:
        _require(entry['hub_type'] is None or entry['hub_type'] in HUB_TYPES, f'{where}.hub_type')
    if 'subcategory' in entry and category == 'attraction' and entry['subcategory'] is not None:
        _require(entry['subcategory'] in ATTRACTION_SUBCATEGORIES, f'{where}.subcategory: one of {sorted(ATTRACTION_SUBCATEGORIES)}')
    if 'subcategory' in entry and category in ('food', 'shopping', 'hotel') and entry['subcategory'] is not None:
        _require(re.fullmatch(r'[a-z][a-z0-9_]{1,31}', entry['subcategory']) is not None, f'{where}.subcategory: a lowercase slug')
    if 'tier' in entry:
        _require(entry['tier'] in TIERS, f'{where}.tier: main or backup')
    if 'confidence' in entry:
        _require(entry['confidence'] in CONFIDENCE, f'{where}.confidence')
    if 'checked_on' in entry:
        day(entry['checked_on'], f'{where}.checked_on')
    if 'sources' in entry:
        url_list(entry['sources'], f'{where}.sources', minimum=1, allow_http=True)


def _check_identity(entry, where):
    city, category = entry['city'], entry['category']
    _require(city in CITIES, f'{where}.city: one of {sorted(CITIES)}')
    _require(category in CATEGORIES, f'{where}.category: one of {list(CATEGORIES)}')
    _require(type(entry['id']) is str and re.fullmatch(rf'pl_{CITIES[city]}_[a-z0-9]+(_[a-z0-9]+)*', entry['id']) is not None,
             f'{where}.id: pl_{CITIES[city]}_<short_name> in lowercase and underscores')


def check_draft(entry, where='entry'):
    """Problems of one draft entry (C1/C7/C8 shape): (errors, warnings). An entry with errors is not imported."""
    errors, warnings = [], []
    try:
        _require(type(entry) is dict, f'{where}: an object')
        where = entry['id'] if type(entry.get('id')) is str else where
        missing = sorted(DRAFT_REQUIRED - set(entry))
        _require(not missing, f'{where}: missing {missing}')
        _check_identity(entry, where)
        category = entry['category']
        allowed = set(fields_for(category, library=False))
        for key in sorted(set(entry) - allowed):
            if entry[key] is None:  # Codex repeats C1's whole field list for every category; a null extra says nothing
                continue
            warnings.append(f'{where}: unknown field {key!r} is dropped on import')
        for key in ('lat', 'lng', 'latitude', 'longitude', 'location', 'gcj02', 'wgs84', 'coordinates'):
            _require(key not in entry, f'{where}: a draft must not carry coordinates ({key}); the importer adds them from Amap')
        _check_fields({k: v for k, v in entry.items() if k in allowed}, category, where)
        if category == 'hub':
            _require(entry.get('hub_type') in HUB_TYPES, f'{where}: hub_type is required')
            _require(entry.get('hub_type') == 'rail' or entry.get('code'), f'{where}: an airport needs its code')
        else:
            _require(entry.get('subcategory'), f'{where}: subcategory is required')
        if category == 'hotel':
            _require(entry.get('accepts_foreigners') is True, f'{where}: a hotel must accept foreign guests (accepts_foreigners: true)')
            signals = entry.get('foreigner_signals') or {}
            _require(signals.get('evidence'), f'{where}: a hotel needs foreigner_signals.evidence for accepts_foreigners')
    except Invalid as error:
        errors.append(str(error))
    except (KeyError, TypeError) as error:  # a shape so wrong a field read failed
        errors.append(f'{where}: malformed ({error!r})')
    return errors, warnings


def check_library_entry(entry, city, where='entry'):
    """Raise Invalid on the first problem of one library entry (all keys present, reviewed, located)."""
    _require(type(entry) is dict, f'{where}: an object')
    where = entry['id'] if type(entry.get('id')) is str else where
    category = entry.get('category')
    _require(category in CATEGORIES, f'{where}.category')
    keys = fields_for(category, library=True)
    extra, missing = set(entry) - set(keys), set(keys) - set(entry)
    _require(not extra and not missing, f'{where}: keys must be exactly the {category} fields (extra {sorted(extra)}, missing {sorted(missing)})')
    _check_identity(entry, where)
    _require(entry['city'] == city, f'{where}.city: {entry["city"]} in the {city} file')
    _check_fields(entry, category, where)
    if category == 'hub':
        _require(entry['hub_type'] == 'rail' or entry['code'] is not None, f'{where}: an airport needs its code')
    for key in LIBRARY_NONNULL[category]:
        _require(entry[key] is not None, f'{where}.{key}: required in the library')
    _require(entry['aliases_zh'] is not None and entry['aliases_en'] is not None, f'{where}: aliases_* must be lists (empty when none)')
    location(entry['location'], f'{where}.location', city)
    review(entry['review'], f'{where}.review')
    integer(entry['rank'], f'{where}.rank', 1, 100000)
    if category == 'hotel':
        _require(entry['accepts_foreigners'] is True and (entry['foreigner_signals'] or {}).get('evidence'),
                 f'{where}: a hotel needs accepts_foreigners true with evidence')
    return entry


# ---------------------------------------------------------------- a whole city file

def _pairs(object_pairs):
    keys = [key for key, _ in object_pairs]
    if len(keys) != len(set(keys)):
        raise Invalid('duplicate JSON key')
    return dict(object_pairs)


def load_city(path, raw=None):
    """Return the validated city document (from `raw` bytes when given); raise Invalid on the first problem."""
    text_ = (Path(path).read_bytes() if raw is None else raw).decode('utf-8')
    doc = json.loads(text_, object_pairs_hook=_pairs)
    _require(type(doc) is dict and set(doc) == {'version', 'city', 'places'}, 'document keys: version, city, places')
    _require(doc['version'] == VERSION, 'version')
    city = doc['city']
    _require(city in CITIES, 'city')
    _require(Path(path).name == f'{city}.v1.json', f'file name must be {city}.v1.json')
    _require(type(doc['places']) is list and doc['places'], 'places: non-empty list')
    seen_ids, seen_names, seen_ranks = set(), {}, set()
    for index, entry in enumerate(doc['places']):
        check_library_entry(entry, city, f'places[{index}]')
        where = entry['id']
        _require(where not in seen_ids, f'{where}: duplicate id')
        seen_ids.add(where)
        names = [entry['name_zh'], entry['name_en'], *entry['aliases_zh'], *entry['aliases_en']]
        for name in names:
            owner = seen_names.setdefault(name.casefold(), where)
            _require(owner == where, f'{where}: name {name!r} also belongs to {owner}; entity linking needs unique names per city')
        if entry['rank'] is not None:
            key = (entry['category'], entry['rank'])
            _require(key not in seen_ranks, f'{where}: rank {entry["rank"]} already used in {entry["category"]}')
            seen_ranks.add(key)
    ordered = [place['id'] for place in doc['places']]
    _require(ordered == sorted(ordered), 'places must be sorted by id (stable diffs)')
    return doc


def dumps(doc):
    """The one canonical serialisation of a city file: stable diffs, byte-identical copies."""
    return json.dumps(doc, ensure_ascii=False, indent=2) + '\n'


def city_files(places_dir=PLACES_DIR):
    return [places_dir / f'{city}.v1.json' for city in CITIES if (places_dir / f'{city}.v1.json').is_file()]
