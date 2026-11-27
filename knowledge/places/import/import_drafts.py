"""Import Codex drafts into place candidates and write the review table (#1986, F-4).

Reads `<inbox>/C1/*.json` (attractions), `<inbox>/C7/hubs.json` (hubs) and `<inbox>/C8/*.json` (food,
shopping, hotels). Every file is a JSON list of draft entries in the formats of `coord/codex/`. Drafts are
never trusted: an entry that fails `placelib.check_draft` goes to the rejected list, not the candidates.

For each clean entry the importer
  1. adds a GCJ-02 point and the Amap POI id (only with `--live`; otherwise the match is "not-run"),
  2. scores it (`score.py`),
  3. keeps it in `<out>/<city>.cand.json` with status "pending",
and writes the review table `<review>/<city>.review.csv|md`: pending entries in review order, in batches
of `--batch-size` (default 25: what JT can review in a day). Nothing enters `knowledge/places/<city>.v1.json`
without a person's decision (`apply_review.py`, #1988).

Re-running is safe: entries a person already decided are kept as they are, pending ones are refreshed.

Usage (repository root):
  python3 -B knowledge/places/import/import_drafts.py --inbox ../codex-inbox --today 2026-11-29            # offline
  CJ_AMAP_WEB_KEY=... python3 -B knowledge/places/import/import_drafts.py --inbox ../codex-inbox --live   # Amap lookups
"""
import argparse
import copy
import csv
import html
import io
import json
import os
from pathlib import Path
import re
import sys
import unicodedata

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import amap  # noqa: E402
import placelib  # noqa: E402
import score as scoring  # noqa: E402

VERSION = 'g2c-places-candidates.1'
DEFAULT_OUT = placelib.PLACES_DIR / 'candidates'
DEFAULT_REVIEW = placelib.PLACES_DIR / 'review'
# Draft files by folder: C1 `<city>.json`, C7 `hubs.json`, C8 `<city>-food|shopping|hotel.json`. Anything else in
# those folders (a manifest, Codex's `intro-rewrite-sources.json` side file) is not a list of places.
SOURCES = (('C1', r'(beijing|shanghai|guangzhou|shenzhen|chengdu|chongqing)\.json'), ('C7', r'hubs\.json'),
           ('C8', r'(beijing|shanghai|guangzhou|shenzhen|chengdu|chongqing)-(food|shopping|hotel)\.json'))
SKIP = {'manifest.json'}
AMAP_LABEL = {'exact': '名称一致', 'close': '名称相近', 'weak': '只是第一条结果，请核对', 'address-only': '只按地址定位',
              'none': '高德没找到', 'not-run': '未查询', 'error': '查询出错'}


def dumps(doc):
    return json.dumps(doc, ensure_ascii=False, indent=2) + '\n'


def normalise(entry):
    """The draft with every field of its category present (null when absent); `external_signals` set aside."""
    keys = placelib.fields_for(entry['category'], library=False)
    out = {key: entry.get(key) for key in keys if key != 'external_signals'}
    out['tier'] = entry.get('tier') or 'main'
    for key in ('aliases_zh', 'aliases_en'):
        out[key] = entry.get(key) or []
    return out, entry.get('external_signals') or []


def read_inbox(inbox):
    """([(source name, entry)], [file problems]) for every draft file found."""
    entries, problems = [], []
    for folder, pattern in SOURCES:
        for path in sorted((Path(inbox) / folder).glob('*.json')):
            if path.name in SKIP or path.name.startswith('.') or re.fullmatch(pattern, path.name) is None:
                continue
            name = f'{folder}/{path.name}'
            try:
                doc = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError) as error:
                problems.append({'file': name, 'id': None, 'errors': [f'unreadable: {type(error).__name__}']})
                continue
            if type(doc) is not list:
                problems.append({'file': name, 'id': None, 'errors': ['the file must be a JSON list of entries']})
                continue
            entries += [(name, entry) for entry in doc]
    return entries, problems


def _read_side(inbox, name):
    """The list in `<inbox>/C1/<name>` ([] when the file is not there; (list, problem) when it cannot be read)."""
    path = Path(inbox) / 'C1' / name
    if not path.is_file():
        return [], None
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        return [], f'C1/{name}: unreadable ({type(error).__name__}), ignored'
    if type(doc) is not list or not all(type(row) is dict and type(row.get('id')) is str for row in doc):
        return [], f'C1/{name}: not a list of objects with an id, ignored'
    return doc, None


def _fold(text):
    return unicodedata.normalize('NFKC', text).casefold().strip()


