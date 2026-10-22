"""FACT evidence and deterministic applicability. Local data, never authentication."""
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Generic, TypeVar

VERSION = "CJ-FACT-INTERNAL@0.1.0-rc.1"
T = TypeVar("T")


def aware(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone_required")
    _instant(value)  # Reject unrepresentable UTC instants at every timestamp boundary.


def _instant(value: datetime) -> datetime:
    """Comparison view only; preserve original source datetime, offset and fold."""
    try:
        return value.astimezone(timezone.utc)
    except OverflowError:
        raise ValueError("instant_out_of_range") from None


@dataclass(frozen=True)
class DateRange:
    """Inclusive calendar dates, already interpreted in the source's stated locale."""
    start: date
    end: date

    def __post_init__(self):
        if type(self.start) is not date or type(self.end) is not date or self.end < self.start:
            raise ValueError("invalid_date_range")

    def contains(self, other: 'DateRange') -> bool:
        return self.start <= other.start and other.end <= self.end


@dataclass(frozen=True, repr=False)
class Excerpt:
    """Exact Unicode offsets in the decoded ORIGINAL document, end exclusive."""
    start: int
    end: int
    text: str

    def validate(self, original: str) -> None:
        if (type(self.start) is not int or type(self.end) is not int
                or not 0 <= self.start < self.end <= len(original)
                or original[self.start:self.end] != self.text):
            raise ValueError("invalid_excerpt")


@dataclass(frozen=True, repr=False)
class Declared(Generic[T]):
    """Explicit extraction + provenance, NOT semantic verification of that extraction."""
    value: T
    excerpt: Excerpt


@dataclass(frozen=True, repr=False)
class Document:
    source_url: str
    retrieved_at: datetime
    media_type: str
    original: bytes = field(repr=False)
    text: str = field(repr=False)
    synthetic: bool

    def __post_init__(self):
        from .policy import canonical_url
        canonical_url(self.source_url)
        aware(self.retrieved_at)
        if (type(self.original) is not bytes or type(self.text) is not str
                or self.original.decode('utf-8', errors='strict') != self.text
                or self.media_type not in ('text/plain', 'application/json')
                or type(self.synthetic) is not bool):
            raise ValueError("invalid_document")

    @property
    def sha256(self) -> str:
        return sha256(self.original).hexdigest()


@dataclass(frozen=True, repr=False)
class Explanation:
    language: str
    text: str
    kind: str  # source_excerpt / machine_translation / model_explanation
    original: Excerpt

    def validate(self, text: str):
        self.original.validate(text)
        if self.language not in ('zh', 'en') or not self.text:
            raise ValueError('invalid_explanation')
        if self.kind not in ('source_excerpt', 'machine_translation', 'model_explanation'):
            raise ValueError('invalid_explanation_kind')
        if self.kind == 'source_excerpt' and self.text != self.original.text:
            raise ValueError('source_text_must_be_original')


@dataclass(frozen=True, repr=False)
class Evidence:
    evidence_id: str
    fact_key: str
    document: Document
    value: Declared[str]
    regions: Declared[tuple[str, ...]] | None = None
    dates: Declared[DateRange] | None = None
    conditions: Declared[tuple[tuple[str, str], ...]] | None = None
    published_at: Declared[datetime] | None = None
    expires_at: Declared[datetime] | None = None
    explanations: tuple[Explanation, ...] = ()

    def __post_init__(self):
        if (type(self.evidence_id) is not str or not self.evidence_id
                or type(self.fact_key) is not str or not self.fact_key
                or type(self.value.value) is not str or not self.value.value):
            raise ValueError('invalid_evidence')
        # Values remain exact source substrings; no normalized/translated answer.
        if self.value.value != self.value.excerpt.text:
            raise ValueError('value_must_be_original')
        for declaration in (self.value, self.regions, self.dates, self.conditions, self.published_at, self.expires_at):
            if declaration is not None:
                declaration.excerpt.validate(self.document.text)
        if self.regions is not None:
            regions = self.regions.value
            if type(regions) is not tuple or not regions or any(type(v) is not str or not v for v in regions):
                raise ValueError('invalid_regions')
        if self.dates is not None and not isinstance(self.dates.value, DateRange):
            raise ValueError('invalid_dates')
        if self.conditions is not None:
            validate_conditions(self.conditions.value)
        for stamp in (self.published_at, self.expires_at):
            if stamp is not None:
                aware(stamp.value)
        if (self.published_at is not None and self.expires_at is not None
                and _instant(self.expires_at.value) <= _instant(self.published_at.value)):
            raise ValueError('invalid_validity')
        if type(self.explanations) is not tuple:
            raise ValueError('immutable_explanations_required')
        for explanation in self.explanations:
            explanation.validate(self.document.text)


def validate_conditions(items):
    if (type(items) is not tuple or any(type(pair) is not tuple or len(pair) != 2
            or any(type(v) is not str or not v for v in pair) for pair in items)
            or len({key for key, _ in items}) != len(items)):
        raise ValueError('invalid_conditions')


@dataclass(frozen=True, repr=False)
class Query:
    fact_key: str
    region: str
    dates: DateRange
    conditions: tuple[tuple[str, str], ...]
    evaluated_at: datetime

    def __post_init__(self):
        aware(self.evaluated_at)
        validate_conditions(self.conditions)
        if (type(self.fact_key) is not str or not self.fact_key
                or type(self.region) is not str or not self.region or not isinstance(self.dates, DateRange)):
            raise ValueError('invalid_query')


class Status(str, Enum):
    SUPPORTED = 'supported'
    OUT_OF_RANGE = 'unsupported_or_out_of_range'
    EXPIRED = 'expired'
    CONFLICTING = 'conflicting'
    UNKNOWN = 'unknown'


@dataclass(frozen=True, repr=False)
class Assessment:
    evidence: Evidence
    status: Status
    reasons: tuple[str, ...]


@dataclass(frozen=True, repr=False)
class Result:
    query: Query
    status: Status
    assessments: tuple[Assessment, ...]
    original_value: str | None
    summary_zh: str
    summary_en: str


_SUMMARIES = {
    Status.SUPPORTED: ('所给证据声明覆盖查询范围；请核对原文和条件。', 'The supplied declarations cover this query; check the original text and conditions.'),
    Status.OUT_OF_RANGE: ('查询超出所给证据声明的适用范围。', 'The query is outside the declared evidence scope.'),
    Status.EXPIRED: ('所给证据已过声明的有效期，需重新核实。', 'The supplied evidence has expired; verification is needed.'),
    Status.CONFLICTING: ('适用证据的原始值不一致，需核实，不能选定答案。', 'Applicable original values differ; verification is needed before choosing an answer.'),
    Status.UNKNOWN: ('证据或适用信息不完整，待核实。', 'Evidence or applicability information is incomplete; verification is needed.'),
}


def _assess(query: Query, evidence: Evidence) -> Assessment:
    reasons = []
    if evidence.fact_key != query.fact_key:
        return Assessment(evidence, Status.OUT_OF_RANGE, ('fact_key_mismatch',))
    if (_instant(evidence.document.retrieved_at) > _instant(query.evaluated_at) or
            (evidence.published_at is not None
             and _instant(evidence.published_at.value) > _instant(evidence.document.retrieved_at))):
        return Assessment(evidence, Status.UNKNOWN, ('future_observation_or_publication',))
    if (evidence.expires_at is not None
            and _instant(query.evaluated_at) >= _instant(evidence.expires_at.value)):
        return Assessment(evidence, Status.EXPIRED, ('expiry_reached',))
    if evidence.regions is None:
        reasons.append('region_not_declared')
    elif query.region not in evidence.regions.value:
        return Assessment(evidence, Status.OUT_OF_RANGE, ('region_mismatch',))
    if evidence.dates is None:
        reasons.append('dates_not_declared')
    elif not evidence.dates.value.contains(query.dates):
        return Assessment(evidence, Status.OUT_OF_RANGE, ('outside_declared_dates',))
    if evidence.conditions is None:
        reasons.append('conditions_not_declared')
    else:
        supplied = dict(query.conditions)
        for key, value in evidence.conditions.value:
            if key not in supplied:
                reasons.append('condition_not_supplied')
            elif supplied[key] != value:
                return Assessment(evidence, Status.OUT_OF_RANGE, ('condition_mismatch',))
    # A forecast date window does not invent a freshness lifetime.
    if evidence.expires_at is None:
        reasons.append('expiry_not_declared')
    return Assessment(evidence, Status.UNKNOWN if reasons else Status.SUPPORTED, tuple(dict.fromkeys(reasons)))


def evaluate(query: Query, evidence: tuple[Evidence, ...]) -> Result:
    """No IO. Conservative exact-value comparison, no fuzzy semantic/legal inference."""
    if type(evidence) is not tuple or len({item.evidence_id for item in evidence}) != len(evidence):
        raise ValueError('unique_immutable_evidence_required')
    assessed = tuple(_assess(query, item) for item in evidence)
    eligible = [item for item in assessed if item.status == Status.SUPPORTED]
    values = {item.evidence.value.value for item in eligible}
    if len(values) > 1:
        status = Status.CONFLICTING
    elif any(item.status == Status.UNKNOWN for item in assessed):
        # An incomplete potentially applicable conflicting source must not vanish.
        status = Status.UNKNOWN
    elif eligible:
        status = Status.SUPPORTED
    elif assessed and all(item.status == Status.EXPIRED for item in assessed):
        status = Status.EXPIRED
    elif assessed and all(item.status == Status.OUT_OF_RANGE for item in assessed):
        status = Status.OUT_OF_RANGE
    else:
        status = Status.UNKNOWN
    zh, en = _SUMMARIES[status]
    return Result(query, status, assessed, next(iter(values)) if status == Status.SUPPORTED else None, zh, en)
