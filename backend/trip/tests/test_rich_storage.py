from copy import deepcopy
import json
from pathlib import Path

import pytest

from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus, TrustedPrincipal
from cj_trip.auth_boundary import Boundary
from cj_trip.domain import Denied, Proposal, packed
from cj_trip.postgres import Repository

CASES=json.loads((Path(__file__).resolve().parents[3]/'contracts/trip/structured-examples.4.json').read_bytes())['cases']


def no_connection():
    raise AssertionError('consumer refusal must precede database access')


def test_legacy_validated_direct_source_writer_keeps_its_existing_ingress():
    class Cursor:
        def __init__(self): self.statements = []
        def execute(self, statement, arguments): self.statements.append((statement, arguments))
        def fetchone(self): return None

    event = {key: {'state': 'unknown'} for key in ('date', 'time', 'timezone', 'utc_offset')}
    raw = packed(dict(content_version='structured.1', title='Original validated itinerary', sources=[],
        items=[dict(id='legacy-item', text='Original stop', verification='pending', evidence=[],
            schedule=dict(start=event, end=event), fixed={'state': 'unknown'},
            source_category='user_provided', source_refs=[])]))
    proposal = Proposal('legacy-proposal', 'legacy-trip', 0, 'legacy-source', 9999999999, raw)
    repository = Repository(no_connection, 'owner')
    cursor = Cursor()
    assert repository._publish_in_tx(cursor, proposal) == proposal.digest('owner')
    assert len(cursor.statements) == 2
    assert cursor.statements[1][1][6] == raw
    # Its public consumer still cannot read/publish structured data implicitly.
    with pytest.raises(Denied): repository.publish(proposal)


def test_rich_proposal_data_is_canonical_but_old_ingress_does_not_gain_admission():
    for case in CASES.values():
        raw=packed(case['content'])
        proposal=Proposal('fixture-proposal','fixture-trip',0,'fixture-rich-read',9999999999,raw)
        for flags in ({},{'structured':True},{'structured':True,'calendar':True}):
            repository=Repository(no_connection,'owner',**flags)
            with pytest.raises(Denied):repository.publish(proposal)
            with pytest.raises(Denied):repository._publish_in_tx(None,proposal)
            with pytest.raises(Denied):repository._content(raw)
        admitted=Repository(no_connection,'owner',structured=True,calendar=True,rich=True)
        assert admitted._content(raw)==raw
    with pytest.raises(ValueError):
        Proposal('fixture-proposal','fixture-trip',0,'fixture-rich-read',9999999999,
                 json.dumps(CASES['unconfirmed']['content'],indent=2).encode())
    bad=deepcopy(CASES['unconfirmed']['content'])
    bad['lodging']['recommendations'][0]['price']=100
    with pytest.raises(ValueError):
        Proposal('fixture-proposal','fixture-trip',0,'fixture-rich-read',9999999999,packed(bad))


def test_rich_is_an_explicit_server_capability_and_final_binding_cannot_change():
    for flags in ({'rich':True},{'rich':True,'structured':True}):
        with pytest.raises(ValueError):Repository(no_connection,'owner',**flags)
        with pytest.raises(ValueError):Boundary(**flags)
    principal=TrustedPrincipal('issuer','subject','audience',1,1,9999999999)
    class Checker:
        def check(self,token):
            return AdmissionDecision(AdmissionStatus.ALLOWED,AdmissionReason.ACCEPTED,principal)
    boundary=Boundary(Checker(),lambda _:(no_connection,'owner'),structured=True,calendar=True,rich=True)
    def project(context):
        assert context.metadata.principal==principal
        boundary.rich=False
        return b'withheld private data'
    with pytest.raises(Denied):boundary.with_operation('synthetic',project)
