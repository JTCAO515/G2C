"""Validate the attraction booking rules and generate the App's bundled Swift table (#1755).

`booking-rules.v1.json` is the only source. `LioAttractionBookingRules.swift` is generated from
it and must never be edited by hand; `backend/tests/test_attraction_rules_source.py` fails CI
when the committed Swift file differs from what this script produces.

Usage (from the repository root):
    python3 -B knowledge/attractions/generate_ios.py          # rewrite the Swift file
    python3 -B knowledge/attractions/generate_ios.py --check  # exit 1 if it is out of date
"""
from datetime import date
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'knowledge/attractions/booking-rules.v1.json'
SWIFT = ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/LioAttractionBookingRules.swift'
MODEL = ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/LioAttractionBooking.swift'
VERSION = 'attraction-booking-rules.1'

REQUIREMENTS = {'required': 'required', 'booking_or_on_site': 'bookingOrOnSite',
                'not_required': 'notRequired', 'unknown': 'unknown'}
PASSPORTS = {'accepted': 'accepted', 'not_stated': 'notStated'}
# Calendar weekday numbers as Swift's Calendar uses them (1 = Sunday).
WEEKDAYS = {'sunday': 1, 'monday': 2, 'tuesday': 3, 'wednesday': 4, 'thursday': 5, 'friday': 6, 'saturday': 7}
RULE_KEYS = {'id', 'name', 'city', 'aliases', 'requirement', 'window_days', 'release_time', 'passport',
             'closed_weekdays', 'open_on_public_holidays', 'limits', 'notes', 'official_channel',
             'partner_links', 'sources', 'checked_on'}


