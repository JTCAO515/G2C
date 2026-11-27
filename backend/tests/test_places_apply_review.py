"""From Codex draft to library entry: import, human decision, apply, validate (#1988)."""
import copy
import csv
import io
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
for sub in ('knowledge/places', 'knowledge/places/import', 'backend/tests'):
    sys.path.insert(0, str(ROOT / sub))
import apply_review  # noqa: E402
import generate  # noqa: E402
import import_drafts as importer  # noqa: E402
import placelib  # noqa: E402
import validate  # noqa: E402
from test_places_import import TODAY, fake_fetch, inbox, poi, second  # noqa: E402
from test_places_pipeline import C1  # noqa: E402


def imported(tmp_path, entries, fetch=None):
    """Run the importer into tmp dirs; returns (candidate dir, review dir)."""
    fetch = fetch or fake_fetch(lambda keywords: [poi({'故宫博物院': '故宫博物院', '天坛公园': '天坛公园'}.get(keywords, keywords),
                                                     ident='B000A8UIN8' if keywords == '故宫博物院' else 'B000A8UF3K',
                                                     lng='116.397029' if keywords == '故宫博物院' else '116.407',
                                                     lat='39.917839' if keywords == '故宫博物院' else '39.882')])
    by_city, rejected, notes = importer.process(inbox(tmp_path, C1__beijing=entries), TODAY, fetch, library_dir=tmp_path / 'lib')
    out, review = tmp_path / 'cand', tmp_path / 'review'
    importer.write_outputs(by_city, rejected, notes, TODAY, out, review, 25)
    return out, review


