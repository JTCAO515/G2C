"""Canonical metadata records from D/R's frozen cross-binding fixture v1.

This boundary validates structure only. A well-formed record grants no access
and is not evidence that its declarations agree with protected originals.
"""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import re
from typing import Annotated, Literal

from pydantic import (AfterValidator, BaseModel, BeforeValidator, ConfigDict,
                      Field, StringConstraints, ValidationError, model_validator)

from .contract import Binding, Invalid, Pins, decode, digest, encode, require


VERSION = 'G2C-cross-binding-fixture.1'
SPEC_RELEASE = '929db2b28abc2f0c75ab0a49ba0ac82219213afa'
SCHEMA_SHA256 = '488ab9357fd15b6188207a714e07e109ec942435144eaad8dc2f440bdc0340aa'
MAX_RECORD_BYTES = 1_048_576
Status = Literal['PASS', 'FAIL', 'UNKNOWN', 'UNRUN']
Hash = Annotated[str, StringConstraints(pattern=r'^[a-f0-9]{64}$')]
Label = Annotated[str, StringConstraints(min_length=1, max_length=256, pattern=r'^[^\s\x00]+$')]

def _json_integer(value):
    # Draft2020-12 integer includes integral JSON numbers such as 1.0. Preserve
    # the original wire for hashes; normalize only the validated domain value.
    if type(value) is float and value.is_integer():
        return int(value)
    return value


Positive = Annotated[int, BeforeValidator(_json_integer), Field(ge=1)]
Count = Annotated[int, BeforeValidator(_json_integer), Field(ge=0)]


def _timestamp(value):
    if type(value) is not str or re.fullmatch(
            r'[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}'
            r'(?:\.[0-9]+)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])', value) is None:
        raise ValueError('aware RFC3339 instant required')
    datetime.fromisoformat(value)
    return value


Timestamp = Annotated[str, AfterValidator(_timestamp)]


def _array(value):
    if type(value) is not list:
        raise ValueError('JSON array required')
    return tuple(value)


def _unique(value):
    if len(value) != len(set(value)):
        raise ValueError('duplicate record item')
    return value


