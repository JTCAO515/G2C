"""Validate the business-pack knowledge catalogue (#1759) and keep its server copy in step (#1859).

Each entry carries its official sources, the day they were read (`checked_on`, Beijing calendar) and
its review deadline (`expires_on`). The scene pack (`backend/cj_api/scene_packs/business.json`)
refers to these ids; nothing here reads a clock, so CI never turns red on a calendar day
(expiry alerts are `scripts/fact_expiry.py`'s job, #1757).

The server copy `backend/fact/cj_fact/business_guangzhou.v1.json` (read by `cj_fact.business`
for Lio's fact tool) and the App's bundled copy `LioBusinessGuangzhou.v1.json` must be
byte-identical to `guangzhou.v1.json`; never edit them by hand. The App copy is checked here, in
the Python job, because a PR that only changes `knowledge/` does not run the Swift job.

Usage (from the repository root):
  python3 -B knowledge/business/validate.py           validate, and fail if the server copy is stale
  python3 -B knowledge/business/validate.py --write   validate, then rewrite the server copy
"""
from datetime import date
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
CATALOGUES = (ROOT / 'knowledge/business/guangzhou.v1.json',)
# Server copy for Lio's fact tool (#1859): byte-identical to the Guangzhou catalogue.
SERVER_COPIES = {CATALOGUES[0]: ROOT / 'backend/fact/cj_fact/business_guangzhou.v1.json'}
# App copy (the trip lane's #1963): must match whenever it exists. Until that file lands on main it is
# absent and not created here (`--write` leaves an absent App copy alone); make it required then.
APP_COPIES = {CATALOGUES[0]: ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/Resources/LioBusinessGuangzhou.v1.json'}
VERSION = 'g2c-business-knowledge.1'
CITIES = frozenset({'guangzhou'})
TOPICS = frozenset({'trade_fair_registration', 'venue_transport', 'visa_channel', 'business_payment'})
# S1 hosts only, each approved for the Guangzhou business entries; see knowledge/business/README.md.
HOSTS = frozenset({'www.cantonfair.org.cn', 'hk.cantonfair.org.cn', 'gaj.gz.gov.cn', 'www.gz.gov.cn', 'www.nia.gov.cn'})
KEYS = frozenset({'id', 'topic', 'title', 'text_zh', 'text_en', 'source_urls', 'checked_on', 'expires_on'})
MAX_REVIEW_DAYS = 90


class Invalid(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise Invalid(message)


def _text(value, where):
    _require(type(value) is str and value.strip() == value and value and '\n' not in value, f'{where}: one trimmed line')
    return value


def _day(value, where):
    _require(type(value) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) is not None, f'{where}: YYYY-MM-DD')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise Invalid(f'{where}: not a calendar day') from None


def _pairs(object_pairs):
    keys = [key for key, _ in object_pairs]
    if len(keys) != len(set(keys)):
        raise Invalid('duplicate JSON key')
    return dict(object_pairs)


def load(path, raw=None):
    """Return the validated catalogue (from `raw` bytes when given); raise Invalid on the first problem."""
    text = (Path(path).read_bytes() if raw is None else raw).decode('utf-8')
    doc = json.loads(text, object_pairs_hook=_pairs)
    _require(type(doc) is dict and doc.keys() == {'version', 'city', 'entries'}, 'document keys')
    _require(doc['version'] == VERSION, 'version')
    _require(doc['city'] in CITIES, 'city')
    _require(type(doc['entries']) is list and doc['entries'], 'entries: non-empty list')
    seen = set()
    for index, entry in enumerate(doc['entries']):
        _require(type(entry) is dict and entry.keys() == KEYS, f'entries[{index}]: keys')
        where = _text(entry['id'], f'entries[{index}].id')
        _require(re.fullmatch(rf"business\.{doc['city']}\.[a-z0-9-]+", where) is not None, f'{where}: id prefix')
        _require(where not in seen, f'{where}: duplicate id')
        seen.add(where)
        _require(type(entry['topic']) is str and entry['topic'] in TOPICS, f'{where}: topic')
        title = entry['title']
        _require(type(title) is dict and title.keys() == {'zh', 'en'}, f'{where}: title zh/en')
        for key in ('zh', 'en'):
            _text(title[key], f'{where}.title.{key}')
        _text(entry['text_zh'], f'{where}.text_zh')
        _text(entry['text_en'], f'{where}.text_en')
        urls = entry['source_urls']
        _require(type(urls) is list and urls and len(set(urls)) == len(urls), f'{where}: unique non-empty sources')
        for url in urls:
            parts = urlsplit(_text(url, f'{where}.source_urls'))
            _require(parts.scheme == 'https' and parts.hostname in HOSTS and parts.port is None and parts.path not in ('', '/')
                     and not parts.username and not parts.password and not parts.fragment,
                     f'{where}: source {url} is not a page on an approved https host')
        checked = _day(entry['checked_on'], f'{where}.checked_on')
        expires = _day(entry['expires_on'], f'{where}.expires_on')
        _require(checked < expires and (expires - checked).days <= MAX_REVIEW_DAYS, f'{where}: review period 1..90 days')
    return doc


def _shown(path):
    return path.relative_to(ROOT) if path.is_relative_to(ROOT) else path


def stale_copies(raw, server, app):
    """Copies that differ from the source bytes: the server copy must exist, the App copy only when present."""
    out = [server] if not server.is_file() or server.read_bytes() != raw else []
    if app.is_file() and app.read_bytes() != raw:
        out.append(app)
    return out


def main(argv=()):
    unknown = [arg for arg in argv if arg != '--write']
    if unknown:
        print(f'unknown argument {unknown[0]!r}; the only option is --write', file=sys.stderr)
        return 2
    stale = False
    for path in CATALOGUES:
        raw = path.read_bytes()
        doc = load(path, raw)
        server, app = SERVER_COPIES[path], APP_COPIES[path]
        if '--write' in argv:
            server.write_bytes(raw)
            print(f'wrote {_shown(server)}')
            if app.is_file():
                app.write_bytes(raw)
                print(f'wrote {_shown(app)}')
        else:
            out_of_date = stale_copies(raw, server, app)
            for copy in out_of_date:
                print(f'{_shown(copy)} is out of date; run python3 -B knowledge/business/validate.py --write', file=sys.stderr)
            if out_of_date:
                stale = True
                continue
        print(f'PASS: {len(doc["entries"])} entries in {_shown(path)}, copies identical')
    return 1 if stale else 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except Invalid as error:
        print(f'FAIL: {error}', file=sys.stderr)
        sys.exit(1)
