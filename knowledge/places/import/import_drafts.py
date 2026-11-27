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
import csv
import io
import json
import os
from pathlib import Path
import re
import sys

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
        flags = list(warnings)
        key = (draft['city'], draft['name_zh'].casefold())
        if key in names:
            flags.append(f'possible duplicate of {names[key]} (same Chinese name)')
        names.setdefault(key, ident)
        by_city.setdefault(draft['city'], []).append({
            'id': ident, 'source_file': source, 'status': 'pending', 'draft': draft,
            'external_signals': signals if (keep_signals or use_external) else [], 'location': location, 'amap': info,
            'score': scoring.score(draft, info['status'], signals, use_external), 'flags': flags,
        })
    for city, items in by_city.items():  # pending entries that disappeared from the inbox stay
        kept = {item['id'] for item in items}
        items += [old for ident, old in existing.items() if old['draft']['city'] == city and ident not in kept]
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


def review_rows(candidates, batch_size):
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
            'hours': draft.get('hours_zh'), 'source': draft['sources'][0], 'flags': '；'.join(cand['flags']),
        })
    return rows


CSV_HEAD = ('batch', 'id', 'category', 'kind', 'tier', 'score', 'name_zh', 'name_en', 'district', 'amap_status', 'amap_name',
            'amap_address', 'lat', 'lng', 'intro_zh', 'intro_en', 'hours', 'source', 'flags')
CSV_LABELS = ('批次', 'id', '类别', '细类', '档', '分', '中文名', 'English name', '区', '高德匹配', '高德名称', '高德地址',
              '纬度', '经度', '简介', 'Intro', '开放时间', '来源', '提醒')


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
        if row['flags']:
            lines.append(f'- 提醒：{row["flags"]}')
        lines += ['- [ ] accept　[ ] reject　[ ] edit：', '']
    return '\n'.join(lines)


# ---------------------------------------------------------------- run

def write_outputs(by_city, rejected, notes, today, out_dir, review_dir, batch_size):
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
        rows = review_rows(items, batch_size)
        table = review_dir / f'{city}.review.csv'
        table.write_text(render_csv(rows, read_filled(table)), encoding='utf-8-sig')
        (review_dir / f'{city}.review.md').write_text(render_md(city, rows, today), encoding='utf-8')
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
    for city, total, pending in write_outputs(by_city, rejected, notes, args.today, args.out, args.review, args.batch_size):
        print(f'{city}: {total} candidates, {pending} pending review')
    print(f'{len(rejected)} rejected, {len(notes)} notes' + (f' (see rejected-{args.today}.json)' if rejected or notes else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
