"""Offline checks for model-written Lio prose; never dispatches or grants a save."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from pypinyin import lazy_pinyin

from evaluation.cj028.evaluate import latency, number, ratio, require

ROOT = Path(__file__).resolve().parent
CHECK_VERSION = 'LIO-voice-checks.1'
BANDS = {'short': {'zh': 30, 'en': 20}, 'default': {'zh': 80, 'en': 50},
         'expanded': {'zh': 150, 'en': 90}, 'unlimited': {'zh': None, 'en': None}}
SCENARIOS = ('emergency', 'in_china_today', 'change', 'planning', 'exploration',
             'practical', 'out_of_scope', 'greeting')
HAN = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U0002fa1f]')
WORD = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*|\d+(?:[.:]\d+)*", re.UNICODE)
SYSTEM_TERMS = (r'本轮|未核实|供应商|接口|数据库|存储|您|不构成预订|未保存|未预订|未调用|候选确认',
                r'(?<!交通)工具',
                r'\b(?:UNKNOWN|UNRUN|TripProposal|RLS|API|provider|database|'
                r'storage|backend|tool(?:s)?|this turn|noted)\b')
INTERNAL = re.compile(r'\b(?:lio-dialogue-|cnat-|run_id|message_id|request_id|'
                      r'source_refs|cj_m1_runtime|TripProposal|RLS)\b', re.I)
COORDINATES = re.compile(r'(?<!\w)[+-]?\d{1,3}\.\d{3,}\s*[,，]\s*'
                         r'[+-]?\d{1,3}\.\d{3,}(?!\w)')
LINK = re.compile(r'https?://\S+|\bwww\.\S+|\[[^\]]+\]\([^\n]+\)|<a\b|'
                  r'\b[a-z0-9][a-z0-9.-]+\.(?:com|cn|org|net|gov|edu|io|space)\b', re.I)
TABLE = re.compile(r'^\s*\|?.*\|.*\n\s*\|?\s*:?-{3,}:?\s*\|', re.M)
HEADING = re.compile(r'^\s{0,3}#{1,6}\s+|^\s*\*\*[^\n]+\*\*\s*$|'
                     r'^.+\n\s*(?:={3,}|-{3,})\s*$|<h[1-6]\b', re.M | re.I)
LIST_ITEM = re.compile(r'^\s*(?:[-+*•▪◦]\s+|(?:\d+|[一二三四五六七八九十]+)'
                       r'[.)、．）](?:\s+|(?=[\u3400-\u9fff])))', re.M)
MODEL_CRITERIA = ('direct_answer', 'useful_question', 'useful_uncertainty')


def load_cases():
    raw = (ROOT / 'lio_voice_cases.v1.json').read_bytes()
    doc = json.loads(raw)
    require(doc['version'] == 'LIO-voice-cases.1', 'unsupported voice cases')
    cases = doc['cases']
    require(len(cases) == 30 and len({c['id'] for c in cases}) == 30, 'expected 30 unique cases')
    require(Counter(c['locale'] for c in cases) == {'zh': 15, 'en': 15}, 'expected 15 per language')
    for case in cases:
        require(case['scenario'] in SCENARIOS and case['length_band'] in BANDS, 'invalid case category')
        require(type(case['question']) is str and bool(case['question'].strip()), 'missing question')
    return doc, hashlib.sha256(raw).hexdigest()


def count_units(text, locale, pinyin=()):
    # Pinyin metadata comes from the frozen case/source annotation, never model output.
    # Chinese characters do not produce English tokens. Plain unmarked pinyin needs annotation.
    plain = re.sub(r'[*_`#]', '', unicodedata.normalize('NFC', text))
    if locale == 'zh':
        return len(re.sub(r'\s', '', plain))
    for phrase in sorted(pinyin, key=len, reverse=True):
        plain = re.sub(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', '', plain, flags=re.I)
    # Verify pronunciation against the adjacent Chinese; an accented English
    # word such as cafe must not become a pinyin length exemption.
    def annotation(match):
        tail = match[2]
        words = WORD.findall(tail)
        def roman(value):
            return ''.join(c for c in unicodedata.normalize('NFD',value).casefold() if 'a'<=c<='z')
        expected=roman(''.join(lazy_pinyin(match[1])))
        return match[1] if words and roman(tail)==expected else match[0]
    plain = re.sub(r'([\u3400-\u9fff]+)\s+([A-Za-z\u00c0-\u024f\u0300-\u036f ]+)(?=\))',
                   annotation, plain)
    return len(WORD.findall(HAN.sub(' ', plain)))


def check_answer(case, answer):
    """Deterministic surface checks; factual and omitted-name review stays separate."""
    require(type(answer) is str and bool(answer.strip()), 'missing model answer')
    locale, band = case['locale'], case['length_band']
    units = count_units(answer, locale, case.get('pinyin', ()))
    maximum = BANDS[band][locale]
    exempt = case['scenario'] == 'emergency' or case.get('farewell', False)
    ending = answer.rstrip().rstrip('*_`\"\'”’」』)]）').rstrip()
    question_ok = exempt or (ending.endswith(('?', '？')) and len(re.findall(r'[?？]', answer)) == 1)
    # An unrelated Han character cannot cover a known, mentioned place/dish alias.
    names = [n for n in case.get('names', ()) if any(re.search(r'(?<!\w)' + re.escape(a) + r'(?!\w)',
             answer, re.I) for a in n['aliases'])]
    name_ok = locale != 'en' or all(n['chinese'] in answer for n in names)
    if locale == 'en' and case.get('expects_chinese') and not names:
        name_ok = bool(HAN.search(answer))
    bullets = len(LIST_ITEM.findall(answer))
    language = re.sub(r'\b(?:luggage|baggage)\s+storage\b', 'luggage lockers', answer, flags=re.I)
    system_hits = [m.group() for pattern in SYSTEM_TERMS for m in re.finditer(pattern, language, re.I)]
    checks = dict(length=maximum is None or units <= maximum, closing_question=question_ok,
                  chinese_names=name_ok, no_tables=not (TABLE.search(answer) or re.search(r'<table\b', answer, re.I)),
                  no_headings=not HEADING.search(answer), no_links=not LINK.search(answer),
                  list_limit=bullets <= (0 if band == 'short' else 3), system_language=not system_hits)
    redline_signals = []
    if INTERNAL.search(answer) or COORDINATES.search(answer):
        redline_signals.append('internal_identifier_or_coordinates')
    if re.search(r'https?://[^\s]*(?:amap|dashscope|supabase|/v[13]/)', answer, re.I):
        redline_signals.append('provider_endpoint')
    if case['scenario'] == 'emergency' and not re.search(r'\b(?:110|120)\b', re.split(r'[.!。！\n]', answer)[0]):
        redline_signals.append('emergency_first_sentence_missing_help_number')
    return dict(version=CHECK_VERSION, units=units, unit='visible_characters' if locale == 'zh' else 'words',
                length_band=band, maximum=maximum, list_items=bullets,
                checks={k: 'PASS' if v else 'FAIL' for k, v in checks.items()}, system_hits=system_hits,
                redline_signals=redline_signals,
                semantic_review='UNKNOWN: first answer, useful question, uncertainty, name omissions and factual/action/identity redlines need grounded review')


def calibration(samples, judgments):
    """Compare actual model judgments to independent human labels, without inventing either."""
    rows = samples['samples']
    require(len(rows) == 20 and len({r['id'] for r in rows}) == 20, 'expected 20 unique calibration samples')
    require(set(judgments) <= {r['id'] for r in rows}, 'unknown model judgment sample')
    results = {}
    for item in MODEL_CRITERIA:
        known, matches = 0, 0
        for row in rows:
            human, model = row['human_labels'][item], judgments.get(row['id'], {}).get(item)
            require(human in (None, 'PASS', 'FAIL') and model in (None, 'PASS', 'FAIL'), 'invalid calibration verdict')
            if human is not None:
                require(bool(row.get('human_reviewer')) and bool(row.get('human_label_ref')), 'human label needs attribution and reference')
            if human is not None and model is not None:
                known += 1
                matches += human == model
        results[item] = dict(status='COMPLETE' if known == 20 else 'UNRUN' if known == 0 else 'INCOMPLETE',
                             agreement=ratio(matches, known), planned_n=20, missing_n=20-known)
    return results


def summarize(cases, observations, *, evidence_kind='UNQUALIFIED'):
    """One fixed arm. Missing/failed outputs stay in the planned denominator."""
    ids = {c['id'] for c in cases}
    require(evidence_kind in ('UNQUALIFIED','fixture','real_service'), 'explicit evidence layer required')
    require(set(observations) <= ids, 'unknown observation case')
    checked, clocks = [], []
    model_verdicts = {k: [] for k in MODEL_CRITERIA}
    for case in cases:
        row = observations.get(case['id'])
        if row is None or row.get('status') != 'completed':
            checked.append(None)
            clocks.append(None)
            continue
        require(row.get('evidence_ref') and row.get('run_id'), 'completed output needs original evidence and RUN')
        if evidence_kind == 'real_service':
            require(not row['evidence_ref'].startswith(('synthetic:','fixture:')), 'fixture reference cannot certify a real-service arm')
        seconds = row.get('first_paragraph_seconds')
        require(seconds is None or number(seconds), 'invalid first paragraph clock')
        review = row.get('model_review')
        if review is not None:
            require(review.get('run_id') == row['run_id']
                    and review.get('answer_sha256') == hashlib.sha256(row['answer'].encode()).hexdigest()
                    and review.get('ref') and review.get('reviewer')
                    and review.get('prompt_sha256') == hashlib.sha256((ROOT / 'lio_voice_judge_prompts.md').read_bytes()).hexdigest(),
                    'model review must bind the original answer/RUN and frozen prompt')
            require(set(review['verdicts']) <= set(MODEL_CRITERIA), 'unknown model review criterion')
            for item, verdict in review['verdicts'].items():
                require(verdict in ('PASS', 'FAIL'), 'invalid model verdict')
                model_verdicts[item].append(verdict)
        checked.append(check_answer(case, row['answer']))
        clocks.append(dict(first_paragraph_seconds=seconds))
    keys = ('length', 'closing_question', 'chinese_names', 'no_tables', 'no_headings', 'no_links', 'list_limit', 'system_language')
    rates = {k: ratio(sum(r is not None and r['checks'][k] == 'PASS' for r in checked), len(cases)) for k in keys}
    signals = sum(len(r['redline_signals']) for r in checked if r)
    reviewed = 0
    for case in cases:
        row = observations.get(case['id'], {})
        review = row.get('redline_review', {})
        reviewed += (review.get('outcome') == 'PASS' and review.get('kind') in ('human', 'program')
                     and review.get('independent') is True and bool(review.get('ref'))
                     and review.get('run_id') == row.get('run_id') and bool(row.get('run_id')))
    redline_fails = sum(observations.get(c['id'], {}).get('redline_review', {}).get('outcome') == 'FAIL' for c in cases)
    missing = sum(r is None for r in checked)
    impossible = any((r['numerator'] + missing) / r['denominator'] < .9 for r in rates.values())
    gate = 'FAIL' if signals or redline_fails or impossible else 'UNKNOWN'
    if all(checked) and reviewed == len(cases):
        gate = 'PASS' if not (signals or redline_fails) and all(r['value'] >= .9 for r in rates.values()) else 'FAIL'
    control_gate = gate
    if evidence_kind != 'real_service':
        gate = 'UNRUN' if evidence_kind == 'fixture' else 'UNKNOWN'
    histogram = Counter()
    for case, result in zip(cases, checked):
        if result:
            category = next((band for band in ('short', 'default', 'expanded')
                             if result['units'] <= BANDS[band][case['locale']]), 'above_expanded')
            histogram[category] += 1
    return dict(planned_n=len(cases), completed_prose_n=sum(r is not None for r in checked), check_rates=rates,
                model_check_rates={k: dict(status='UNRUN' if not v else 'COMPLETE' if len(v) == len(cases) else 'INCOMPLETE',
                    pass_rate=ratio(v.count('PASS'), len(cases)), known_n=len(v), fail_n=v.count('FAIL'),
                    missing_n=len(cases)-len(v)) for k, v in model_verdicts.items()},
                lengths=[dict(id=c['id'], band=c['length_band'], units=r['units']) for c, r in zip(cases, checked) if r],
                expected_length_bands=dict(Counter(r['length_band'] for r in checked if r)),
                actual_length_distribution=dict(histogram),
                length_summary=latency([dict(units=r['units']) if r else None for r in checked], 'units'),
                first_paragraph=latency(clocks, 'first_paragraph_seconds'),
                code_redline_signals=signals, grounded_redline_pass_n=reviewed,
                grounded_redline_fail_n=redline_fails, evidence_kind=evidence_kind,
                fixture_or_unqualified_control_gate=control_gate, stage1_gate=gate)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('compare', 'calibrate'))
    parser.add_argument('input', type=Path, help='Offline old/new bundle, or actual model judgments for calibration')
    args = parser.parse_args()
    if args.mode == 'calibrate':
        samples = json.loads((ROOT / 'lio_voice_calibration.v1.json').read_bytes())
        print(json.dumps(calibration(samples, json.loads(args.input.read_bytes())), ensure_ascii=False, indent=2))
        return
    dataset, digest = load_cases()
    bundle = json.loads(args.input.read_bytes())
    require(bundle['dataset_sha256'] == digest, 'dataset digest mismatch')
    require(set(bundle['arms']) == {'old', 'new'}, 'need old and new arms')
    result = dict(dataset_sha256=digest, arms={})
    for name, arm in bundle['arms'].items():
        require(all(arm.get(k) for k in ('source_commit', 'prompt_sha256', 'model_profile', 'window_id')), 'missing arm provenance')
        require(arm.get('evidence_kind') in ('fixture','real_service'), 'missing arm evidence layer')
        result['arms'][name] = dict(provenance={k: arm[k] for k in ('source_commit', 'prompt_sha256', 'model_profile', 'window_id')},
                                  languages={locale: summarize([c for c in dataset['cases'] if c['locale'] == locale],
                                      {k: v for k, v in arm['observations'].items() if k in {c['id'] for c in dataset['cases'] if c['locale'] == locale}},
                                      evidence_kind=arm['evidence_kind'])
                                             for locale in ('zh', 'en')})
        require(set(arm['observations']) <= {c['id'] for c in dataset['cases']}, 'unknown arm case ID')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
