"""Markdown reports for release evaluation runs (#1761 W6-1). Offline only.

Usage:
  python -m eval.release_eval.report compare OLD_RUN.json NEW_RUN.json [--output REPORT.md]
  python -m eval.release_eval.report single RUN.json [--output REPORT.md]

A case got worse when it has fewer passing answers or more must_not_say hits than before;
it got better when it has more passing answers or fewer hits and did not get worse.
"""
import argparse
from pathlib import Path
import sys

from eval.release_eval.bank import load_bank
from eval.release_eval.score import load_run, score_run

META = (('source_sha', '源提交'), ('model', '模型'), ('started_at', '开始时间'), ('bank_version', '题库版本'),
        ('repeats', '每题次数'), ('sender', '发送方式'))


def _cell(value):
    if value is None:
        return '—'
    if type(value) is float:
        value = round(value, 3)
    return str(value).replace('|', '\\|').replace('\n', ' ')


def _diff(old, new):
    if type(old) not in (int, float) or type(new) not in (int, float):
        return '—'
    delta = round(new - old, 3)
    return ('+' if delta > 0 else '') + str(delta)


def _metrics(summary):
    return [
        ('通过题数', summary['passed_cases']), ('已答题数', summary['answered_cases']),
        ('通过回答数', summary['passed_answers']), ('must_say 命中率', summary['must_say_hit_rate']),
        ('must_not_say 违规数', summary['violations']), ('违规回答数', summary['violation_answers']),
        ('错误数', summary['errors']),
        ('首字 p50 (ms)', summary['first_token_ms']['p50']), ('首字 p95 (ms)', summary['first_token_ms']['p95']),
        ('完整 p50 (ms)', summary['total_ms']['p50']), ('完整 p95 (ms)', summary['total_ms']['p95']),
    ] + [(f'混合题通过 ({k})' if k == 'mixed' else f'{k} 通过', v['passed'])
         for k, v in sorted(summary['by_kind'].items())]


def _case_lines(row):
    lines = []
    for detail in row['violation_details']:
        lines.append(f"  - 违规 `{detail['source']}`：「{_cell(detail['snippet'])}」")
    for group in row['missed_must_say']:
        lines.append(f'  - 漏说：{_cell(group)}')
    if row['v1_failed']:
        lines.append('  - v1 检查未过：' + ', '.join(row['v1_failed']))
    for message in row['error_messages']:
        lines.append(f'  - 错误：{_cell(message)[:80]}')
    return lines


def _errors(title, scored):
    rows = [row for row in scored['cases'].values() if row['errors']]
    lines = [f'## {title}（{sum(r["errors"] for r in rows)} 次）', '']
    for row in rows:
        lines.append(f"- {row['id']}：{row['errors']}/{row['runs']} 次；" + '；'.join(_cell(m)[:80] for m in row['error_messages']))
    if scored['missing']:
        lines.append('- 未作答：' + ', '.join(scored['missing']))
    return lines + ([] if rows or scored['missing'] else ['无']) + ['']


def single_report(scored):
    s = scored['summary']
    lines = ['# 发布评测单次报告', '', '| 项 | 值 |', '|---|---|']
    lines += [f'| {label} | {_cell(scored["run"].get(key))} |' for key, label in META]
    lines += [f'| 题目数 | {s["cases"]} |']
    lines += [f'| {label} | {_cell(value)} |' for label, value in _metrics(s)]
    failed = [row for row in scored['cases'].values() if not row['passed']]
    lines += ['', f'## 未通过的题（{len(failed)}）', '']
    for row in failed:
        lines.append(f"- **{row['id']}**（{row['kind']}/{row['locale']}）通过 {row['passed_runs']}/{row['runs']}，违规 {row['violations']}")
        lines += _case_lines(row)
    if not failed:
        lines.append('无')
    lines += [''] + _errors('错误', scored)
    return '\n'.join(lines)