def _merged_aliases(own, extra):
    """`own` first (kept as they are), then the new ones that are text and not already there (NFKC, case-folded)."""
    seen, out = set(), []
    for item in list(own or []) + list(extra or []):
        if type(item) is str and item.strip() and _fold(item) not in seen:
            seen.add(_fold(item))
            out.append(item.strip())
    return out


def _apply_recheck(entry, row):
    """`entry` with one field-level recheck row applied (a new value, its source, the day it was read)."""
    field = row['field']
    if field.startswith('ticket.'):
        ticket = entry.get('ticket') if type(entry.get('ticket')) is dict else dict.fromkeys(
            ('booking', 'passport_required', 'price_cny', 'closed_weekdays', 'booking_channel_zh', 'booking_url'))
        ticket[field.split('.', 1)[1]] = row['new']
        entry['ticket'] = ticket
    else:
        entry[field] = row['new']
        if field == 'hours_zh' and entry.get('hours_source') is None:
            entry['hours_source'] = row.get('source')
    source = row.get('source')
    if type(source) is str and source not in (entry.get('sources') or []):
        entry['sources'] = list(entry.get('sources') or []) + [source]
    checked = row.get('checked_on')
    if type(checked) is str and checked > str(entry.get('checked_on') or ''):
        entry['checked_on'] = checked
    return entry


def apply_followups(entries, inbox, notes):
    """C1's later files laid over the drafts: ([(source, entry)], {id: [flags]}, {id: alias evidence}).

    * `C1/aliases.json`: every alias Codex found, added to the entry's own (which all stay); the evidence per
      alias is kept next to the candidate, so the reviewer can see where a spelling comes from.
    * `C1/recheck.json`: field-level rechecks. A new value is applied only when the entry is still a clean
      draft with it (otherwise a note says why); a `new: null` row means Codex could not confirm that field,
      which the review table shows as a flag. Values on a row whose `old` is not what the draft holds now are
      skipped (the draft changed since the recheck).
    """
    aliases, problem = _read_side(inbox, 'aliases.json')
    rows, other = _read_side(inbox, 'recheck.json')
    notes += [p for p in (problem, other) if p]
    aliases = {row['id']: row for row in aliases}
    rechecks = {}
    for row in rows:
        if type(row.get('field')) is str and 'new' in row and 'old' in row:
            rechecks.setdefault(row['id'], []).append(row)
    flags, evidence, out = {}, {}, []
    for source, entry in entries:
        ident = entry.get('id') if type(entry) is dict else None
        if ident is None or (ident not in aliases and ident not in rechecks):
            out.append((source, entry))
            continue
        entry = copy.deepcopy(entry)
        if ident in aliases:
            for lang in ('zh', 'en'):
                entry[f'aliases_{lang}'] = _merged_aliases(entry.get(f'aliases_{lang}'), aliases[ident].get(f'aliases_{lang}'))
            if aliases[ident].get('evidence'):
                evidence[ident] = aliases[ident]['evidence']
        for row in rechecks.get(ident, []):
            current = entry.get('ticket', {}).get(row['field'].split('.', 1)[1]) if row['field'].startswith('ticket.') and type(entry.get('ticket')) is dict \
                else (entry.get(row['field']) if not row['field'].startswith('ticket.') else None)
            if row['new'] is None:
                flags.setdefault(ident, []).append(f"{row['field']}: Codex could not confirm it from an official page; check by hand")
                continue
            if current != row['old']:
                notes.append(f"{ident}: recheck of {row['field']} skipped (the draft no longer holds the value it was made against)")
                continue
            trial = _apply_recheck(copy.deepcopy(entry), row)
            errors, _ = placelib.check_draft(trial, source)
            if errors:
                notes.append(f"{ident}: recheck of {row['field']} not applied ({errors[0]})")
                continue
            entry = trial
        out.append((source, entry))
    return out, flags, evidence


def read_image_ids(image_dir):
    """Ids that have a picture and its thumbnail in Codex's C2 folder (`manifest.json` + the PNG files). Only a
    pointer for the reviewer: the formal check of the pictures is `images/check_images.py`."""
    folder = Path(image_dir)
    try:
        listed = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return set()
    if type(listed) is not list:
        return set()
    return {row['id'] for row in listed if type(row) is dict and type(row.get('id')) is str
            and (folder / str(row.get('file'))).is_file() and (folder / str(row.get('thumb'))).is_file()}


def load_library_ids(library_dir):
    ids = set()
    for path in placelib.city_files(library_dir):
        ids |= {place['id'] for place in placelib.load_city(path)['places']}
    return ids


