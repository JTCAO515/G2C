"""Warn in CI 14 days before a fact the product serves goes stale (#1757); never blocks a merge.

Reads only the review dates of the fact data the App and the server use:
- knowledge/visitor live entries (entries/, entries-v2/, entries-v3/, names/): expires_on, the day
  readers stop returning the entry;
- the arrival rules (knowledge/arrival, the source of the App and server copies): checked_at + review_every_days for the file and each policy, and each
  policy's valid_until (the official end date; the day after it the rule no longer holds).

Each item gets a due day (the first day it is stale) and its own review period (due day minus the
day it was checked). The warning starts the shorter of 14 days and half that period before the due
day (#1757, agreed with the coordinating thread 2026-11-26): an entry re-checked every 14 days, such
as passport booking rules, warns in its last 7 days instead of from the day it was checked. Inside
that lead time it prints a GitHub ::warning annotation; on or after the due day an ::error annotation. Both show on the run
and the pull request, and a table goes to the job summary when GITHUB_STEP_SUMMARY is set. The exit
code is 0 either way: an expiry is fixed by re-checking the source, not by holding every merge.
It exits 1 only when a listed file cannot be read or a date is not YYYY-MM-DD, as the check is then
blind. Format rules stay with knowledge/visitor/validate*.py; this script does not repeat them.

Usage: python3 -B scripts/fact_expiry.py [--as-of YYYY-MM-DD] [--window 14] [--json]
"""
import argparse
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
WINDOW_DAYS = 14
# Live visitor knowledge; candidates/, examples/ and the other *-candidates/ folders are not served.
VISITOR_DIRS = ('knowledge/visitor/entries', 'knowledge/visitor/entries-v2', 'knowledge/visitor/entries-v3',
                'knowledge/visitor/names')
# The single source since #1730; the App and server copies are generated from it (knowledge/arrival/sync_copies.py).
ARRIVAL_RULES = 'knowledge/arrival/arrival-rules.v1.json'


class DataError(Exception):
    pass


@dataclass(frozen=True)
class Item:
    path: str
    id: str
    kind: str    # 'expires' | 'review' | 'policy_end'
    due: str     # first stale day, YYYY-MM-DD
    period: int  # days from the check to the due day; the warning lead is at most half of it


def day(value, where):
    if not isinstance(value, str) or re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) is None:
        raise DataError(f'{where}: date must be YYYY-MM-DD, got {value!r}')
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DataError(f'{where}: {exc}') from exc