def fill(review, decisions):
    """Write the reviewer's answers into the CSV: {id: (decision, rank, note)}."""
    path = review / 'beijing.review.csv'
    rows = list(csv.reader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
    for row in rows[1:]:
        if row[1] in decisions:
            row[-3:] = [str(x) if x is not None else '' for x in decisions[row[1]]]
    out = io.StringIO()
    csv.writer(out, lineterminator='\n').writerows(rows)
    path.write_text(out.getvalue(), encoding='utf-8-sig')
    return path


def run(tmp_path, out, review, *extra):
    return apply_review.main(['beijing', '--reviewer', 'JT', '--on', '2026-11-30', '--candidates', str(out),
                              '--library-dir', str(tmp_path / 'lib'), '--table', str(review / 'beijing.review.csv'), *extra])


def test_accepted_entries_enter_the_library_with_review_record_and_pass_validation(tmp_path):
    out, review = imported(tmp_path, [C1, second()])
    fill(review, {'pl_bj_gugong': ('accept', 1, '简介已读'), 'pl_bj_tiantan': ('reject', '', '预约规则待核')})
    (tmp_path / 'lib').mkdir()
    assert run(tmp_path, out, review) == 0
    doc = placelib.load_city(tmp_path / 'lib' / 'beijing.v1.json')
    place = doc['places'][0]
    assert [p['id'] for p in doc['places']] == ['pl_bj_gugong'] and place['rank'] == 1
    assert place['review'] == {'status': 'approved', 'reviewer': 'JT', 'reviewed_on': '2026-11-30', 'note': '简介已读'}
    assert 'external_signals' not in place and place['location']['amap_id'] == 'B000A8UIN8'
    cands = {c['id']: c for c in json.loads((out / 'beijing.cand.json').read_text(encoding='utf-8'))['candidates']}
    assert cands['pl_bj_gugong']['status'] == 'accepted' and cands['pl_bj_tiantan']['status'] == 'rejected'
    lay = generate.Layout(tmp_path / 'lib', tmp_path / 'server', tmp_path / 'app.json')
    generate.write(lay)                                    # the next step of the flow works on what was written
    assert generate.stale(lay) == [] and validate.validate(lay, rules=[])[1] == []


def test_nothing_is_written_when_an_accept_cannot_be_built(tmp_path):
    out, review = imported(tmp_path, [C1, second()], fetch=fake_fetch([]))      # Amap finds nothing: no location
    fill(review, {'pl_bj_gugong': ('accept', 1, None)})
    (tmp_path / 'lib').mkdir()
    before = (out / 'beijing.cand.json').read_bytes()
    assert run(tmp_path, out, review) == 1
    assert not (tmp_path / 'lib' / 'beijing.v1.json').exists() and (out / 'beijing.cand.json').read_bytes() == before


def test_edit_keeps_the_candidate_pending_and_a_blank_row_is_untouched(tmp_path, capsys):
    out, review = imported(tmp_path, [C1, second()])
    fill(review, {'pl_bj_gugong': ('edit', '', '英文简介太长')})
    (tmp_path / 'lib').mkdir()
    assert run(tmp_path, out, review) == 0
    assert 'pl_bj_gugong: 英文简介太长' in capsys.readouterr().out
    cands = {c['id']: c for c in json.loads((out / 'beijing.cand.json').read_text(encoding='utf-8'))['candidates']}
    assert cands['pl_bj_gugong']['status'] == 'pending' and cands['pl_bj_gugong']['review_note'] == '英文简介太长'
    assert cands['pl_bj_tiantan']['status'] == 'pending' and not (tmp_path / 'lib' / 'beijing.v1.json').exists()


@pytest.mark.parametrize('cells', [('maybe', '', ''), ('edit', '', ''), ('accept', 'first', ''), ('accept', '0', '')])
def test_bad_cells_in_the_table_are_refused(tmp_path, cells):
    out, review = imported(tmp_path, [C1])
    fill(review, {'pl_bj_gugong': cells})
    assert run(tmp_path, out, review) == 1


def test_a_second_accept_with_the_same_name_is_caught_by_the_library_rules(tmp_path):
    twin = second(name_zh='故宫博物院', name_en='Twin Palace', aliases_zh=[], aliases_en=[])
    out, review = imported(tmp_path, [C1, twin])
    fill(review, {'pl_bj_gugong': ('accept', 1, None), 'pl_bj_tiantan': ('accept', 2, None)})
    (tmp_path / 'lib').mkdir()
    assert run(tmp_path, out, review) == 1                      # names must stay unique within a city
    assert not (tmp_path / 'lib' / 'beijing.v1.json').exists()


def test_accepting_again_replaces_the_entry_and_keeps_the_rest(tmp_path):
    out, review = imported(tmp_path, [C1, second()])
    fill(review, {'pl_bj_gugong': ('accept', 1, None)})
    (tmp_path / 'lib').mkdir()
    assert run(tmp_path, out, review) == 0
    # a later batch: the candidate file of the first run still lists both; accept the other one
    fill(review, {'pl_bj_gugong': ('', '', ''), 'pl_bj_tiantan': ('accept', 2, None)})
    assert run(tmp_path, out, review) == 0
    assert [p['id'] for p in placelib.load_city(tmp_path / 'lib' / 'beijing.v1.json')['places']] == ['pl_bj_gugong', 'pl_bj_tiantan']


def test_an_accept_never_overwrites_a_library_entry_unless_asked_and_says_so(tmp_path, capsys):
    out, review = imported(tmp_path, [C1, second()])
    fill(review, {'pl_bj_gugong': ('accept', 1, None)})
    (tmp_path / 'lib').mkdir()
    assert run(tmp_path, out, review) == 0
    first = (tmp_path / 'lib' / 'beijing.v1.json').read_bytes()
    capsys.readouterr()
    # the same id again: the candidate is no longer pending, and the entry is in the library
    fill(review, {'pl_bj_gugong': ('accept', 5, '再审')})
    assert run(tmp_path, out, review) == 1
    assert 'already in the library' in capsys.readouterr().err and (tmp_path / 'lib' / 'beijing.v1.json').read_bytes() == first
    assert run(tmp_path, out, review, '--replace') == 0
    printed = capsys.readouterr().out
    assert '1 replaced' in printed and 'replaced pl_bj_gugong' in printed
    assert placelib.load_city(tmp_path / 'lib' / 'beijing.v1.json')['places'][0]['rank'] == 5


@pytest.mark.parametrize('first, second_decision', [('reject', 'accept'), ('accept', 'reject')])
def test_only_a_pending_candidate_can_be_decided_on(tmp_path, capsys, first, second_decision):
    out, review = imported(tmp_path, [C1, second()])
    fill(review, {'pl_bj_gugong': (first, 1 if first == 'accept' else '', '第一次')})
    (tmp_path / 'lib').mkdir()
    assert run(tmp_path, out, review) == 0
    capsys.readouterr()
    fill(review, {'pl_bj_gugong': (second_decision, 1 if second_decision == 'accept' else '', '改主意')})
    assert run(tmp_path, out, review) == 1
    message = capsys.readouterr().err
    assert 'not pending' in message or 'in the library' in message


def test_a_kill_between_writing_and_renaming_leaves_the_old_files_and_no_temporary(tmp_path, monkeypatch):
    out, review = imported(tmp_path, [C1, second()])
    fill(review, {'pl_bj_gugong': ('accept', 1, None)})
    (tmp_path / 'lib').mkdir()
    before = (out / 'beijing.cand.json').read_bytes()
    monkeypatch.setattr(apply_review.os, 'replace', lambda *a: (_ for _ in ()).throw(OSError('disk full')))
    assert run(tmp_path, out, review) == 1
    assert (out / 'beijing.cand.json').read_bytes() == before and not (tmp_path / 'lib' / 'beijing.v1.json').exists()
    assert not list((tmp_path / 'lib').glob('.*')) and not list(out.glob('.*'))


def test_a_renamed_header_or_a_broken_candidate_file_is_a_clean_failure(tmp_path, capsys):
    out, review = imported(tmp_path, [C1])
    (tmp_path / 'lib').mkdir()
    table = review / 'beijing.review.csv'
    table.write_text(table.read_text(encoding='utf-8-sig').replace('decision', 'decision ', 1), encoding='utf-8-sig')
    assert run(tmp_path, out, review) == 1 and 'decision' in capsys.readouterr().err
    out2, review2 = imported(tmp_path / 'again', [C1])
    fill(review2, {'pl_bj_gugong': ('accept', 1, None)})
    doc = json.loads((out2 / 'beijing.cand.json').read_text(encoding='utf-8'))
    del doc['candidates'][0]['location']
    (out2 / 'beijing.cand.json').write_text(json.dumps(doc), encoding='utf-8')
    (tmp_path / 'lib').mkdir(exist_ok=True)
    assert run(tmp_path, out2, review2) == 1
    message = capsys.readouterr().err
    assert 'pl_bj_gugong' in message and 'malformed' in message
    del doc['candidates']
    (out2 / 'beijing.cand.json').write_text(json.dumps(doc), encoding='utf-8')
    assert run(tmp_path, out2, review2) == 1 and 'beijing.cand.json' in capsys.readouterr().err


def test_replace_only_re_reviews_an_accepted_candidate_and_an_edit_never_touches_the_library(tmp_path, capsys):
    out, review = imported(tmp_path, [C1, second()])
    (tmp_path / 'lib').mkdir()
    fill(review, {'pl_bj_gugong': ('accept', 1, None), 'pl_bj_tiantan': ('reject', '', '不要')})
    assert run(tmp_path, out, review) == 0
    capsys.readouterr()
    fill(review, {'pl_bj_gugong': ('edit', '', '改一下')})
    assert run(tmp_path, out, review, '--replace') == 1 and 'edit the library file' in capsys.readouterr().err
    # a cut-off run: the library has the entry but the candidate still says pending -> the message says what to do
    doc = json.loads((out / 'beijing.cand.json').read_text(encoding='utf-8'))
    next(c for c in doc['candidates'] if c['id'] == 'pl_bj_gugong')['status'] = 'pending'
    (out / 'beijing.cand.json').write_text(json.dumps(doc), encoding='utf-8')
    fill(review, {'pl_bj_gugong': ('accept', 1, None)})
    assert run(tmp_path, out, review) == 1 and 'set this candidate' in capsys.readouterr().err
    # --replace on a rejected candidate whose id is in the library is refused too
    doc = json.loads((out / 'beijing.cand.json').read_text(encoding='utf-8'))
    next(c for c in doc['candidates'] if c['id'] == 'pl_bj_gugong')['status'] = 'rejected'
    (out / 'beijing.cand.json').write_text(json.dumps(doc), encoding='utf-8')
    assert run(tmp_path, out, review, '--replace') == 1 and 'only re-reviews' in capsys.readouterr().err
