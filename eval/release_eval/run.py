"""Batch runner interface for the release evaluation (#1761 W6-1). No network code lives here.

A Sender turns one case into one answer: `send(case, turn_texts)` returns
{"text", "first_token_ms", "total_ms", "error"}; a multi-turn case is one send whose sender plays
every turn and returns the last answer. `FixtureSender` replays answers from a JSON file for
tests and report rehearsals. The real sender (Hong Kong dispatch adapter) is not implemented:
the adapter and the post-release hook are left to the coordination thread.

Real calls are refused unless `--real`, `--max-calls` and `--max-cost-cny` are all given (plus
`--cost-per-turn-cny` to estimate the cost), and the plan fits both limits.

Usage:
  python -m eval.release_eval.run plan [--repeats 3] [--cost-per-turn-cny P]
  python -m eval.release_eval.run run --fixture ANSWERS.json --output RUN.json [--repeats 3]
  python -m eval.release_eval.run run --real --max-calls N --max-cost-cny X --cost-per-turn-cny P --output RUN.json
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Protocol

from eval.lio_voice import strict_json
from eval.release_eval.bank import VERSION, load_bank
from eval.release_eval.score import validate_run

REPEATS = 3
REAL_REQUIRED = '拒绝真调用：必须同时给 --real、--max-calls、--max-cost-cny 和 --cost-per-turn-cny'


class Sender(Protocol):
    name: str

    def send(self, case: dict, turn_texts: list[str]) -> dict:
        """One answer: {"text", "first_token_ms", "total_ms", "error"}."""


class FixtureSender:
    """Replays answers per case id in order, cycling when a case has fewer answers than repeats."""
    name = 'fixture'

    def __init__(self, answers):
        self.answers = answers
        self._next = Counter()

    @classmethod
    def from_file(cls, path):
        value = strict_json(Path(path).read_bytes())
        if type(value) is not dict or not all(type(v) is list for v in value.values()):
            raise ValueError('fixture must map case id to a list of answers')
        return cls(value)

    def send(self, case, turn_texts):
        items = self.answers.get(case['id'])
        if not items:
            return dict(text=None, first_token_ms=None, total_ms=None, error='fixture has no answer')
        item = items[self._next[case['id']] % len(items)]
        self._next[case['id']] += 1
        if type(item) is str:
            return dict(text=item, first_token_ms=None, total_ms=None, error=None)
        return dict(dict(text=None, first_token_ms=None, total_ms=None, error=None), **item)


class RealSender:
    """Placeholder: the Hong Kong dispatch adapter is decided by the coordination thread (#1761)."""
    name = 'real'

    def __init__(self, **_):
        raise NotImplementedError('真实 Sender 未实现：香港发题适配层和发布后挂点待统筹决定（#1761）')


def plan(cases, repeats=REPEATS, cost_per_turn_cny=None):
    turns = sum(len(case['turns']) for case in cases) * repeats
    return dict(cases=len(cases), repeats=repeats, calls=len(cases) * repeats, model_turns=turns,
                cost_per_turn_cny=cost_per_turn_cny,
                estimated_cost_cny=None if cost_per_turn_cny is None else round(turns * cost_per_turn_cny, 4))


def real_refusal(planned, max_calls, max_cost_cny):
    """Why a real run must not start, or None when every limit is given and the plan fits."""
    if max_calls is None or max_cost_cny is None or planned['estimated_cost_cny'] is None:
        return REAL_REQUIRED
    if planned['calls'] > max_calls:
        return f'拒绝真调用：计划 {planned["calls"]} 次调用，超过 --max-calls {max_calls}'
    if planned['estimated_cost_cny'] > max_cost_cny:
        return f'拒绝真调用：估算 ¥{planned["estimated_cost_cny"]}，超过 --max-cost-cny {max_cost_cny}'
    return None


def execute(cases, sender, repeats=REPEATS, meta=None, max_calls=None):
    """Send every case `repeats` times; sender exceptions become answer errors."""
    if max_calls is not None and len(cases) * repeats > max_calls:
        raise ValueError(f'{len(cases) * repeats} calls exceed max_calls {max_calls}')
    run = dict(meta or {}, bank_version=VERSION, repeats=repeats, sender=sender.name,
               started_at=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    answers = {}
    for case in cases:
        for _ in range(repeats):
            try:
                result = sender.send(case, list(case['turns']))
                item = {key: result.get(key) for key in ('text', 'first_token_ms', 'total_ms', 'error')}
            except Exception as error:  # one failed send must not stop the batch
                item = dict(text=None, first_token_ms=None, total_ms=None, error=f'{type(error).__name__}: {error}')
            answers.setdefault(case['id'], []).append(item)
    value = dict(run=run, answers=answers)
    validate_run(value)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m eval.release_eval.run')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('plan', 'run'):
        p = sub.add_parser(name)
        p.add_argument('--repeats', type=int, default=REPEATS)
        p.add_argument('--cost-per-turn-cny', type=float)
    run = sub.choices['run']
    run.add_argument('--fixture')
    run.add_argument('--real', action='store_true')
    run.add_argument('--max-calls', type=int)
    run.add_argument('--max-cost-cny', type=float)
    run.add_argument('--output')
    run.add_argument('--source-sha')
    run.add_argument('--model')
    args = parser.parse_args(argv)
    if args.repeats < 1:
        raise SystemExit('--repeats must be at least 1')
    cases = load_bank()
    planned = plan(cases, args.repeats, args.cost_per_turn_cny)
    if args.command == 'plan':
        print(json.dumps(planned, ensure_ascii=False))
        return 0
    if args.real == bool(args.fixture):
        raise SystemExit('run 需要 --fixture（离线回放）或 --real（真调用）二选一；' + REAL_REQUIRED)
    if args.real:
        refusal = real_refusal(planned, args.max_calls, args.max_cost_cny)
        if refusal:
            raise SystemExit(refusal)
    if not args.output:
        raise SystemExit('run 需要 --output')
    output = Path(args.output)
    if output.exists():
        raise SystemExit(f'{output} 已存在；每次运行写新文件，保留历史结果')
    try:
        sender = RealSender() if args.real else FixtureSender.from_file(args.fixture)
    except NotImplementedError as error:
        raise SystemExit(str(error))
    meta = dict(source_sha=args.source_sha, model=args.model)
    value = execute(cases, sender, args.repeats, meta, args.max_calls)
    output.write_text(json.dumps(value, ensure_ascii=False, indent=1) + '\n', encoding='utf8')
    print(json.dumps(planned, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