class Invalid(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise Invalid(message)


def _text(value, where):
    _require(type(value) is str and value.strip() == value and value, f'{where}: non-empty trimmed text')
    _require('\\' not in value and '"' not in value, f'{where}: no backslash or double quote')
    return value


def _pair(value, where):
    _require(type(value) is dict and value.keys() == {'en', 'zh'}, f'{where}: exactly en and zh')
    return {k: _text(value[k], f'{where}.{k}') for k in ('en', 'zh')}


def _lines(value, where):
    _require(type(value) is dict and value.keys() == {'en', 'zh'}, f'{where}: exactly en and zh')
    _require(all(type(value[k]) is list for k in ('en', 'zh')), f'{where}: lists')
    _require(len(value['en']) == len(value['zh']), f'{where}: en and zh have the same number of lines')
    return {k: [_text(item, f'{where}.{k}') for item in value[k]] for k in ('en', 'zh')}


def _url(value, where):
    _text(value, where)
    parts = urlsplit(value)
    _require(parts.scheme in ('https', 'http') and parts.hostname and not parts.username
             and not parts.password and not parts.fragment, f'{where}: plain http(s) URL')
    return value


def load(path=SOURCE):
    """Return the validated document; raise Invalid on the first problem."""
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    _require(type(doc) is dict and doc.keys() == {'version', 'review_days', 'rules'}, 'document keys')
    _require(doc['version'] == VERSION, 'version')
    _require(type(doc['review_days']) is int and 1 <= doc['review_days'] <= 90, 'review_days')
    rules = doc['rules']
    _require(type(rules) is list and rules, 'rules: non-empty list')
    seen_ids, seen_names = set(), {}
    for index, rule in enumerate(rules):
        where = f'rules[{index}]'
        _require(type(rule) is dict and rule.keys() == RULE_KEYS, f'{where}: keys')
        where = rule['id'] if type(rule['id']) is str else where
        _require(re.fullmatch(r'[a-z]+\.[a-z0-9-]+', rule['id'] or '') is not None, f'{where}: id')
        _require(rule['id'] not in seen_ids, f'{where}: duplicate id')
        seen_ids.add(rule['id'])
        _pair(rule['name'], f'{where}.name')
        _pair(rule['city'], f'{where}.city')
        _require(type(rule['aliases']) is list, f'{where}.aliases: list')
        for name in [rule['name']['en'], rule['name']['zh'], *[_text(a, f'{where}.aliases') for a in rule['aliases']]]:
            key = name.casefold()
            _require(seen_names.get(key, rule['id']) == rule['id'], f'{where}: name {name!r} also matches {seen_names.get(key)}')
            seen_names[key] = rule['id']
        _require(rule['requirement'] in REQUIREMENTS, f'{where}.requirement')
        window = rule['window_days']
        _require(window is None or (type(window) is int and 1 <= window <= 90), f'{where}.window_days')
        release = rule['release_time']
        _require(release is None or (type(release) is str and re.fullmatch(r'([01][0-9]|2[0-3]):[0-5][0-9]', release)),
                 f'{where}.release_time')
        _require(release is None or window is not None, f'{where}: a release time needs a booking window')
        _require(rule['requirement'] == 'required' or (window is None and release is None),
                 f'{where}: only required booking carries a window or release time')
        _require(rule['passport'] in PASSPORTS, f'{where}.passport')
        closed = rule['closed_weekdays']
        _require(closed is None or (type(closed) is list and len(set(closed)) == len(closed)
                                    and all(day in WEEKDAYS for day in closed)), f'{where}.closed_weekdays')
        _require(type(rule['open_on_public_holidays']) is bool, f'{where}.open_on_public_holidays')
        _lines(rule['limits'], f'{where}.limits')
        _lines(rule['notes'], f'{where}.notes')
        channel = rule['official_channel']
        _require(type(channel) is dict and channel.keys() == {'name', 'url'}, f'{where}.official_channel')
        _pair(channel['name'], f'{where}.official_channel.name')
        _url(channel['url'], f'{where}.official_channel.url')
        _require(type(rule['partner_links']) is bool, f'{where}.partner_links')
        _require(type(rule['sources']) is list and rule['sources'], f'{where}.sources: non-empty')
        _require(len(set(rule['sources'])) == len(rule['sources']), f'{where}.sources: unique')
        for url in rule['sources']:
            _url(url, f'{where}.sources')
        checked = rule['checked_on']
        _require(type(checked) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', checked), f'{where}.checked_on')
        try:
            date.fromisoformat(checked)
        except ValueError:
            raise Invalid(f'{where}.checked_on: not a calendar day') from None
    return doc


def _s(value):
    return '"' + value + '"'


def _list(values):
    return '[' + ', '.join(_s(v) for v in values) + ']'


def _rule(rule):
    req = REQUIREMENTS[rule['requirement']]
    window = 'nil' if rule['window_days'] is None else str(rule['window_days'])
    if rule['release_time'] is None:
        release = 'nil'
    else:
        hour, minute = (int(part) for part in rule['release_time'].split(':'))
        release = f'.init(hour: {hour}, minute: {minute})'
    closed = rule['closed_weekdays']
    closed = 'nil' if closed is None else '[' + ', '.join(str(WEEKDAYS[d]) for d in closed) + ']'
    channel = rule['official_channel']
    lines = [
        f'        .init(id: {_s(rule["id"])},',
        f'              nameEN: {_s(rule["name"]["en"])}, nameZH: {_s(rule["name"]["zh"])},',
        f'              cityEN: {_s(rule["city"]["en"])}, cityZH: {_s(rule["city"]["zh"])},',
        f'              aliases: {_list(rule["aliases"])},',
        f'              requirement: .{req}, windowDays: {window}, releaseTime: {release},',
        f'              passport: .{PASSPORTS[rule["passport"]]}, closedWeekdays: {closed}, '
        f'openOnPublicHolidays: {"true" if rule["open_on_public_holidays"] else "false"},',
        f'              limitsEN: {_list(rule["limits"]["en"])},',
        f'              limitsZH: {_list(rule["limits"]["zh"])},',
        f'              notesEN: {_list(rule["notes"]["en"])},',
        f'              notesZH: {_list(rule["notes"]["zh"])},',
        f'              officialChannel: .init(nameEN: {_s(channel["name"]["en"])}, nameZH: {_s(channel["name"]["zh"])},',
        f'                                     url: URL(string: {_s(channel["url"])})!),',
        f'              partnerLinks: {"true" if rule["partner_links"] else "false"},',
        '              sources: [' + ', '.join(f'URL(string: {_s(u)})!' for u in rule['sources']) + '],',
        f'              checkedOn: {_s(rule["checked_on"])}),',
    ]
    return '\n'.join(lines)


def render(doc):
    head = ('// Generated by knowledge/attractions/generate_ios.py from knowledge/attractions/booking-rules.v1.json.\n'
            '// Do not edit by hand: change the JSON (with sources and checked_on) and rerun the script.\n'
            'import Foundation\n\n'
            '/// Bundled rule table. Each value comes from the listed page as read on `checkedOn`; anything\n'
            '/// the page does not state is nil or left out. Review every rule within `reviewDays` of its check;\n'
            '/// after that the app withholds the numbers and reminders and points to the official channel.\n'
            'extension LioAttractionBookingRule {\n'
            '    static let all: [LioAttractionBookingRule] = [\n')
    return head + '\n\n'.join(_rule(rule) for rule in doc['rules']) + '\n    ]\n}\n'


def app_review_days():
    match = re.search(r'static let reviewDays = (\d+)', MODEL.read_text(encoding='utf-8'))
    _require(match is not None, 'reviewDays constant not found in LioAttractionBooking.swift')
    return int(match.group(1))


def main(argv):
    doc = load()
    _require(doc['review_days'] == app_review_days(), 'review_days differs from the App reviewDays constant')
    text = render(doc)
    if '--check' in argv:
        if SWIFT.read_text(encoding='utf-8') != text:
            print(f'{SWIFT.relative_to(ROOT)} is out of date; run knowledge/attractions/generate_ios.py', file=sys.stderr)
            return 1
        print(f'OK: {len(doc["rules"])} rules match {SWIFT.relative_to(ROOT)}')
        return 0
    SWIFT.write_text(text, encoding='utf-8')
    print(f'wrote {len(doc["rules"])} rules to {SWIFT.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
