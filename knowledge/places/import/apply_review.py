"""Turn a reviewer's decisions into library entries (#1988, F-6).

The review table (`review/<city>.review.csv`, written by `import_drafts.py`) has three columns for the
reviewer: `decision` (accept / reject / edit), `rank` (optional whole number) and `note`. This script reads
the filled table and the candidate file and:

* accept  -> builds the library entry (draft fields + Amap location + rank + review record), validates the
             whole city file with the same rules `validate.py` uses, then adds it to `<city>.v1.json`;
* reject  -> marks the candidate rejected (kept in the candidate file, never in the library);
* edit    -> leaves the candidate pending and lists it: fix the draft in the candidate file, re-run;
* blank   -> untouched.

Only a candidate that is still pending can be decided on; an id already in the library is never overwritten
unless `--replace` says so (the old reviewer, day and rank are lost, so the summary names every replaced id).
Both files are written through a temporary file and renamed, so a kill or a full disk leaves the old one.

All or nothing per city: if any accepted entry makes the city file invalid, nothing is written and every
problem is listed. Only a person's `accept` brings an entry into the library; the reviewer name and day
are written into each entry, so the audit trail is in the data.

Usage (repository root):
  python3 -B knowledge/places/import/apply_review.py beijing --reviewer JT --on 2026-11-30
then:  python3 -B knowledge/places/validate.py --write     (copies, App file, booking-rule cross-check)
"""
import argparse
import csv
import json
import os
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import import_drafts  # noqa: E402
import placelib  # noqa: E402

DECISIONS = {'accept', 'reject', 'edit'}


