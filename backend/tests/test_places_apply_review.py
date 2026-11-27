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
