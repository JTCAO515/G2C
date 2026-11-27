"""Turn a reviewer's decisions into library entries (#1988, F-6).

The review table (`review/<city>.review.csv`, written by `import_drafts.py`) has three columns for the
reviewer: `decision` (accept / reject / edit), `rank` (optional whole number) and `note`. This script reads
the filled table and the candidate file and:

* accept  -> builds the library entry (draft fields + Amap location + rank + review record), validates the
             whole city file with the same rules `validate.py` uses, then adds it to `<city>.v1.json`;
* reject  -> marks the candidate rejected (kept in the candidate file, never in the library);
* edit    -> leaves the candidate pending and lists it: fix the draft in the candidate file, re-run;
* blank   -> untouched.

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
        for line, row in enumerate(csv.DictReader(handle), start=2):
            decision = (row.get('decision') or '').strip().lower()
            if not decision:
                continue
            ident = (row.get('id') or '').strip()
            placelib._require(decision in DECISIONS, f'{path.name} line {line}: decision {decision!r} is not accept, reject or edit')
            placelib._require(ident not in found, f'{path.name} line {line}: {ident} decided twice')
            rank = (row.get('rank') or '').strip()
            placelib._require(rank == '' or (rank.isdigit() and int(rank) >= 1), f'{path.name} line {line}: rank must be a whole number from 1')
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


def apply(city, decisions, candidates_doc, library_path, reviewer, today):
    """(new library document, new candidate document, edits, problems). Writes nothing."""
    placelib.text(reviewer, 'reviewer')
    placelib.day(today, 'date')
    by_id = {c['id']: c for c in candidates_doc['candidates']}
    problems, edits, accepted = [], [], {}
    for ident, (decision, rank, note) in decisions.items():
        cand = by_id.get(ident)
        if cand is None:
            problems.append(f'{ident}: not in the {city} candidate file')
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
    places = {}
    if library_path.is_file():
        places = {p['id']: p for p in placelib.load_city(library_path)['places']}
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
    return library, candidates_doc, edits, problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('city', choices=sorted(placelib.CITIES))
    parser.add_argument('--reviewer', required=True)
    parser.add_argument('--on', required=True, help='review day, YYYY-MM-DD')
    parser.add_argument('--table', help='review CSV (default review/<city>.review.csv)')
    parser.add_argument('--candidates', default=str(import_drafts.DEFAULT_OUT))
    parser.add_argument('--library-dir', default=str(placelib.PLACES_DIR))
    args = parser.parse_args(argv)
    table = Path(args.table or import_drafts.DEFAULT_REVIEW / f'{args.city}.review.csv')
    cand_path = Path(args.candidates) / f'{args.city}.cand.json'
    library_path = Path(args.library_dir) / f'{args.city}.v1.json'
    try:
        decisions = read_decisions(table)
        doc = json.loads(cand_path.read_text(encoding='utf-8'))
        library, doc, edits, problems = apply(args.city, decisions, doc, library_path, args.reviewer, args.on)
    except (placelib.Invalid, OSError, ValueError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    for problem in problems:
        print(f'FAIL: {problem}', file=sys.stderr)
    if problems:
        print('nothing was written', file=sys.stderr)
        return 1
    accepted = sum(1 for d, _, _ in decisions.values() if d == 'accept')
    rejected = sum(1 for d, _, _ in decisions.values() if d == 'reject')
    if accepted:
        library_path.write_text(placelib.dumps(library), encoding='utf-8')
    cand_path.write_text(import_drafts.dumps(doc), encoding='utf-8')
    print(f'{args.city}: {accepted} accepted, {rejected} rejected, {len(edits)} to edit')
    for edit in edits:
        print(f'  edit {edit}')
    if accepted:
        print('now run: python3 -B knowledge/places/validate.py --write')
    return 0


if __name__ == '__main__':
    sys.exit(main())
