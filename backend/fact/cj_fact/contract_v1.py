"""FACT@1.0 bounded data codec over the existing source parser/evaluator."""
import base64
import binascii
from datetime import date, datetime
import json

from .acquisition import _json_bounds, parse_document
from .model import DateRange, Query, aware, evaluate
from .policy import FactFailure, SourcePolicy
from .structured import extract_structured_evidence

VERSION = 'FACT@1.0'
QUERY_VERSION = 'FACT-query.1'
RESULT_VERSION = 'FACT-result.1'
ORIGIN = 'https://synthetic-fact.g2c.invalid'
POLICY = SourcePolicy((ORIGIN,), 16384, 64, 1, 2, 16, 4096)
WIRE_POLICY = SourcePolicy((ORIGIN,), 131072, 1, 0, 2, 24, 16384)


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')


def load(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= WIRE_POLICY.max_bytes:
        raise FactFailure('bounded_fact_wire_required')
    try: text = raw.decode('utf8')
    except UnicodeError: raise FactFailure('invalid_fact_utf8') from None
    _json_bounds(text, WIRE_POLICY)
    return json.loads(text)


def exact(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        raise FactFailure('unexpected_fact_fields')


def text(value):
    if type(value) is not str or not value.strip() or len(value) > 256:
        raise FactFailure('bounded_fact_text_required')
    return value


def stamp(value):
    return dict(iso8601=value.isoformat(timespec='microseconds'), fold=value.fold)


def read_stamp(value):
    exact(value, 'iso8601 fold')
    if (type(value['iso8601']) is not str or len(value['iso8601']) > 64
            or type(value['fold']) is not int or value['fold'] not in (0, 1)):
        raise FactFailure('invalid_fact_timestamp')
    try:
        result = datetime.fromisoformat(value['iso8601']).replace(fold=value['fold'])
        aware(result)
    except (ValueError, OverflowError): raise FactFailure('invalid_fact_timestamp') from None
    if stamp(result) != value: raise FactFailure('noncanonical_fact_timestamp')
    return result


def encode_query(query: Query):
    if len(query.conditions) > 32: raise FactFailure('bounded_fact_conditions_required')
    return dump(dict(version=QUERY_VERSION, fact_key=text(query.fact_key), region=text(query.region),
                     dates=dict(start=query.dates.start.isoformat(), end=query.dates.end.isoformat()),
                     conditions={text(k):text(v) for k, v in query.conditions}))


def decode_query(raw, *, evaluated_at):
    value = load(raw)
    exact(value, 'version fact_key region dates conditions')
    if value['version'] != QUERY_VERSION: raise FactFailure('unsupported_fact_query_version')
    exact(value['dates'], 'start end')
    dates = []
    try:
        for key in ('start', 'end'):
            raw_date = value['dates'][key]
            if type(raw_date) is not str or len(raw_date) != 10: raise ValueError()
            parsed = date.fromisoformat(raw_date)
            if parsed.isoformat() != raw_date: raise ValueError()
            dates.append(parsed)
        conditions = value['conditions']
        if type(conditions) is not dict or len(conditions) > 32: raise ValueError()
        return Query(text(value['fact_key']), text(value['region']), DateRange(*dates),
                     tuple((text(k), text(v)) for k, v in conditions.items()), evaluated_at)
    except ValueError: raise FactFailure('invalid_fact_query') from None


def _declarations(evidence):
    def scalar(value): return None if value is None else value.value
    return dict(regions=scalar(evidence.regions),
        dates=None if evidence.dates is None else dict(start=evidence.dates.value.start.isoformat(), end=evidence.dates.value.end.isoformat()),
        conditions=None if evidence.conditions is None else dict(evidence.conditions.value),
        published_at=None if evidence.published_at is None else stamp(evidence.published_at.value),
        expires_at=None if evidence.expires_at is None else stamp(evidence.expires_at.value))


def encode_result(result, request_ref):
    if len(result.assessments) > 16: raise FactFailure('bounded_fact_sources_required')
    sources = []
    for assessment in result.assessments:
        e = assessment.evidence
        if not e.document.synthetic: raise FactFailure('synthetic_fact_source_required')
        POLICY.target(e.document.source_url)
        sources.append(dict(evidence_id=text(e.evidence_id), fact_key=text(e.fact_key),
            source_url=e.document.source_url, retrieved_at=stamp(e.document.retrieved_at),
            media_type=e.document.media_type,
            original_utf8_base64=base64.b64encode(e.document.original).decode('ascii'),
            original_sha256=e.document.sha256, value=dict(text=e.value.value,
                start=e.value.excerpt.start, end=e.value.excerpt.end),
            declarations=_declarations(e), status=assessment.status.value, reasons=assessment.reasons))
    raw = dump(dict(version=RESULT_VERSION, data_origin='synthetic', request_ref=text(request_ref),
        query=json.loads(encode_query(result.query)), evaluated_at=stamp(result.query.evaluated_at),
        outcome='ok' if sources else 'no_results', status=result.status.value,
        original_value=result.original_value, summary_zh=result.summary_zh,
        summary_en=result.summary_en, sources=sources))
    if len(raw) > WIRE_POLICY.max_bytes: raise FactFailure('fact_result_size_limit')
    return raw


FAILURES = {
    'rate_limited': ('合成来源限流，待核实。', 'Synthetic source rate limited; verification is needed.'),
    'invalid_response': ('合成来源内容无效，待核实。', 'Synthetic source content is invalid; verification is needed.'),
    'source_failure': ('合成来源失败，待核实。', 'Synthetic source failed; verification is needed.'),
}


def encode_failure(query, request_ref, outcome):
    zh, en = FAILURES[outcome]
    return dump(dict(version=RESULT_VERSION, data_origin='synthetic', request_ref=text(request_ref),
        query=json.loads(encode_query(query)), evaluated_at=stamp(query.evaluated_at), outcome=outcome,
        status='unknown', original_value=None, summary_zh=zh, summary_en=en, sources=[]))


def decode_result(raw):
    """Reparse source bytes/recompute derived data, never trust a supplied verdict."""
    value = load(raw)
    exact(value, 'version data_origin request_ref query evaluated_at outcome status original_value summary_zh summary_en sources')
    if value['version'] != RESULT_VERSION or value['data_origin'] != 'synthetic':
        raise FactFailure('unsupported_fact_result_version')
    if type(value['outcome']) is not str: raise FactFailure('invalid_fact_outcome')
    ref = text(value['request_ref'])
    query = decode_query(dump(value['query']), evaluated_at=read_stamp(value['evaluated_at']))
    if value['outcome'] in FAILURES:
        canonical = encode_failure(query, ref, value['outcome'])
    else:
        if type(value['sources']) is not list or len(value['sources']) > 16:
            raise FactFailure('bounded_fact_sources_required')
        evidence = []
        for source in value['sources']:
            exact(source, 'evidence_id fact_key source_url retrieved_at media_type original_utf8_base64 original_sha256 value declarations status reasons')
            try:
                encoded = source['original_utf8_base64']
                if type(encoded) is not str: raise ValueError()
                original = base64.b64decode(encoded, validate=True)
                if base64.b64encode(original).decode('ascii') != encoded: raise ValueError()
            except (ValueError, binascii.Error): raise FactFailure('invalid_fact_source_bytes') from None
            document = parse_document(source_url=source['source_url'], retrieved_at=read_stamp(source['retrieved_at']),
                content_type=source['media_type'], body=original, policy=POLICY, synthetic=True)
            evidence.append(extract_structured_evidence(document, evidence_id=text(source['evidence_id']),
                fact_key=text(source['fact_key']), policy=POLICY))
        try: result = evaluate(query, tuple(evidence))
        except ValueError: raise FactFailure('invalid_fact_evidence') from None
        canonical = encode_result(result, ref)
    # Compare JSON types as well as values (Python considers False == 0).
    expected = json.dumps(json.loads(canonical), sort_keys=True, ensure_ascii=False, allow_nan=False)
    actual = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    if expected != actual:
        raise FactFailure('fact_source_association_mismatch')
    return value
