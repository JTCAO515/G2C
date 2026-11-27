"""Amap (高德) Web Service lookups for place candidates (#1986, F-4).

Adds the two things Codex does not write: a GCJ-02 point and the Amap POI id. Amap answers in GCJ-02
already, so nothing is converted. The key comes from the environment and is never printed or put in an
error message. Network access is injected (`fetch`), so tests run on canned answers; the real `fetch`
is only built when the importer is run with `--live`.

Matching is deliberately plain: a POI only counts as `exact` when its name equals the place's name or
an alias, `close` when one name contains the other, `weak` when it is merely the first result. The
review table shows the status, so a person confirms every weak match before it enters the library.
"""
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import placelib  # noqa: E402

BASE = 'https://restapi.amap.com'
CITY_ZH = {'beijing': '北京', 'shanghai': '上海', 'guangzhou': '广州', 'shenzhen': '深圳', 'chengdu': '成都', 'chongqing': '重庆'}
# Amap infocodes that mean "stop, this will not get better": bad key, no permission, daily quota gone.
FATAL = {'10001', '10002', '10003', '10009', '10010', '10011', '10012', '10013', '10020', '10021'}
RETRY = {'10004', '10014', '10019'}  # too frequent


class AmapError(RuntimeError):
    pass


def scrub(text, key):
    """Never let the key reach a log, an exception or a file."""
    if not key:
        return text
    return text.replace(key, '***').replace(quote(key, safe=''), '***')


def make_fetch(key, timeout=10, pause=0.25, cache_dir=None):
    """The real network function: GET path+params -> parsed JSON. Cached by request (key excluded)."""
    cache_dir = Path(cache_dir) if cache_dir else None
    last = [0.0]

    def fetch(path, params):
        ident = hashlib.sha256((path + json.dumps(params, sort_keys=True, ensure_ascii=False)).encode('utf-8')).hexdigest()
        cached = cache_dir / f'{ident}.json' if cache_dir else None
        if cached and cached.is_file():
            return json.loads(cached.read_text(encoding='utf-8'))
        wait = last[0] + pause - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        url = f'{BASE}{path}?{urlencode({**params, "key": key}, quote_via=quote)}'
        for attempt in range(3):
            try:
                with urlopen(Request(url, headers={'User-Agent': 'g2c-places-import'}), timeout=timeout) as response:
                    doc = json.loads(response.read().decode('utf-8'))
            except Exception as error:  # network or JSON: report without the URL (it carries the key)
                raise AmapError(f'{path}: {scrub(type(error).__name__ + ": " + str(error), key)}') from None
            finally:
                last[0] = time.monotonic()
            if doc.get('status') == '0' and doc.get('infocode') in RETRY and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            break
        if cached and doc.get('status') == '1':  # a refusal (rate limit, bad key, quota) must not be remembered
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
        return doc

    return fetch


def _check(doc, path):
    if doc.get('status') != '1':
        code = str(doc.get('infocode'))
        message = f'{path}: Amap infocode {code} {doc.get("info")}'
        raise AmapError(message + ' (stopping: fix the key or quota)') if code in FATAL else AmapError(message)
    return doc


def _point(location):
    """'lng,lat' -> (lat, lng) rounded to 6 decimals, or None."""
    match = re.fullmatch(r'\s*(-?[0-9]+(?:\.[0-9]+)?),(-?[0-9]+(?:\.[0-9]+)?)\s*', location or '')
    return None if match is None else (round(float(match.group(2)), 6), round(float(match.group(1)), 6))


def _in_city(point, city):
    south, north, west, east = placelib.CITY_BOXES[city]
    return point is not None and south <= point[0] <= north and west <= point[1] <= east


def search(fetch, city, keywords):
    """Up to 5 POIs {id,name,address,type,lat,lng} of `keywords` inside the city, in Amap's order."""
    doc = _check(fetch('/v3/place/text', {'keywords': keywords, 'city': CITY_ZH[city], 'citylimit': 'true',
                                          'offset': '5', 'page': '1', 'extensions': 'base'}), '/v3/place/text')
    found = []
    for poi in doc.get('pois') or []:
        point = _point(poi.get('location'))
        if not _in_city(point, city) or not poi.get('id') or not poi.get('name'):
            continue
        address = poi.get('address')
        found.append({'id': poi['id'], 'name': poi['name'], 'address': address if isinstance(address, str) else '',
                      'type': poi.get('type') or '', 'lat': point[0], 'lng': point[1]})
    return found


def geocode(fetch, city, address):
    """The first geocode result inside the city as {lat,lng,name}, or None."""
    doc = _check(fetch('/v3/geocode/geo', {'address': address, 'city': CITY_ZH[city]}), '/v3/geocode/geo')
    for item in doc.get('geocodes') or []:
        point = _point(item.get('location'))
        if _in_city(point, city):
            formatted = item.get('formatted_address')
            return {'lat': point[0], 'lng': point[1], 'name': formatted if isinstance(formatted, str) and formatted else None}
    return None


def _norm(name):
    return re.sub(r'[\s·・（）()\-—–]', '', name).casefold()


def _contains(a, b):
    """One name inside the other and at least 60% of its length: a cafe called '故宫角楼咖啡' is not '故宫'."""
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 3 and short in long_ and len(short) >= 0.6 * len(long_)


def classify(place, pois):
    """('exact'|'close'|'weak'|'none', best POI or None) for a draft against Amap's results."""
    names = {_norm(n) for n in (place['name_zh'], *(place.get('aliases_zh') or [])) if n}
    for poi in pois:
        if _norm(poi['name']) in names:
            return 'exact', poi
    for poi in pois:
        pn = _norm(poi['name'])
        if any(_contains(n, pn) for n in names):
            return 'close', poi
    return ('weak', pois[0]) if pois else ('none', None)


def locate(fetch, place, today):
    """Look one draft up. Returns (location block or None, amap info dict). Raises AmapError when Amap refuses."""
    city = place['city']
    pois = search(fetch, city, place['name_zh'])
    status, best = classify(place, pois)
    info = {'status': status, 'alternatives': [dict(p) for p in pois[:3]]}
    if best is not None:
        return ({'gcj02': {'lat': best['lat'], 'lng': best['lng']}, 'amap_id': best['id'], 'amap_name': best['name'],
                 'method': 'amap-poi-search', 'geocoded_on': today}, info)
    if place.get('address_zh'):
        found = geocode(fetch, city, place['address_zh'])
        if found is not None:
            info['status'] = 'address-only'
            return ({'gcj02': {'lat': found['lat'], 'lng': found['lng']}, 'amap_id': None, 'amap_name': found['name'],
                     'method': 'amap-geocode', 'geocoded_on': today}, info)
    return None, info
