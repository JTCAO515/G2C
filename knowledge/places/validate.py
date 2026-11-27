"""Validate the place library and keep its server and App copies in step (#1985, F-3).

Checks every `knowledge/places/<city>.v1.json` (shape, official sources, GCJ-02 point inside the city,
unique names, review record) and the library as a whole (ids unique across cities, no conflict with
`knowledge/attractions/booking-rules.v1.json`, which stays the only booking-rule source), then compares
the generated copies byte for byte. Nothing here reads a clock, so CI never turns red on a calendar day.

Usage (from the repository root):
  python3 -B knowledge/places/validate.py           validate; fail if a copy is stale
  python3 -B knowledge/places/validate.py --write   validate, then rewrite canonical sources and copies
"""
import importlib.util
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate  # noqa: E402
import placelib  # noqa: E402

BOOKING_RULES = placelib.ROOT / 'knowledge/attractions/generate_ios.py'
_WEEKDAYS = {'monday': 1, 'tuesday': 2, 'wednesday': 3, 'thursday': 4, 'friday': 5, 'saturday': 6, 'sunday': 7}


def _booking_module():
    spec = importlib.util.spec_from_file_location('attraction_rules_source', BOOKING_RULES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def booking_conflicts(docs, rules):
    """Places that contradict the booking-rule table for the same venue (exact name or alias match)."""
    by_name = {}
    for rule in rules:
        for name in (rule['name']['zh'], rule['name']['en'], *rule['aliases']):
            by_name[name.casefold()] = rule
    problems = []
    for doc in docs:
        for place in doc['places']:
            if place['category'] != 'attraction':
                continue
            rule = next((by_name[n.casefold()] for n in (place['name_zh'], place['name_en'], *place['aliases_zh'], *place['aliases_en'])
                         if n.casefold() in by_name), None)
            ticket = place['ticket']
            if rule is None or ticket is None:
                continue
            if (rule['requirement'] == 'required' and ticket['booking'] == 'none') or \
                    (rule['requirement'] == 'not_required' and ticket['booking'] == 'required'):
                problems.append(f'{place["id"]}: ticket.booking {ticket["booking"]!r} contradicts booking rule {rule["id"]} ({rule["requirement"]})')
            if rule['closed_weekdays'] is not None and ticket['closed_weekdays'] is not None and \
                    {_WEEKDAYS[d] for d in rule['closed_weekdays']} != set(ticket['closed_weekdays']):
                problems.append(f'{place["id"]}: ticket.closed_weekdays {ticket["closed_weekdays"]} differs from booking rule {rule["id"]}')
    return problems


def validate(layout=generate.LAYOUT, rules=None, thumbs=None):
    """Return (documents, problems); raises placelib.Invalid for a malformed city file."""
    docs = [placelib.load_city(path) for path in placelib.city_files(layout.places_dir)]
    problems, seen = [], {}
    for doc in docs:
        for place in doc['places']:
            if place['id'] in seen:
                problems.append(f'{place["id"]}: also in {seen[place["id"]]}')
            seen[place['id']] = doc['city']
    if rules is None:
        rules = _booking_module().load()['rules']
    problems += booking_conflicts(docs, rules)
    return docs, problems


def main(argv=()):
    unknown = [arg for arg in argv if arg != '--write']
    if unknown:
        print(f'unknown argument {unknown[0]!r}; the only option is --write', file=sys.stderr)
        return 2
    if '--write' in argv:
        docs, problems = validate()
        if problems:
            print('\n'.join(f'FAIL: {p}' for p in problems), file=sys.stderr)
            return 1
        for path in generate.write():
            print(f'wrote {path}')
    else:
        docs, problems = validate()
        out_of_date = generate.stale()
        for path in out_of_date:
            print(f'{path} is out of date; run python3 -B knowledge/places/validate.py --write', file=sys.stderr)
        if problems or out_of_date:
            print('\n'.join(f'FAIL: {p}' for p in problems), file=sys.stderr)
            return 1
    print(f'PASS: {sum(len(d["places"]) for d in docs)} places in {len(docs)} city files, copies identical')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except placelib.Invalid as error:
        print(f'FAIL: {error}', file=sys.stderr)
        sys.exit(1)