def process(inbox, today, fetch=None, use_external=False, library_dir=placelib.PLACES_DIR, existing=None, keep_signals=False):
    """Return ({city: [candidate]}, [rejected], [notes]). `fetch` None means no Amap lookups."""
    existing = existing or {}
    entries, rejected = read_inbox(inbox)
    in_library, seen, by_city, notes = load_library_ids(library_dir), {}, {}, []
    entries, followup_flags, alias_evidence = apply_followups(entries, inbox, notes)
    names = {}
    for source, entry in entries:
        errors, warnings = placelib.check_draft(entry, source)
        ident = entry.get('id') if isinstance(entry, dict) else None
        if not errors and ident in seen:
            errors = [f'{ident}: duplicate id (also in {seen[ident]})']
        if errors:
            rejected.append({'file': source, 'id': ident, 'errors': errors})
            continue
        seen[ident] = source
        if ident in in_library:
            notes.append(f'{ident}: already in the library, skipped')
            continue
        old = existing.get(ident)
        if old is not None and old['status'] != 'pending':
            by_city.setdefault(entry['city'], []).append(old)
            continue
        draft, signals = normalise(entry)
        location, info = None, {'status': 'not-run', 'alternatives': []}
        if fetch is not None:
            try:
                location, info = amap.locate(fetch, draft, today)
            except amap.AmapError as error:
                info = {'status': 'error', 'alternatives': [], 'message': str(error)}
                if 'stopping' in str(error):
                    raise
        flags = list(warnings) + followup_flags.get(ident, [])
        if entry['category'] == 'hotel' and draft.get('price_band') is None:
            flags.append('no price band: it cannot enter the library until the operator\'s own page gives a rate')
        key = (draft['city'], draft['name_zh'].casefold())
        if key in names:
            flags.append(f'possible duplicate of {names[key]} (same Chinese name)')
        names.setdefault(key, ident)
        by_city.setdefault(draft['city'], []).append({
            'id': ident, 'source_file': source, 'status': 'pending', 'draft': draft,
            'external_signals': signals if (keep_signals or use_external) else [], 'location': location, 'amap': info,
            'score': scoring.score(draft, info['status'], signals, use_external), 'flags': flags,
            **({'alias_evidence': alias_evidence[ident]} if ident in alias_evidence else {}),
        })
    for city, items in by_city.items():
        kept = {item['id'] for item in items}
        for ident, old in sorted(existing.items()):
            if old['draft']['city'] != city or ident in kept:
                continue
            if old['status'] == 'pending':  # Codex took it out of its files: it is no longer up for review
                notes.append(f'{ident}: no longer in the inbox, dropped from review')
            else:                           # a decision already made stays on record
                items.append(old)
        items.sort(key=lambda c: c['id'])
    return by_city, rejected, notes


def load_existing(out_dir):
    """{id: candidate} from the candidate files already written."""
    found = {}
    for city in placelib.CITIES:
        path = Path(out_dir) / f'{city}.cand.json'
        if path.is_file():
            doc = json.loads(path.read_text(encoding='utf-8'))
            found.update({item['id']: item for item in doc['candidates']})
    return found


# ---------------------------------------------------------------- review table

def _cell(value):
    text = '' if value is None else str(value)
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text  # no spreadsheet formulas from drafts


def review_rows(candidates, batch_size, images=frozenset()):
    pending = sorted((c for c in candidates if c['status'] == 'pending'), key=scoring.order_key)
    rows = []
    for index, cand in enumerate(pending):
        draft, info = cand['draft'], cand['amap']
        best = info['alternatives'][0] if info['alternatives'] else None
        point = (cand['location'] or {}).get('gcj02') or {}
        rows.append({
            'batch': index // batch_size + 1, 'id': cand['id'], 'category': draft['category'],
            'kind': draft.get('subcategory') or draft.get('hub_type'), 'tier': draft['tier'], 'score': cand['score']['total'],
            'name_zh': draft['name_zh'], 'name_en': draft['name_en'], 'district': draft.get('district_zh'),
            'amap_status': AMAP_LABEL[info['status']], 'amap_name': (cand['location'] or {}).get('amap_name'),
            'amap_address': best['address'] if best else None, 'lat': point.get('lat'), 'lng': point.get('lng'),
            'intro_zh': draft.get('intro_short_zh'), 'intro_en': draft.get('intro_short_en'),
            'hours': draft.get('hours_zh'), 'source': draft['sources'][0], 'image': '有' if cand['id'] in images else '',
            'flags': '；'.join(cand['flags']),
        })
    return rows