def read_json(root, rel):
    try:
        return json.loads((root / rel).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise DataError(f'{rel}: {exc}') from exc


def visitor_items(root):
    items = []
    for folder in VISITOR_DIRS:
        paths = sorted((root / folder).glob('*.json'))
        if not paths:
            raise DataError(f'{folder}: no entry files')
        for path in paths:
            rel = path.relative_to(root).as_posix()
            records = read_json(root, rel)
            if not isinstance(records, list):
                raise DataError(f'{rel}: expected an entry array')
            for index, record in enumerate(records):
                where = f'{rel} entry {index}'
                if not isinstance(record, dict) or not isinstance(record.get('id'), str):
                    raise DataError(f'{where}: no id')
                expires = day(record.get('expires_on'), where)
                checked = day(record.get('checked_on'), where)
                items.append(Item(rel, record['id'], 'expires', expires.isoformat(), (expires - checked).days))
    return items


def arrival_items(root):
    data = read_json(root, ARRIVAL_RULES)
    every = data.get('review_every_days')
    if not isinstance(every, int) or isinstance(every, bool) or every <= 0:
        raise DataError(f'{ARRIVAL_RULES}: review_every_days must be a positive integer')
    review = lambda checked, where: (day(checked, where) + timedelta(days=every)).isoformat()
    items = [Item(ARRIVAL_RULES, 'arrival-rules', 'review', review(data.get('checked_at'), ARRIVAL_RULES), every)]
    for index, policy in enumerate(data.get('policies') or []):
        where = f'{ARRIVAL_RULES} policy {index}'
        name = policy.get('id') if isinstance(policy.get('id'), str) else f'policy {index}'
        checked = policy.get('checked_at')
        items.append(Item(ARRIVAL_RULES, name, 'review', review(checked, where), every))
        if policy.get('valid_until') is not None:
            end = day(policy['valid_until'], where) + timedelta(days=1)
            # An official end date is not a review cycle: the full window applies.
            items.append(Item(ARRIVAL_RULES, name, 'policy_end', end.isoformat(), 2 * WINDOW_DAYS))
    return items


def collect(root=ROOT):
    return visitor_items(root) + arrival_items(root)


def lead_days(item, window=WINDOW_DAYS):
    """Days before the due day the warning starts: the window, or half the item's period if shorter."""
    return max(1, min(window, item.period // 2))


def classify(items, *, as_of, window=WINDOW_DAYS):
    """(expired, due soon): due on or before as_of, and due within the item's lead time."""
    expired = sorted((i for i in items if i.due <= as_of.isoformat()), key=lambda i: (i.due, i.path, i.id))
    soon = sorted((i for i in items
                   if as_of.isoformat() < i.due <= (as_of + timedelta(days=lead_days(i, window))).isoformat()),
                  key=lambda i: (i.due, i.path, i.id))
    return expired, soon


LABEL = {'expires': '条目到期', 'review': '复核到期', 'policy_end': '政策截止'}


def escape(text):
    return text.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def annotations(expired, soon, *, as_of):
    lines = []
    for item in expired:
        lines.append(f'::error file={item.path},title=事实数据已过期（{LABEL[item.kind]}）::'
                     + escape(f'{item.id} 自 {item.due} 起已过期，请对照来源复核后更新日期（不挡合并）'))
    for item in soon:
        left = (date.fromisoformat(item.due) - as_of).days
        lines.append(f'::warning file={item.path},title=事实数据将到期（{LABEL[item.kind]}）::'
                     + escape(f'{item.id} 将于 {item.due} 过期，还剩 {left} 天，请提前复核'))
    return lines


def summary(expired, soon, *, as_of, window):
    rows = [f'### 事实数据到期预警（{as_of.isoformat()}，提前 {window} 天）', '',
            f'已过期 {len(expired)} 项，进入预警期 {len(soon)} 项（提前 {window} 天与复核周期一半取较短者）。', '']
    if expired or soon:
        rows += ['| 状态 | 失效日 | 类型 | 条目 | 文件 |', '|---|---|---|---|---|']
        rows += [f'| 已过期 | {i.due} | {LABEL[i.kind]} | `{i.id}` | `{i.path}` |' for i in expired]
        rows += [f'| 将到期 | {i.due} | {LABEL[i.kind]} | `{i.id}` | `{i.path}` |' for i in soon]
    return '\n'.join(rows) + '\n'


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--as-of', help='test clock YYYY-MM-DD; default is today in Asia/Shanghai')
    parser.add_argument('--window', type=int, default=WINDOW_DAYS, help='longest warning lead in days')
    parser.add_argument('--json', action='store_true', help='print the lists as JSON instead of annotations')
    args = parser.parse_args(argv)
    try:
        as_of = day(args.as_of, '--as-of') if args.as_of else datetime.now(ZoneInfo('Asia/Shanghai')).date()
        expired, soon = classify(collect(root), as_of=as_of, window=args.window)
    except DataError as exc:
        print(f'::error title=事实数据到期检查读不了数据::{escape(str(exc))}')
        return 1
    if args.json:
        print(json.dumps({'as_of': as_of.isoformat(), 'window_days': args.window,
                          'expired': [asdict(i) for i in expired], 'due_soon': [asdict(i) for i in soon]},
                         ensure_ascii=False, indent=2))
        return 0
    for line in annotations(expired, soon, as_of=as_of):
        print(line)
    print(f'fact expiry: {len(expired)} expired, {len(soon)} in their warning lead (at most {args.window} days; as of {as_of})')
    target = os.environ.get('GITHUB_STEP_SUMMARY')
    if target:
        with open(target, 'a', encoding='utf-8') as handle:
            handle.write(summary(expired, soon, as_of=as_of, window=args.window))
    return 0


if __name__ == '__main__':
    sys.exit(main())
