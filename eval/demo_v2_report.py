"""Summarize original Demo v2 runs, independent verdicts, and attributed Meter rows."""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path

from fees import usage


SCENES = tuple(f'{prefix}{index:02d}' for prefix in ('Z', 'E') for index in range(1, 6))
LIO_PHASE_SCENES = {
    1: ('Z01', 'Z02', 'Z06', 'E01', 'E02', 'E06'),
    2: ('Z03', 'E03'),
    3: ('Z04', 'Z05', 'E04', 'E05'),
    4: SCENES,
}
OUTCOMES = ('PASS', 'FAIL', 'UNKNOWN', 'UNRUN')
INDEPENDENT_VERDICTS = ('program', 'human')
CLOCKS = ('first_server_progress_seconds', 'first_running_or_tool_seconds',
          'first_app_visible_progress_seconds', 'first_body_seconds', 'complete_seconds')
PAID_TOOLS = {'place', 'route', 'weather'}
KINDS = PAID_TOOLS | {'model', 'fact'}


def _tool_amount(value):
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError('original tool estimate needs decimal text')
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise ValueError('original tool estimate needs decimal text') from error
    if not amount.is_finite() or amount < 0:
        raise ValueError('original tool estimate must be finite and nonnegative')
    return amount


def _fees(attempts, meter_complete):
    value = usage(attempts)
    tools = [row for row in attempts if row['kind'] in PAID_TOOLS]
    estimates = [_tool_amount(row.get('estimated_cny')) if row['state'] == 'RECEIVED' else None
                 for row in tools]
    known = sum((amount for amount in estimates if amount is not None), Decimal(0))
    model = value['token_price_estimate']
    return dict(conservative_known_cny=value['conservative_hold_cny'], meter_complete=meter_complete,
                estimated_model_known_cny=model['known_receipt_subtotal_cny'],
                estimated_model_complete=meter_complete and not model['unknown_model_attempts'],
                estimated_tool_known_cny=str(known), estimated_tool_complete=meter_complete and None not in estimates,
                model_tokens=value['model_tokens_from_complete_receipts'], calls=value['call_attempts_by_kind'],
                unresolved=value['unknown_intents'], actual_billed_cny='UNKNOWN')


def summarize(attempts, *, lio_phase=None):
    """Input rows identify an original attempt, its runs and its attributed Meter.

    A null meter is missing evidence; an empty meter is a verified zero-call set.
    Each scene's first attempt counts in the fixed denominator. Further attempts
    retain their own verdict, timings and costs without replacing the first.
    """
    planned_scenes = SCENES if lio_phase is None else LIO_PHASE_SCENES[lio_phase]
    by_scene = {scene: [] for scene in planned_scenes}
    all_runs, all_actions, all_meters = set(), set(), set()
    all_rows = []
    for source in attempts:
        scene, index, verdict = source['scene'], source['attempt'], source['verdict']
        if (scene not in by_scene or type(index) is not int or index != len(by_scene[scene]) + 1 or
                verdict not in OUTCOMES[:-1]):
            raise ValueError('original scene attempts must be in order')
        if verdict in ('PASS', 'FAIL') and (source.get('verdict_basis') not in INDEPENDENT_VERDICTS or
                not isinstance(source.get('verdict_ref'), str) or not source['verdict_ref'].strip()):
            raise ValueError('independent scene verdict reference required')
        runs = []
        run_ids = set()
        for row in source['runs']:
            run = row['run_id']
            if not isinstance(run, str) or not run or run in all_runs:
                raise ValueError('original RUN may be reported once')
            clocks = {key: row.get(key) for key in CLOCKS}
            if any(value is not None and (type(value) not in (int, float) or
                    not math.isfinite(value) or value < 0) for value in clocks.values()):
                raise ValueError('invalid original client clock')
            if clocks['complete_seconds'] is not None and (clocks['first_body_seconds'] is None or
                    clocks['complete_seconds'] < clocks['first_body_seconds']):
                raise ValueError('complete clock needs the original first body')
            all_runs.add(run)
            run_ids.add(run)
            evidence = row['evidence_ref']
            if not isinstance(evidence, str) or not evidence.strip():
                raise ValueError('original RUN evidence reference required')
            runs.append(dict(run_id=run, evidence_ref=evidence, **clocks))
        if verdict == 'PASS' and not runs:
            raise ValueError('scene PASS requires original RUN evidence')
        actions = []
        for row in source.get('actions', ()):
            action = row['action_id']
            if not isinstance(action, str) or not action or action in all_actions:
                raise ValueError('original action may be reported once')
            all_actions.add(action)
            actions.append({key: row[key] for key in ('action_id', 'operation', 'evidence_ref')})
        meter = source['meter']
        rows = [] if meter is None else meter
        for row in rows:
            identity = row['attempt_id']
            if (not isinstance(identity, str) or not identity or identity in all_meters or
                    row['run_id'] not in run_ids or row['kind'] not in KINDS or
                    row['state'] not in ('INTENT', 'RECEIVED')):
                raise ValueError('Meter must attach once to an original scene RUN')
            all_meters.add(identity)
        all_rows.extend(rows)
        by_scene[scene].append(dict(attempt=index, verdict=verdict, verdict_basis=source.get('verdict_basis'),
            verdict_ref=source.get('verdict_ref'),
            runs=runs, actions=actions, meter_attempt_ids=[row['attempt_id'] for row in rows], fees=_fees(rows, meter is not None)))
    states = {scene: rows[0]['verdict'] if rows else 'UNRUN' for scene, rows in by_scene.items()}
    languages = {}
    for language, prefix in (('zh', 'Z'), ('en', 'E')):
        counts = Counter(states[scene] for scene in states if scene.startswith(prefix))
        planned = sum(counts.values())
        group = dict(planned=planned, outcomes={key: counts[key] for key in OUTCOMES},
                     success_rate=None if counts['UNRUN'] == planned else counts['PASS'] / planned)
        if lio_phase is not None:
            latest = Counter((rows[-1]['verdict'] if rows else 'UNRUN')
                             for scene, rows in by_scene.items() if scene.startswith(prefix))
            group['latest_outcomes'] = {key: latest[key] for key in OUTCOMES}
            group['latest_success_rate'] = None if latest['UNRUN'] == planned else latest['PASS'] / planned
        languages[language] = group
    report = dict(scenes=by_scene, first_attempt_outcomes=states, languages=languages,
                  fees=_fees(all_rows, bool(attempts) and all(row['meter'] is not None for row in attempts)))
    if lio_phase is not None:
        report['lio_phase'] = lio_phase
    return report