def read_decisions(path):
    """{id: (decision, rank, note)} for the rows the reviewer filled in; raises Invalid on a bad cell."""
    found = {}
    with open(path, encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        placelib._require({'id', 'decision'} <= set(reader.fieldnames or ()), f'{path.name}: the header must have the columns id and decision')
        for line, row in enumerate(reader, start=2):
            decision = (row.get('decision') or '').strip().lower()
            if not decision:
                continue
            ident = (row.get('id') or '').strip()
            placelib._require(decision in DECISIONS, f'{path.name} line {line}: decision {decision!r} is not accept, reject or edit')
            placelib._require(ident not in found, f'{path.name} line {line}: {ident} decided twice')
            rank = (row.get('rank') or '').strip()
            placelib._require(rank == '' or (rank.isascii() and rank.isdigit() and int(rank) >= 1), f'{path.name} line {line}: rank must be a whole number from 1')
            note = (row.get('note') or '').strip() or None
            placelib._require(decision != 'edit' or note, f'{path.name} line {line}: an edit needs a note saying what to change')
            found[ident] = (decision, int(rank) if rank else None, note)
    return found


def library_entry(candidate, rank, reviewer, today, note):
    """The library entry an accepted candidate becomes."""
    placelib._require(candidate['location'] is not None, f'{candidate["id"]}: no location (Amap found nothing); cannot accept')
    entry = {key: value for key, value in candidate['draft'].items() if key != 'external_signals'}
    entry['location'] = candidate['location']
    entry['rank'] = rank
    entry['review'] = {'status': 'approved', 'reviewer': reviewer, 'reviewed_on': today, 'note': note}
    keys = placelib.fields_for(entry['category'], library=True)
    return {key: entry.get(key) for key in keys}


def apply(city, decisions, candidates_doc, library_path, reviewer, today, allow_replace=False):
    """(new library document, new candidate document, edits, problems, replaced ids). Writes nothing."""
    placelib.text(reviewer, 'reviewer')
    placelib.day(today, 'date')
    by_id = {c['id']: c for c in candidates_doc['candidates']}
    problems, edits, accepted = [], [], {}
    places = {}
    if library_path.is_file():
        places = {p['id']: p for p in placelib.load_city(library_path)['places']}
    replaced = []
    for ident, (decision, rank, note) in decisions.items():
        cand = by_id.get(ident)
        if cand is None:
            problems.append(f'{ident}: not in the {city} candidate file')
            continue
        in_library = ident in places
        if decision == 'accept' and in_library and not allow_replace:
            problems.append(f'{ident}: already in the library (reviewed {places[ident]["review"]["reviewed_on"]} by {places[ident]["review"]["reviewer"]}); '
                            'run with --replace to overwrite it')
            continue
        if cand['status'] != 'pending' and not (decision == 'accept' and in_library and allow_replace):
            problems.append(f'{ident}: the candidate is {cand["status"]}, not pending; only a pending candidate can be decided on '
                            '(put it back to pending in the candidate file if you changed your mind)')
            continue
        if decision == 'reject' and in_library:
            problems.append(f'{ident}: it is in the library; remove or retire it there, not through a reject')
            continue
        if decision == 'reject':
            cand['status'], cand['review_note'] = 'rejected', note
        elif decision == 'edit':
            cand['review_note'] = note
            edits.append(f'{ident}: {note}')
        else:
            try:
                accepted[ident] = library_entry(cand, rank, reviewer, today, note)
            except placelib.Invalid as error:
                problems.append(str(error))
    replaced = [ident for ident in accepted if ident in places]
    places.update(accepted)
    library = {'version': placelib.VERSION, 'city': city, 'places': sorted(places.values(), key=lambda p: p['id'])}
    if accepted and not problems:  # validate with the real rules, under the real file name
        with tempfile.TemporaryDirectory() as scratch:
            probe = Path(scratch) / f'{city}.v1.json'
            probe.write_text(placelib.dumps(library), encoding='utf-8')
            try:
                placelib.load_city(probe)
            except placelib.Invalid as error:
                problems.append(f'the {city} library would be invalid: {error}')
    for ident in accepted:
        by_id[ident]['status'] = 'accepted'
    return library, candidates_doc, edits, problems, replaced


def _write_atomic(path, text):
    """Write through a temporary file in the same folder and rename it over `path`."""
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    try:
        temporary.write_text(text, encoding='utf-8')
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('city', choices=sorted(placelib.CITIES))
    parser.add_argument('--reviewer', required=True)
    parser.add_argument('--on', required=True, help='review day, YYYY-MM-DD')
    parser.add_argument('--table', help='review CSV (default review/<city>.review.csv)')
    parser.add_argument('--candidates', default=str(import_drafts.DEFAULT_OUT))
    parser.add_argument('--library-dir', default=str(placelib.PLACES_DIR))
    parser.add_argument('--replace', action='store_true', help='let an accept overwrite an entry that is already in the library')
    args = parser.parse_args(argv)
    table = Path(args.table or import_drafts.DEFAULT_REVIEW / f'{args.city}.review.csv')
    cand_path = Path(args.candidates) / f'{args.city}.cand.json'
    library_path = Path(args.library_dir) / f'{args.city}.v1.json'
    try:
        decisions = read_decisions(table)
        doc = json.loads(cand_path.read_text(encoding='utf-8'))
        library, doc, edits, problems, replaced = apply(args.city, decisions, doc, library_path, args.reviewer, args.on, args.replace)
    except (placelib.Invalid, OSError, ValueError, KeyError, TypeError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    for problem in problems:
        print(f'FAIL: {problem}', file=sys.stderr)
    if problems:
        print('nothing was written', file=sys.stderr)
        return 1
    accepted = sum(1 for d, _, _ in decisions.values() if d == 'accept')
    rejected = sum(1 for d, _, _ in decisions.values() if d == 'reject')
    try:
        if accepted:
            _write_atomic(library_path, placelib.dumps(library))
        _write_atomic(cand_path, import_drafts.dumps(doc))
    except OSError as error:
        print(f'FAIL: could not write ({error}); the library file is written first, so check it before re-running', file=sys.stderr)
        return 1
    print(f'{args.city}: {accepted} accepted ({accepted - len(replaced)} new, {len(replaced)} replaced), {rejected} rejected, {len(edits)} to edit')
    for ident in replaced:
        print(f'  replaced {ident}')
    for edit in edits:
        print(f'  edit {edit}')
    if accepted:
        print('now run: python3 -B knowledge/places/validate.py --write')
    return 0


if __name__ == '__main__':
    sys.exit(main())
