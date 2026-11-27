"""Offline evaluation of tappable answers (#2011, Q-1): entity links, follow-up coverage, tool-card parameters.

Pure code, no model, no network. It measures what the server decides by rule (`cj_message.lio_entities`,
`lio_followups`, `lio_cards`), over annotated answers and questions; it does not judge the model's prose
(`eval.lio_answer_quality` does that) and it never dispatches a message.

    python -m eval.lio_rich_eval                         # synthetic library (CI), prints the report
    python -m eval.lio_rich_eval --library dev           # the development pack knowledge/places/dev (unreviewed)
    python -m eval.lio_rich_eval --library dev --strict  # exit 1 when a target is missed

Targets (strategy/59-implementation-logic.md, acceptance for 59α):
    entity precision >= 0.98, recall >= 0.80, follow-up coverage 1.0, card parameter accuracy 1.0.
The development pack has no reviewed aliases, so its recall is a measurement of that gap, not a pass or fail of
the linker; precision and the other two are real gates. When the reviewed library lands, run it again on it.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CASES = Path(__file__).resolve().parent / 'lio_rich_cases.v1.json'
DEV_PACK = ROOT / 'knowledge/places/dev/places-dev-pack.v1.json'
ANSWER_QUALITY_CASES = Path(__file__).resolve().parent / 'lio_answer_quality_cases.v1.json'
FOLLOWUP_CASES = Path(__file__).resolve().parent / 'lio_followup_cases.v1.json'
VERSION = 'LIO-rich-eval.1'
TARGETS = dict(entity_precision=0.98, entity_recall=0.80, followup_coverage=1.0, card_accuracy=1.0)
DEV_LIBRARY_NOTE = 'unreviewed development pack: every place is treated as approved for this measurement only'


def load_cases(path=CASES):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if value.get('version') != 'LIO-rich-eval-cases.1' or type(value.get('entities')) is not list or type(value.get('cards')) is not list:
        raise ValueError('not a LIO-rich-eval case file')
    return value


def dev_docs(path=DEV_PACK):
    """The development pack as library documents, one per city, every place marked approved *in memory only*."""
    pack = json.loads(Path(path).read_text(encoding='utf-8'))
    by_city = {}
    for place in pack['places']:
        by_city.setdefault(place['city'], []).append(dict(place, review=dict(status='approved')))
    return {city: dict(version='g2c-places.1', city=city, places=places) for city, places in by_city.items()}


def entity_metrics(cases, docs):
    """Precision and recall of `lio_entities.link` over the annotated answers; `docs` maps city id to its document."""
    from cj_message import lio_entities as ent
    produced = correct = expected = found = 0
    rows = []
    for case in cases:
        city = ent.city_for_adcode(case['adcode'])
        answer = case['answer']
        links = [(answer[s:e], pid) for s, e, pid in ent.link(answer, [docs[city]] if city in docs else [])]
        want = [tuple(item) for item in case['expected']]
        right = want + [tuple(item) for item in case.get('acceptable', [])]
        hit = [link for link in links if link in right]
        produced += len(links)
        correct += len(hit)
        expected += len(want)
        found += len([w for w in want if w in links])
        rows.append(dict(id=case['id'], produced=links, missed=[w for w in want if w not in links], wrong=[l for l in links if l not in right]))
    return dict(precision=round(correct / produced, 4) if produced else 1.0, recall=round(found / expected, 4) if expected else 1.0,
                produced=produced, correct=correct, expected=expected, found=found, rows=rows)


def question_bank(paths=(ANSWER_QUALITY_CASES, FOLLOWUP_CASES)):
    """The last traveler turn of every case of the answer-quality banks (#1761 and the follow-up bank), with its locale."""
    bank = []
    for path in paths:
        for case in json.loads(Path(path).read_text(encoding='utf-8'))['cases']:
            if case.get('turns'):
                bank.append((case['id'], case['turns'][-1], case['locale']))
    return bank


def followup_metrics(bank):
    """Share of normal answers whose chips are two or three, distinct, and not the question itself."""
    from cj_message import lio_followups as fu
    bad = []
    for cid, question, locale in bank:
        chips = fu.chips_for(question, locale)
        if not (fu.MIN_CHIPS <= len(chips) <= fu.MAX_CHIPS) or len(set(chips)) != len(chips) or question.strip() in chips:
            bad.append(cid)
    return dict(coverage=round(1 - len(bad) / len(bank), 4) if bank else 1.0, n=len(bank), uncovered=bad)


def card_metrics(cases):
    """Whether every card the table builds for a question has exactly the expected type and parameters / data."""
    from cj_message import lio_cards as cards
    from cj_message import lio_entities as ent
    from cj_message.lio_followups import Destination, topics
    right, rows = 0, []
    for case in cases:
        destination = case.get('destination')
        built = cards.build(case['question'], case['locale'], destination=Destination(**destination) if destination else None,
                            library_city=ent.city_for_adcode(case.get('adcode')), taxi_topic='taxi' in topics(case['question']))
        got = [dict(type=card['type'], **({'parameters': card['open']['parameters']} if card['open']['parameters'] else {}),
                    **({'data': card['data']} if 'data' in card else {})) for card in built]
        want = [dict(type=item['type'], **({'parameters': item['parameters']} if item.get('parameters') else {}),
                     **({'data': item['data']} if item.get('data') else {})) for item in case['expected']]
        ok = got == want
        right += ok
        rows.append(dict(id=case['id'], ok=ok, got=got, want=want))
    return dict(accuracy=round(right / len(cases), 4) if cases else 1.0, n=len(cases), wrong=[row['id'] for row in rows if not row['ok']], rows=rows)


def run(library='dev', cases_path=CASES, docs=None):
    value = load_cases(cases_path)
    documents = docs if docs is not None else dev_docs()
    entities = entity_metrics(value['entities'], documents)
    followups = followup_metrics(question_bank())
    tool_cards = card_metrics(value['cards'])
    report = dict(version=VERSION, library=library, note=DEV_LIBRARY_NOTE if library == 'dev' else '', generated=int(time.time()),
                  entity_precision=entities['precision'], entity_recall=entities['recall'], followup_coverage=followups['coverage'],
                  card_accuracy=tool_cards['accuracy'], targets=TARGETS,
                  entities=entities, followups=followups, cards=tool_cards)
    report['missed'] = [name for name, target in TARGETS.items() if report[name] < target]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m eval.lio_rich_eval')
    parser.add_argument('--library', choices=('dev',), default='dev')
    parser.add_argument('--cases', default=str(CASES))
    parser.add_argument('--strict', action='store_true', help='exit 1 when any target is missed')
    parser.add_argument('--rows', action='store_true', help='print the per-case rows')
    args = parser.parse_args(argv)
    report = run(args.library, args.cases)
    if not args.rows:
        for part in ('entities', 'cards'):
            report[part] = {k: v for k, v in report[part].items() if k != 'rows'}
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 1 if args.strict and report['missed'] else 0


if __name__ == '__main__':
    sys.exit(main())
