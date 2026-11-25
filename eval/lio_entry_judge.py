"""Entry-facts model judge for Lio answers (JT 2026-11-26: approved model review).

Regex checks on free text could not reach zero false alarms on correct entry
statements (#1664, five review rounds). This judge gives the evaluator model the
answer plus that country's policies from the landing-mode rules file and asks
only whether the answer contradicts them (docs/lio-voice.md section 9.1: semantic
correctness belongs to model review).

Cost (JT 2026-11-26, authorization entry 4): one-time acceptance of about 300
labeled sentences, then 2 judge calls per evaluation run (the two entry cases).
The key comes only from CJ_MODEL_API_KEY and is never printed.

Usage:
  CJ_MODEL_API_KEY=... python -m eval.lio_entry_judge validate <acceptance.json> [--limit N]
  CJ_MODEL_API_KEY=... python -m eval.lio_entry_judge score <answers.json>
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
ARRIVAL_RULES = ROOT.parent / 'ios/Modules/CJShell/Sources/CJLioUser/Resources/LioArrivalRules.v1.json'
ENTRY_CASES = {'transit-visa-zh': 'US', 'visa-uk-en': 'GB'}
BASE = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
MODEL = 'qwen3.8-flash'
SYSTEM = (
    'You check one travel answer against official China entry rules for one passport country. '
    'Reply with JSON only: {"contradicts": true or false, "sentence": "<the contradicting sentence, or empty>"}. '
    'contradicts is true only when a statement in the answer, read in its context, conflicts with the supplied '
    'rules: a wrong stay length or limit, a wrong area or movement restriction, saying a visa is needed where the '
    'rules make the trip visa-free (or the reverse), or presenting a retired policy as current. '
    'It is false for statements that negate or correct a mistaken claim, describe past rules as past, ask a '
    'question, state conditions under which a visa is still required, or talk about things the rules do not '
    'cover. Missing information is not a contradiction. Judge only against the supplied rules.')


class JudgeUnavailable(ValueError):
    pass


def _rules():
    try:
        return json.loads(ARRIVAL_RULES.read_text())
    except (OSError, ValueError) as error:
        raise JudgeUnavailable('landing-mode rules unavailable: ' + ARRIVAL_RULES.name) from error


def country_rules(code):
    """The policies that apply to one passport country, as plain data for the judge."""
    rules = _rules()
    policies = {policy['id']: policy for policy in rules['policies']}
    country = next((row for row in rules['countries'] if row['code'] == code), None)
    if country is None:
        raise JudgeUnavailable('country not in landing-mode rules: ' + code)
    picked = [dict(id=key, kind=policies[key]['kind'], max_stay_days=policies[key]['max_stay_days'],
                   valid_from=policies[key]['valid_from'], valid_until=policies[key]['valid_until'],
                   summary=policies[key]['summary'], not_covered=policies[key].get('not_covered'))
              for key in country['policies']]
    return json.dumps(dict(passport=code, data_version=rules['data_version'], checked_at=rules['checked_at'],
                           policies=picked), ensure_ascii=False)


def judge_request(code, answer):
    return dict(model=MODEL, temperature=0, enable_thinking=False, response_format={'type': 'json_object'},
                messages=[dict(role='system', content=SYSTEM),
                          dict(role='user', content='Rules:\n' + country_rules(code) + '\n\nAnswer:\n' + answer)])


def parse_verdict(raw):
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise JudgeUnavailable('judge output is not JSON') from error
    if type(value) is not dict or type(value.get('contradicts')) is not bool:
        raise JudgeUnavailable('judge output lacks a boolean contradicts')
    sentence = value.get('sentence') or ''
    return value['contradicts'], sentence if type(sentence) is str else ''


def model_judge(key):
    import httpx

    def judge(code, answer):
        response = httpx.post(BASE + '/chat/completions', json=judge_request(code, answer),
                              headers={'Authorization': 'Bearer ' + key}, timeout=60)
        response.raise_for_status()
        return parse_verdict(response.json()['choices'][0]['message']['content'])
    return judge


def validate(rows, judge):
    """Accuracy of the judge on labeled sentences; a false alarm fails a correct sentence."""
    false_alarms, misses = [], []
    for row in rows:
        contradicts, _ = judge(row['country'], row['text'])
        if row['correct'] and contradicts:
            false_alarms.append(dict(country=row['country'], text=row['text']))
        elif not row['correct'] and not contradicts:
            misses.append(dict(country=row['country'], text=row['text']))
    total = len(rows)
    return dict(total=total, accuracy=round((total - len(false_alarms) - len(misses)) / total, 3) if total else None,
                false_alarms=len(false_alarms), misses=len(misses),
                correct_rows=sum(row['correct'] for row in rows), wrong_rows=sum(not row['correct'] for row in rows),
                false_alarm_rows=false_alarms, miss_rows=misses)


def score_answers(answers, judge):
    """entry_facts per entry case: True when the judge finds no contradiction."""
    results = {}
    for case, code in sorted(ENTRY_CASES.items()):
        if case not in answers:
            continue
        value = answers[case]
        text = value['text'] if isinstance(value, dict) else value
        contradicts, _ = judge(code, text)
        results[case] = not contradicts
    return dict(entry_facts=results, rate=round(sum(results.values()) / len(results), 3) if results else None)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m eval.lio_entry_judge')
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('validate')
    check.add_argument('acceptance')
    check.add_argument('--limit', type=int)
    score = sub.add_parser('score')
    score.add_argument('answers')
    args = parser.parse_args(argv)
    key = os.environ.get('CJ_MODEL_API_KEY')
    if not key:
        raise SystemExit('CJ_MODEL_API_KEY is required (never printed)')
    judge = model_judge(key)
    if args.command == 'validate':
        rows = json.loads(Path(args.acceptance).read_text())['rows'][:args.limit]
        result = validate(rows, judge)
    else:
        result = score_answers(json.loads(Path(args.answers).read_text()), judge)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