CSV_HEAD = ('batch', 'id', 'category', 'kind', 'tier', 'score', 'name_zh', 'name_en', 'district', 'amap_status', 'amap_name',
            'amap_address', 'lat', 'lng', 'intro_zh', 'intro_en', 'hours', 'source', 'image', 'flags')
CSV_LABELS = ('批次', 'id', '类别', '细类', '档', '分', '中文名', 'English name', '区', '高德匹配', '高德名称', '高德地址',
              '纬度', '经度', '简介', 'Intro', '开放时间', '来源', '示意图', '提醒')


def read_filled(path):
    """{id: (decision, rank, note)} the reviewer already typed into an existing table (empty cells ignored)."""
    path = Path(path)
    if not path.is_file():
        return {}
    with open(path, encoding='utf-8-sig', newline='') as handle:
        return {row['id']: (row.get('decision') or '', row.get('rank') or '', row.get('note') or '')
                for row in csv.DictReader(handle) if row.get('id') and any((row.get('decision'), row.get('rank'), row.get('note')))}


def render_csv(rows, filled=None):
    """Columns for the reviewer to fill in: decision (accept / reject / edit), rank (optional), note.
    Answers already typed into the previous table are carried over by id, never wiped by a re-import."""
    filled = filled or {}
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow([*CSV_LABELS, 'decision', 'rank', 'note'])
    for row in rows:
        writer.writerow([*(_cell(row[key]) for key in CSV_HEAD), *filled.get(row['id'], ('', '', ''))])
    return buffer.getvalue()


def render_md(city, rows, today):
    lines = [f'# {city} 收录审核（{today}）', '', f'共 {len(rows)} 条待审，按批次排列，每批可一天审完。'
             '决定写在 CSV 的 decision 列：accept、reject 或 edit（edit 在 note 里写要改什么）。', '']
    batch = None
    for row in rows:
        if row['batch'] != batch:
            batch = row['batch']
            lines += [f'## 第 {batch} 批', '']
        lines += [
            f'### {row["name_zh"]} · {row["name_en"]}  `{row["id"]}`',
            f'- {row["category"]}/{row["kind"]} · {row["tier"]} · 分数 {row["score"]} · {row["district"] or "区未知"}',
            f'- 高德：{row["amap_status"]}' + (f'（{row["amap_name"]}，{row["amap_address"] or "无地址"}，{row["lat"]},{row["lng"]}）' if row['lat'] else ''),
            f'- 简介：{row["intro_zh"] or "—"} / {row["intro_en"] or "—"}',
            f'- 开放时间：{row["hours"] or "—"}',
            f'- 来源：{row["source"]}',
        ]
        if row['image']:
            lines.append('- 示意图：有（AI 生成，须标「示意图」；预览见 --preview-dir 生成的页面）')
        if row['flags']:
            lines.append(f'- 提醒：{row["flags"]}')
        lines += ['- [ ] accept　[ ] reject　[ ] edit：', '']
    return '\n'.join(lines)


def render_preview(city, rows, image_dir, today):
    """A local page for the reviewer: the thumbnail next to each entry. Not for the repository (it names local paths)."""
    base = Path(image_dir).resolve().as_uri()
    esc = html.escape
    parts = ['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">',
             f'<title>{esc(city)} 收录预览 {esc(today)}</title>',
             '<style>body{font:15px/1.5 -apple-system,sans-serif;margin:24px auto;max-width:960px;padding:0 16px;color:#222}'
             '.c{display:flex;gap:16px;border-top:1px solid #ddd;padding:14px 0}.c img{width:160px;height:160px;object-fit:cover;border-radius:8px;background:#eee}'
             '.n{font-weight:600}.m{color:#666;font-size:13px}.f{color:#b45309}.tag{font-size:12px;border:1px solid #999;border-radius:4px;padding:0 4px;color:#555}</style>',
             f'<h1>{esc(city)} 收录预览</h1><p class="m">示意图为 AI 生成，在 App 里必须标「示意图」。决定写在 CSV 的 decision 列。</p>']
    batch = None
    for row in rows:
        if row['batch'] != batch:
            batch = row['batch']
            parts.append(f'<h2>第 {batch} 批</h2>')
        picture = (f'<img src="{base}/{esc(row["id"])}_thumb.png" alt="示意图 {esc(row["name_zh"])}">' if row['image']
                   else '<img alt="" style="visibility:hidden">')
        parts.append(
            f'<div class="c">{picture}<div><div class="n">{esc(row["name_zh"])} · {esc(row["name_en"])} <span class="m">{esc(row["id"])}</span>'
            + (' <span class="tag">示意图</span>' if row['image'] else '') + '</div>'
            f'<div class="m">{esc(str(row["category"]))}/{esc(str(row["kind"]))} · {esc(row["tier"])} · 分数 {row["score"]} · {esc(row["district"] or "区未知")} · 高德：{esc(row["amap_status"])}</div>'
            f'<div>{esc(row["intro_zh"] or "—")}</div><div class="m">{esc(row["intro_en"] or "—")}</div>'
            + (f'<div class="f">{esc(row["flags"])}</div>' if row['flags'] else '') + '</div></div>')
    return '\n'.join(parts) + '\n'