def markdown(report):
    phase = report.get('lio_phase')
    lines = [f'# Lio 阶段 {phase} 冒烟' if phase is not None else '# Demo v2 零配置冒烟', '']
    if 'batch' in report:
        batch = report['batch']
        lines += [f'部署 `{batch["source"]}`／`{batch["image"]}`，原账本 `{batch["ledger_start"]}` → '
                  f'`{batch["ledger_end"]}`。', '']
    lines += ['| 语言 | 计划 | PASS | FAIL | UNKNOWN | UNRUN | 已证实成功／计划 |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for language, group in report['languages'].items():
        rate = group['success_rate']
        values = [language, str(group['planned']), *(str(group['outcomes'][key]) for key in OUTCOMES),
                  'UNRUN' if rate is None else f'{rate:.0%}']
        lines.append('| ' + ' | '.join(values) + ' |')
    if phase is not None:
        lines += ['', '最近一次尝试单列，首次结果及所有复跑见下表。', '']
        for language, group in report['languages'].items():
            rate = group['latest_success_rate']
            latest = group['latest_outcomes']
            label = 'UNRUN' if rate is None else f'{rate:.0%}'
            lines.append(f'- {language.upper()} {latest["PASS"]}/{group["planned"]}（{label}）')
    lines += ['', '分母固定。每场首次尝试决定该场计数，复跑单列。时钟按原 RUN 分开，实付保留 UNKNOWN。', '',
              '| 场景／尝试 | 结论 | 原 RUN | 首状态／开始运行／App 显示／首正文／完整（秒） | 保守已知模型／工具 | 已知模型估算／工具估算 | 实付 |',
              '|---|---|---|---|---|---|---|']
    for scene, attempts in report['scenes'].items():
        if not attempts:
            lines.append(f'| {scene} | UNRUN | — | — | — | — | UNKNOWN |')
        for attempt in attempts:
            fees = attempt['fees']
            reserved = fees['conservative_known_cny']
            holds = f'¥{reserved["model"]}／¥{reserved["tool"]}' if fees['meter_complete'] else 'UNKNOWN'
            estimates = []
            for kind in ('model', 'tool'):
                known = fees[f'estimated_{kind}_known_cny']
                if fees[f'estimated_{kind}_complete']:
                    estimates.append(f'¥{known}')
                elif Decimal(known) > 0:
                    estimates.append(f'UNKNOWN（已知 ¥{known}）')
                else:
                    estimates.append('UNKNOWN')
            clocks = ['／'.join(f'{run[key]:.3f}' if run[key] is not None else 'UNKNOWN' for key in CLOCKS)
                      for run in attempt['runs']]
            lines.append(f'| {scene}／{attempt["attempt"]} | {attempt["verdict"]} | '
                         f'{"<br>".join(run["run_id"] for run in attempt["runs"]) or "—"} | '
                         f'{"<br>".join(clocks) or "—"} | {holds} | {"／".join(estimates)} | UNKNOWN |')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--lio-phase', type=int, choices=LIO_PHASE_SCENES)
    args = parser.parse_args()
    evidence = json.loads(args.evidence.read_bytes())
    report = summarize(evidence['attempts'], lio_phase=args.lio_phase)
    report['batch'] = {key: evidence['batch'][key] for key in ('source', 'image', 'ledger_start', 'ledger_end')}
    args.output.mkdir(mode=0o700)
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (args.output / 'report.md').write_text(markdown(report))


if __name__ == '__main__':
    main()
