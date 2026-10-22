"""Narrow JSON evidence extraction; not a provider selector or a public HTTP schema.

Only the explicitly documented field layout is supported. No natural-language
inference, fallback field names, source translation or default validity is used.
"""
import json
from datetime import date, datetime

from .model import DateRange, Declared, Document, Evidence, Excerpt, aware
from .policy import FactFailure, SourcePolicy
from .acquisition import parse_document


def _fields(text):
    """Get exact top-level value spans after the bounded duplicate-free JSON check."""
    decoder = json.JSONDecoder()
    index = 0
    def skip_space(position):
        while position < len(text) and text[position] in ' \r\n\t':
            position += 1
        return position
    index = skip_space(index)
    if text[index] != '{':
        raise FactFailure('structured_object_required')
    index = skip_space(index + 1)
    fields = {}
    while text[index] != '}':
        key, index = decoder.raw_decode(text, index)
        index = skip_space(index)
        if text[index] != ':':
            raise FactFailure('malformed_json')
        start = skip_space(index + 1)
        value, end = decoder.raw_decode(text, start)
        fields[key] = (value, Excerpt(start, end, text[start:end]))
        index = skip_space(end)
        if text[index] == '}':
            break
        index = skip_space(index + 1)
    return fields


def extract_structured_evidence(document: Document, *, evidence_id: str, fact_key: str,
                                policy: SourcePolicy) -> Evidence:
    """Extract the source's exact typed declarations; this does NOT verify its truth.

    The caller chooses an evidence ID and semantic fact key; source content cannot
    select a tool, identity, query, budget, runtime or system instruction. Layout:
    value (required JSON scalar), regions (string array), dates ({start,end} ISO
    dates), conditions ({key:string}), published_at/expires_at (aware ISO stamps).
    Missing/null optional fields stay absent. Unexpected fields stay only in raw
    bytes; never turned into instructions. A source-specific adapter must be
    separately accepted before using a real source with a different layout.
    """
    if document.media_type != 'application/json':
        raise FactFailure('structured_json_required')
    # Reapply explicit bounds even for a caller-constructed Document.
    parse_document(source_url=document.source_url, retrieved_at=document.retrieved_at,
                   content_type=document.media_type, body=document.original, policy=policy,
                   synthetic=document.synthetic)
    try:
        fields = _fields(document.text)
        if 'value' not in fields or fields['value'][0] is None or type(fields['value'][0]) in (dict, list):
            raise FactFailure('structured_value_required')
        # Keep exact JSON literal, including escapes/negation/currency/date. A
        # consumer may display this literal, not relabel a translation as official.
        value = Declared(fields['value'][1].text, fields['value'][1])
        def optional(name, convert):
            if name not in fields or fields[name][0] is None:
                return None
            raw, excerpt = fields[name]
            return Declared(convert(raw), excerpt)
        def regions(raw):
            if type(raw) is not list or any(type(v) is not str for v in raw):
                raise ValueError()
            return tuple(raw)
        def dates(raw):
            if type(raw) is not dict or set(raw) != {'start', 'end'}:
                raise ValueError()
            for key in ('start', 'end'):
                if type(raw[key]) is not str or len(raw[key]) != 10:
                    raise ValueError()
            return DateRange(date.fromisoformat(raw['start']), date.fromisoformat(raw['end']))
        def conditions(raw):
            if type(raw) is not dict:
                raise ValueError()
            return tuple(raw.items())
        def stamp(raw):
            if type(raw) is not str:
                raise ValueError()
            value = datetime.fromisoformat(raw)
            aware(value)
            return value
        return Evidence(evidence_id, fact_key, document, value,
                        optional('regions', regions), optional('dates', dates),
                        optional('conditions', conditions), optional('published_at', stamp),
                        optional('expires_at', stamp))
    except (ValueError, TypeError, KeyError, IndexError):
        raise FactFailure('invalid_structured_evidence') from None