# ---------------------------------------------------------------- run

def write_outputs(by_city, rejected, notes, today, out_dir, review_dir, batch_size, images=frozenset(), image_dir=None, preview_dir=None):
    out_dir, review_dir = Path(out_dir), Path(review_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for city in placelib.CITIES:
        items = by_city.get(city)
        if not items:
            continue
        path = out_dir / f'{city}.cand.json'
        path.write_text(dumps({'version': VERSION, 'city': city, 'generated_on': today, 'candidates': items}), encoding='utf-8')
        rows = review_rows(items, batch_size, images)
        table = review_dir / f'{city}.review.csv'
        table.write_text(render_csv(rows, read_filled(table)), encoding='utf-8-sig')
        (review_dir / f'{city}.review.md').write_text(render_md(city, rows, today), encoding='utf-8')
        if preview_dir and image_dir:
            Path(preview_dir).mkdir(parents=True, exist_ok=True)
            (Path(preview_dir) / f'{city}.preview.html').write_text(render_preview(city, rows, image_dir, today), encoding='utf-8')
        written.append((city, len(items), len(rows)))
    report = out_dir / f'rejected-{today}.json'
    if rejected or notes:
        report.write_text(dumps({'rejected': rejected, 'notes': notes}), encoding='utf-8')
    elif report.is_file():  # a clean re-run must not leave the earlier run's problems behind
        report.unlink()
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--inbox', required=True, help='the codex-inbox directory')
    parser.add_argument('--today', required=True, help='YYYY-MM-DD, written into the files (the importer reads no clock)')
    parser.add_argument('--out', default=str(DEFAULT_OUT))
    parser.add_argument('--review', default=str(DEFAULT_REVIEW))
    parser.add_argument('--batch-size', type=int, default=25)
    parser.add_argument('--images', help="Codex's C2 folder with the pictures (default: <inbox>/C2); only entries that have a picture are marked")
    parser.add_argument('--preview-dir', help='write <city>.preview.html here (thumbnails next to each entry, for the reviewer; keep it outside the repository)')
    parser.add_argument('--live', action='store_true', help='look places up on Amap (needs the key in the environment)')
    parser.add_argument('--key-env', default='CJ_AMAP_WEB_KEY')
    parser.add_argument('--cache', help='directory for Amap answers (default: <inbox>/.amap-cache); never committed')
    parser.add_argument('--keep-external-signals', action='store_true',
                        help='keep Tripadvisor-style numbers in the candidate files (default: dropped; the repository is public and their terms are not settled)')
    parser.add_argument('--use-external-signals', action='store_true',
                        help='let Tripadvisor-style ranks count in the score (only after the terms decision)')
    args = parser.parse_args(argv)
    placelib.day(args.today, '--today')
    fetch = None
    if args.live:
        key = os.environ.get(args.key_env)
        if not key:
            print(f'--live needs the Amap Web Service key in ${args.key_env}', file=sys.stderr)
            return 2
        fetch = amap.make_fetch(key, cache_dir=args.cache or Path(args.inbox) / '.amap-cache')
    existing = load_existing(args.out)
    try:
        by_city, rejected, notes = process(args.inbox, args.today, fetch, args.use_external_signals, existing=existing,
                                            keep_signals=args.keep_external_signals)
    except amap.AmapError as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    image_dir = args.images or Path(args.inbox) / 'C2'
    images = read_image_ids(image_dir)
    for city, total, pending in write_outputs(by_city, rejected, notes, args.today, args.out, args.review, args.batch_size,
                                              images, image_dir, args.preview_dir):
        print(f'{city}: {total} candidates, {pending} pending review')
    print(f'{len(rejected)} rejected, {len(notes)} notes' + (f' (see rejected-{args.today}.json)' if rejected or notes else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