class Metadata(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class OriginalReference(Metadata):
    ref: Annotated[str, StringConstraints(pattern=r'^original-[a-f0-9]{64}$')]
    sha256: Hash


References = Annotated[tuple[OriginalReference, ...], BeforeValidator(_array),
                       Field(max_length=256), AfterValidator(_unique)]


class BindingReference(Metadata):
    binding_sha256: Hash
    binding_ref: OriginalReference
    owner_scope_sha256: Hash


class StateSnapshot(Metadata):
    observed_at: Timestamp
    trip_id_sha256: Hash
    trip_version: Positive
    content_sha256: Hash
    state_ref: OriginalReference


class Preparation(Metadata):
    binding: BindingReference
    status: Status
    purpose_authorization_ref: OriginalReference | None
    window_ref: OriginalReference | None
    original_request_inventory_ref: OriginalReference | None
    original_action_inventory_ref: OriginalReference | None
    meter_inventory_ref: OriginalReference | None
    fee_inventory_ref: OriginalReference | None
    trip_receipt_ref: OriginalReference | None
    completed_at: Timestamp | None


class PreparationCost(Metadata):
    charge_id: Label
    charged_batch_id: Label
    ledger_id_sha256: Hash
    original_cost_anchor_ref: OriginalReference | None
    cost_inventory_ref: OriginalReference | None
    allocation_ref: OriginalReference | None
    mode: Literal['original_ledger_read_only']


class ReusePolicy(Metadata):
    registry_ref: OriginalReference
    consumer_registration_ref: OriginalReference
    valid_from: Timestamp
    valid_until: Timestamp
    maximum_uses: Positive
    baseline_mutation: Literal['forbidden']
    preparation_charge: Literal['original_charge_once_references_on_reuse']


class FixtureDefinition(Metadata):
    version: Literal[VERSION]
    kind: Literal['definition']
    fixture_id: Label
    fixture_revision: Positive
    task_id: Literal['val-owner']
    source: Literal['authorized_synthetic_native_trip']
    frozen_at: Timestamp
    producer: Preparation
    baseline: StateSnapshot | None
    private_sentinel_set_ref: OriginalReference | None
    preparation_cost: PreparationCost
    reuse_policy: ReusePolicy

    @model_validator(mode='after')
    def complete_preparation(self):
        if self.producer.status == 'PASS':
            p = self.producer
            c = self.preparation_cost
            required = (p.purpose_authorization_ref, p.window_ref, p.original_request_inventory_ref,
                        p.original_action_inventory_ref, p.meter_inventory_ref, p.fee_inventory_ref,
                        p.trip_receipt_ref, p.completed_at, self.baseline, self.private_sentinel_set_ref,
                        c.original_cost_anchor_ref, c.cost_inventory_ref, c.allocation_ref)
            if any(value is None for value in required):
                raise ValueError('PASS preparation requires complete references')
        return self


class Probe(Metadata):
    probe_id: Label
    operation_kind: Literal['foreign_read', 'foreign_mutation', 'task_message']
    original_request_ref: OriginalReference
    original_response_ref: OriginalReference | None
    association_ref: OriginalReference
    request_sha256: Hash
    sent_at: Timestamp
    terminal_at: Timestamp | None
    result: Literal['DENIED', 'NO_DISPATCH', 'RETURNED', 'UNKNOWN', 'UNRUN']


Probes = Annotated[tuple[Probe, ...], BeforeValidator(_array), Field(max_length=256), AfterValidator(_unique)]


class Consumer(Metadata):
    binding: BindingReference
    pins_sha256: Hash
    experiment_ref: OriginalReference
    public_release_ref: OriginalReference
    batch_id: Label
    candidate_id: Label
    task_id: Literal['val-owner']
    language: Literal['zh', 'en']
    attempt_id: Label
    step_id: Label
    request_sha256: Hash
    request_association_ref: OriginalReference | None
    inventory_ref: OriginalReference | None
    probes: Probes
    task_terminal_at: Timestamp | None


class Observer(Metadata):
    binding: BindingReference
    qualification_ref: OriginalReference | None
    pre_authority_ref: OriginalReference | None
    post_authority_ref: OriginalReference | None
    publication_authority_ref: OriginalReference | None
    before: StateSnapshot | None
    after: StateSnapshot | None
    disclosure_scan_ref: OriginalReference | None
    consumer_evidence_inventory_ref: OriginalReference | None
    foreign_read_rows: Count | None
    foreign_mutations: Count | None
    private_visible_hits: Count | None
    checked_at: Timestamp | None
    dispatch_authority_ref: OriginalReference | None


class CostAttribution(Metadata):
    charge_id: Label
    charged_batch_id: Label
    allocation_ref: OriginalReference | None
    treatment: Literal['first_attribution', 'reuse_reference', 'UNKNOWN', 'UNRUN']
    batch_cost_report_ref: OriginalReference | None


class Check(Metadata):
    status: Status
    reason: Literal['MISSING_ORIGINAL', 'ASSOCIATION_MISMATCH', 'AUTHORITY_UNAVAILABLE',
                    'FIXTURE_CHANGED', 'PRIVATE_DISCLOSURE', 'COST_UNRESOLVED',
                    'NOT_STARTED', 'UNSUPPORTED_RELEASE', 'INCOMPLETE_INVENTORY'] | None
    evidence_refs: References


class Checks(Metadata):
    producer_chain: Check
    fixture_identity: Check
    reuse_admission: Check
    observer_authority: Check
    consumer_probe_binding: Check
    consumer_inventory: Check
    foreign_read_observation: Check
    foreign_write_observation: Check
    before_after_consistency: Check
    private_disclosure_scan: Check
    cost_accounting: Check


class Coverage(Metadata):
    foreign_read_interface: Status
    foreign_write_interface: Status
    model_visible_exact_scan: Status
    user_visible_exact_scan: Status
    semantic_disclosure_review: Status


class FixtureUse(Metadata):
    version: Literal[VERSION]
    kind: Literal['use']
    use_id: Label
    definition_ref: OriginalReference
    fixture_id: Label
    fixture_revision: Positive
    reservation_ref: OriginalReference | None
    consumer: Consumer
    observer: Observer | None
    cost_attribution: CostAttribution
    stage: Literal['NOT_STARTED', 'PROBE_STARTED', 'COMPLETE']
    evidence_status: Status
    checks: Checks
    published_at: Timestamp | None
    isolation_ref: OriginalReference | None
    coverage: Coverage

    @model_validator(mode='after')
    def status_constraints(self):
        checks = self.checks.model_dump()
        coverage = self.coverage.model_dump()
        if (any(item['status'] == 'FAIL' for item in checks.values()) or 'FAIL' in coverage.values()):
            if self.evidence_status != 'FAIL':
                raise ValueError('known FAIL requires root FAIL')
        if self.evidence_status == 'UNRUN':
            if self.stage != 'NOT_STARTED' or self.consumer.probes or self.consumer.task_terminal_at is not None:
                raise ValueError('UNRUN requires unstarted task')
        if self.evidence_status == 'PASS':
            if self.stage != 'COMPLETE' or self.observer is None or not self.consumer.probes:
                raise ValueError('PASS requires complete observation')
            o, c, cost = self.observer, self.consumer, self.cost_attribution
            required = (self.reservation_ref, self.published_at, self.isolation_ref,
                        c.request_association_ref, c.inventory_ref, c.task_terminal_at,
                        o.qualification_ref, o.pre_authority_ref, o.dispatch_authority_ref,
                        o.post_authority_ref, o.publication_authority_ref, o.before, o.after,
                        o.disclosure_scan_ref, o.consumer_evidence_inventory_ref, o.checked_at,
                        cost.allocation_ref, cost.batch_cost_report_ref)
            if any(value is None for value in required) or cost.treatment not in ('first_attribution', 'reuse_reference'):
                raise ValueError('PASS requires complete references')
            if (o.foreign_read_rows, o.foreign_mutations, o.private_visible_hits) != (0, 0, 0):
                raise ValueError('PASS requires observed zeros')
            if any(item['status'] != 'PASS' or item['reason'] is not None or not item['evidence_refs']
                   for item in checks.values()):
                raise ValueError('PASS requires every evidence check')
            if any(coverage[name] != 'PASS' for name in ('foreign_read_interface',
                    'model_visible_exact_scan', 'user_visible_exact_scan')):
                raise ValueError('PASS requires read and exact-scan coverage')
        return self


def decode_record(raw: bytes) -> FixtureDefinition | FixtureUse:
    """Validate canonical wire bytes, never print private invalid input values."""
    require(type(raw) is bytes and len(raw) <= MAX_RECORD_BYTES, 'FIXTURE_RECORD_BOUND')
    try:
        value = decode(raw)
    except (ValueError, RecursionError):
        raise Invalid('FIXTURE_RECORD_JSON') from None
    require(type(value) is dict and value.get('version') == VERSION, 'FIXTURE_RECORD_VERSION')
    try:
        canonical = encode(value)
    except (ValueError, RecursionError):
        raise Invalid('FIXTURE_RECORD_CANONICAL') from None
    require(canonical == raw, 'FIXTURE_RECORD_CANONICAL')
    try:
        if value.get('kind') == 'definition':
            return FixtureDefinition.model_validate(value)
        if value.get('kind') == 'use':
            return FixtureUse.model_validate(value)
    except ValidationError:
        raise Invalid('FIXTURE_RECORD_SCHEMA') from None
    raise Invalid('FIXTURE_RECORD_KIND')


@dataclass(frozen=True)
class LinkedRecords:
    """Structurally valid metadata linked to G's already established E context.

    This is not a source/authority verdict. Protected source resolution, registry,
    cost, observation, scan and publication checks remain mandatory.
    """
    definition: FixtureDefinition
    use: FixtureUse
    definition_wire: bytes
    use_wire: bytes


def link_records(definition_raw: bytes, use_raw: bytes, *, binding: Binding,
                 pins: Pins, request: dict) -> LinkedRecords:
    """Reject contradictory metadata before any cross-binding source lookup.

    binding/pins/request come from G's original context, not from the supplied
    fixture record. No reference is resolved and no C privilege is acquired here.
    A successful return must never be converted into evidence_status=PASS.
    """
    definition, use = decode_record(definition_raw), decode_record(use_raw)
    require(definition.kind == 'definition' and use.kind == 'use', 'FIXTURE_RECORD_KIND')
    require(use.definition_ref.sha256 == sha256(definition_raw).hexdigest(), 'FIXTURE_DEFINITION_HASH')
    require((definition.fixture_id, definition.fixture_revision, definition.task_id) ==
            (use.fixture_id, use.fixture_revision, use.consumer.task_id), 'FIXTURE_IDENTITY_MISMATCH')
    c = use.consumer
    require(c.binding.binding_sha256 == binding.key and
            c.binding.owner_scope_sha256 == sha256(binding.scope.encode()).hexdigest(),
            'FIXTURE_CONSUMER_BINDING_MISMATCH')
    require(c.pins_sha256 == pins.key, 'FIXTURE_CONSUMER_PINS_MISMATCH')
    require((c.attempt_id, c.step_id, c.request_sha256) ==
            (request['attempt_id'], request['step_id'], digest(request)), 'FIXTURE_CONSUMER_REQUEST_MISMATCH')
    producer = definition.producer.binding
    require(producer.owner_scope_sha256 != c.binding.owner_scope_sha256, 'FIXTURE_REQUIRES_DIFFERENT_OWNER')
    if use.observer is not None:
        observer = use.observer.binding
        # Different approved metadata refs may describe the same Binding.key.
        # A different session/key is never accepted merely because scope agrees.
        require((observer.binding_sha256, observer.owner_scope_sha256) ==
                (producer.binding_sha256, producer.owner_scope_sha256), 'FIXTURE_OBSERVER_BINDING_MISMATCH')
    require((use.cost_attribution.charge_id, use.cost_attribution.charged_batch_id) ==
            (definition.preparation_cost.charge_id, definition.preparation_cost.charged_batch_id),
            'FIXTURE_ORIGINAL_CHARGE_MISMATCH')
    return LinkedRecords(definition, use, definition_raw, use_raw)
