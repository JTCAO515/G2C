"""The development data pack: unreviewed candidates, for building features before the library exists (#1985 follow-up).

JT reviews candidates a day at a time, so the library is empty for a while, yet the dialogue lane (entity
linking), the App (place page) and the canvas need place data to be built against. The pack is that data:
every pending candidate in the library shape, with `review.status == "unreviewed"` and `location` null
until Amap has run. It is NOT the library:

* it lives in `knowledge/places/dev/`, is never copied into `backend/fact/cj_fact/` (the server image) or
  into the App bundle, and is checked in CI to stay that way;
* the server reads it only through `cj_fact.places_dev`, which needs two explicit opt-ins in the environment;
  the App reads it only in a Debug build, from a path given at launch (`LioPlacesDevPack`);
* it is regenerated from `candidates/` (`validate.py --write`), and entries a person accepts leave it
  because they move into the real library.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import placelib  # noqa: E402

VERSION = 'g2c-places-dev.1'
PACK = placelib.PLACES_DIR / 'dev/places-dev-pack.v1.json'
CANDIDATES = placelib.PLACES_DIR / 'candidates'
WARNING = 'UNREVIEWED DEVELOPMENT DATA. Not the place library. Never read in production, never shown to users.'
UNREVIEWED = {'status': 'unreviewed', 'reviewer': None, 'reviewed_on': None, 'note': None}


def entry_from_candidate(candidate):
    draft = candidate['draft']
    keys = placelib.fields_for(draft['category'], library=True)
    entry = {key: draft.get(key) for key in keys}
    entry['location'] = candidate['location']
    entry['rank'] = None
    entry['review'] = dict(UNREVIEWED)
    return entry


def build(candidates_dir=CANDIDATES):
    """The pack document from every pending candidate in `candidates_dir`."""
    places, generated = [], None
    for city in placelib.CITIES:
        path = Path(candidates_dir) / f'{city}.cand.json'
        if not path.is_file():
            continue
        doc = json.loads(path.read_text(encoding='utf-8'))
        generated = max(filter(None, [generated, doc['generated_on']]))
        places += [entry_from_candidate(c) for c in doc['candidates'] if c['status'] == 'pending']
    places.sort(key=lambda p: p['id'])
    return {'version': VERSION, 'warning': WARNING, 'generated_on': generated, 'places': places}


def check_entry(entry, where):
    placelib._require(type(entry) is dict and entry.get('category') in placelib.CATEGORIES, f'{where}: category')
    keys = placelib.fields_for(entry['category'], library=True)
    placelib._require(set(entry) == set(keys), f'{where}: keys must be exactly the {entry["category"]} library fields')
    placelib._check_identity(entry, where)
    placelib._check_fields(entry, entry['category'], where)
    if entry['location'] is not None:
        placelib.location(entry['location'], f'{where}.location', entry['city'])
    placelib._require(entry['rank'] is None, f'{where}.rank: a development entry has no rank')
    placelib._require(entry['review'] == UNREVIEWED, f'{where}.review: must be the unreviewed record')


def validate(doc):
    placelib._require(type(doc) is dict and set(doc) == {'version', 'warning', 'generated_on', 'places'}, 'pack keys')
    placelib._require(doc['version'] == VERSION and doc['warning'] == WARNING, 'version and warning')
    placelib._require(doc['generated_on'] is None or placelib.day(doc['generated_on'], 'generated_on'), 'generated_on')
    ids = [p.get('id') for p in doc['places']]
    placelib._require(ids == sorted(ids) and len(set(ids)) == len(ids), 'places must be sorted by id and unique')
    for entry in doc['places']:
        check_entry(entry, entry['id'])
    return doc


def dumps(doc):
    return json.dumps(doc, ensure_ascii=False, indent=1) + '\n'


def stale(pack=PACK, candidates_dir=CANDIDATES):
    """Problems between the committed pack and what the candidates produce (empty list when in step)."""
    expected = build(candidates_dir)
    if not expected['places']:
        return [f'{pack} exists but there are no pending candidates'] if Path(pack).is_file() else []
    validate(expected)
    if not Path(pack).is_file() or Path(pack).read_text(encoding='utf-8') != dumps(expected):
        return [f'{pack} is out of date; run python3 -B knowledge/places/validate.py --write']
    return []


def write(pack=PACK, candidates_dir=CANDIDATES):
    doc = build(candidates_dir)
    pack = Path(pack)
    if not doc['places']:
        pack.unlink(missing_ok=True)
        return None
    validate(doc)
    pack.parent.mkdir(parents=True, exist_ok=True)
    pack.write_text(dumps(doc), encoding='utf-8')
    return pack
