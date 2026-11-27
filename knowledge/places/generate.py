"""Generate the copies of the place library that ship with the server and the App (#1985, F-3).

`knowledge/places/<city>.v1.json` is the only source. From it:

* server copy: `backend/fact/cj_fact/places_<city>.v1.json`, byte-identical to the source;
* App copy: one slim file `ios/Modules/CJShell/Sources/CJLioUser/Resources/LioPlaces.v1.json` with what
  the App shows before it asks the server (names, aliases, GCJ-02 point, Amap id, a hotel's price band / star / accepts-foreigners flag, one-line
  intro, thumbnail).

Neither copy is edited by hand. `validate.py` checks them (byte for byte) and `validate.py --write`
rewrites them. A copy without a source (a city that was removed, or the App file when no city exists)
is stale too. The App copy is checked in the Python job because a PR that changes only knowledge/ does
not run the Swift job.
"""
from collections import namedtuple
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import placeimages  # noqa: E402
import placelib  # noqa: E402

Layout = namedtuple('Layout', 'places_dir server_dir app_path images_path', defaults=(None,))
LAYOUT = Layout(
    placelib.PLACES_DIR,
    placelib.ROOT / 'backend/fact/cj_fact',
    placelib.ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/Resources/LioPlaces.v1.json',
    placelib.PLACES_DIR / 'images/manifest.v1.json',
)
APP_KEYS = ('id', 'city', 'category', 'kind', 'tier', 'rank', 'name_zh', 'name_en', 'aliases_zh', 'aliases_en',
            'lat', 'lng', 'amap_id', 'price_band', 'star', 'accepts_foreigners', 'intro_short_zh', 'intro_short_en',
            'thumb')


def server_copy(layout, city):
    return layout.server_dir / f'places_{city}.v1.json'


def app_place(entry, thumb):
    point = entry['location']['gcj02']
    return {
        'id': entry['id'], 'city': entry['city'], 'category': entry['category'],
        'kind': entry['hub_type'] if entry['category'] == 'hub' else entry['subcategory'],
        'tier': entry['tier'], 'rank': entry['rank'],
        'name_zh': entry['name_zh'], 'name_en': entry['name_en'],
        'aliases_zh': entry['aliases_zh'], 'aliases_en': entry['aliases_en'],
        'lat': point['lat'], 'lng': point['lng'], 'amap_id': entry['location']['amap_id'],
        # Hotels only (null for every other category): "Stay" filters on these and intersects with Amap results.
        'price_band': entry.get('price_band'), 'star': entry.get('star'),
        'accepts_foreigners': entry.get('accepts_foreigners'),
        'intro_short_zh': entry.get('intro_short_zh'), 'intro_short_en': entry.get('intro_short_en'),
        'thumb': thumb,
    }


def render_app(docs, thumbs=None):
    """The App copy for the given city documents; places are ordered city, category, rank (unranked last), id."""
    thumbs = thumbs or {}
    cities, categories = list(placelib.CITIES), list(placelib.CATEGORIES)
    places = [app_place(entry, thumbs.get(entry['id'])) for doc in docs for entry in doc['places']]
    places.sort(key=lambda p: (cities.index(p['city']), categories.index(p['category']), p['rank'] is None, p['rank'] or 0, p['id']))
    return json.dumps({'version': placelib.APP_VERSION, 'places': places}, ensure_ascii=False, separators=(',', ':')) + '\n'


def expected(layout=LAYOUT, thumbs=None):
    """{path: bytes} of every generated file, validating each source on the way (raises placelib.Invalid)."""
    if thumbs is None:  # thumbnail file names come from the image manifest, when there is one
        thumbs = placeimages.thumbs(layout.images_path) if layout.images_path and layout.images_path.is_file() else {}
    out, docs = {}, []
    for path in placelib.city_files(layout.places_dir):
        raw = path.read_bytes()
        doc = placelib.load_city(path, raw)
        _require_canonical(path, raw, doc)
        docs.append(doc)
        out[server_copy(layout, doc['city'])] = raw
    if docs:
        out[layout.app_path] = render_app(docs, thumbs).encode('utf-8')
    return out


def _require_canonical(path, raw, doc):
    if raw != placelib.dumps(doc).encode('utf-8'):
        raise placelib.Invalid(f'{path.name} is not in canonical form; run knowledge/places/validate.py --write')


def stale(layout=LAYOUT, thumbs=None):
    """Generated files that are missing, different, or left over with no source."""
    want = expected(layout, thumbs)
    bad = [path for path, data in want.items() if not path.is_file() or path.read_bytes() != data]
    leftovers = [server_copy(layout, city) for city in placelib.CITIES
                 if server_copy(layout, city).is_file() and server_copy(layout, city) not in want]
    if layout.app_path.is_file() and layout.app_path not in want:
        leftovers.append(layout.app_path)
    return bad + leftovers


def write(layout=LAYOUT, thumbs=None):
    """Rewrite the canonical sources and every copy; remove copies that no longer have a source."""
    for path in placelib.city_files(layout.places_dir):
        doc = placelib.load_city(path)
        path.write_bytes(placelib.dumps(doc).encode('utf-8'))
    want = expected(layout, thumbs)
    for path, data in want.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    for path in stale(layout, thumbs):
        if path.is_file():
            path.unlink()
    return sorted(want)


if __name__ == '__main__':
    try:
        for written in write():
            print(f'wrote {written}')
    except placelib.Invalid as error:
        print(f'FAIL: {error}', file=sys.stderr)
        sys.exit(1)