def classify(old, new):
    """(worse, better) case ids among cases answered in both runs."""
    worse, better = [], []
    for case_id, b in new['cases'].items():
        a = old['cases'].get(case_id)
        if a is None:
            continue
        if b['passed_runs'] < a['passed_runs'] or b['violations'] > a['violations']:
            worse.append(case_id)
        elif b['passed_runs'] > a['passed_runs'] or b['violations'] < a['violations']:
            better.append(case_id)
    return worse, better


def compare_report(old, new):
    so, sn = old['summary'], new['summary']
    lines = ['# 发布评测对比报告', '', '| 项 | 旧 | 新 | 差值 |', '|---|---|---|---|']
    lines += [f'| {label} | {_cell(old["run"].get(key))} | {_cell(new["run"].get(key))} | |' for key, label in META]
    lines += [f'| 题目数 | {so["cases"]} | {sn["cases"]} | {_diff(so["cases"], sn["cases"])} |']
    for (label, a), (_, b) in zip(_metrics(so), _metrics(sn)):
        lines.append(f'| {label} | {_cell(a)} | {_cell(b)} | {_diff(a, b)} |')
    worse, better = classify(old, new)
    for title, ids in (('变差的题', worse), ('变好的题', better)):
        lines += ['', f'## {title}（{len(ids)}）', '']
        for case_id in ids:
            a, b = old['cases'][case_id], new['cases'][case_id]
            lines.append(f"- **{case_id}**（{b['kind']}/{b['locale']}）通过 {a['passed_runs']}/{a['runs']} → "
                         f"{b['passed_runs']}/{b['runs']}，违规 {a['violations']} → {b['violations']}")
            if title == '变差的题':
                lines += _case_lines(b)
        if not ids:
            lines.append('无')
    lines += ['', '## 耗时对比（每题中位数，按完整耗时变化从大到小，前 10）', '',
              '| 题 | 首字 旧 | 首字 新 | 完整 旧 | 完整 新 | 完整差值 |', '|---|---|---|---|---|---|']
    pairs = [(old['cases'][i], row) for i, row in new['cases'].items() if i in old['cases']]
    pairs = [p for p in pairs if p[0]['total_ms_median'] is not None and p[1]['total_ms_median'] is not None]
    pairs.sort(key=lambda p: p[1]['total_ms_median'] - p[0]['total_ms_median'], reverse=True)
    for a, b in pairs[:10]:
        lines.append(f"| {b['id']} | {_cell(a['first_token_ms_median'])} | {_cell(b['first_token_ms_median'])} | "
                     f"{_cell(a['total_ms_median'])} | {_cell(b['total_ms_median'])} | {_diff(a['total_ms_median'], b['total_ms_median'])} |")
    lines += [''] + _errors('新一次的错误', new)
    only_old = sorted(set(old['cases']) - set(new['cases']))
    only_new = sorted(set(new['cases']) - set(old['cases']))
    if only_old or only_new:
        lines += ['## 只在一次运行中作答的题', '', '- 只在旧：' + (', '.join(only_old) or '无'),
                  '- 只在新：' + (', '.join(only_new) or '无'), '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m eval.release_eval.report')
    sub = parser.add_subparsers(dest='command', required=True)
    compare = sub.add_parser('compare')
    compare.add_argument('old')
    compare.add_argument('new')
    single = sub.add_parser('single')
    single.add_argument('run')
    for p in (compare, single):
        p.add_argument('--output')
    args = parser.parse_args(argv)
    try:
        cases = load_bank()
        if args.command == 'compare':
            text = compare_report(score_run(cases, load_run(args.old)), score_run(cases, load_run(args.new)))
        else:
            text = single_report(score_run(cases, load_run(args.run)))
    except ValueError as error:
        raise SystemExit(str(error))
    if args.output:
        Path(args.output).write_text(text + '\n', encoding='utf8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
