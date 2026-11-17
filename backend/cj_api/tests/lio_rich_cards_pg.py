"""Read actual signed rich save receipts through the explicit Lio Card3 reader.

C's existing sole-writer fixture supplies real private-PG saves and rollback
controls. Only its HTTP transports are synthetic; no receipt/Trip is inserted by
this reader test, and the default production timeline remains unchanged here.
"""
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests'),str(ROOT/'backend/draft/tests')]
from cj_api.lio_trip_cards import LioTripCards
from cj_api.local_worker_context import checker_for
from cj_message.demo_dialogue import LIO_VERSION_V4
from cj_trip.domain import Denied
from cj_trip.postgres import Repository
from cj_draft.rich_place_selection import RichPlaceSelectionContextSource,LioSelectedRichPublisher
from contracts.message.check_lio_v4 import SCHEMA,REGISTRY,_card3
from jsonschema import Draft202012Validator,FormatChecker
import lio_exploration_flow_pg as native
import rich_publication_pg as writer


def main():
    original_prepare=writer.prepare
    original_receipt=Repository.rich_plan_receipt
    active=[];read=[];reading=False
    validator=Draft202012Validator(dict(
        **{'$defs':SCHEMA['$defs'],'$ref':'#/$defs/Card3'}),registry=REGISTRY,format_checker=FormatChecker())

    def prepare(*args):
        fixture=original_prepare(*args);active.append(fixture);return fixture

    def receipt(repository,binding):
        nonlocal reading
        value=original_receipt(repository,binding)
        if value is None or reading:return value
        fixture=active[-1]
        token=native.dev_auth.token(fixture.auth,native.SUBJECT,3600)
        reader=LioTripCards(fixture.database,checker_for(fixture.auth),calendar=True,rich=True)
        reading=True
        try:
            card=reader.read(token,binding,protocol=LIO_VERSION_V4)
            validator.validate(card);_card3(card)
            assert card['trip_id']==value.trip_id and card['trip_version']==value.committed_version
            trip=repository.detail(value.trip_id)
            assert card['content_version']=='structured.4'
            from hashlib import sha256
            assert card['content_sha256']==sha256(trip.content).hexdigest()
            assert [day['day_index']for day in card['days']]==[1,2,3]
            for old in (LioTripCards(fixture.database,checker_for(fixture.auth)),
                        LioTripCards(fixture.database,checker_for(fixture.auth),calendar=True)):
                try:old.read(token,binding,protocol=LIO_VERSION_V4)
                except Denied:pass
                else:raise AssertionError('rich receipt was projected through a legacy reader')
            for extra in ({'edit':True},{'conversion':True}):
                try:reader.read(token,binding,protocol=LIO_VERSION_V4,**extra)
                except Denied:pass
                else:raise AssertionError('rich planning receipt became an unimplemented edit/conversion receipt')
            foreign=native.dev_auth.token(fixture.auth,native.OUTSIDE,3600)
            try:reader.read(foreign,binding,protocol=LIO_VERSION_V4)
            except Denied:pass
            else:raise AssertionError('another owner read the original rich receipt')
            read.append(binding.run_id)
            print('PASS actual rich Card3 original receipt/version/hash and AUTH/old-reader negatives RUN '+binding.run_id,flush=True)
        finally:reading=False
        return value

    def exercise(root,conninfo):
        return writer.exercise(root,conninfo,source_type=RichPlaceSelectionContextSource,
            publisher_type=LioSelectedRichPublisher,provider_available=True)

    with patch.object(writer,'prepare',prepare),patch.object(Repository,'rich_plan_receipt',receipt), \
            patch.object(native,'exercise',exercise):native.main()
    assert len(active)==1 and len(read)==6
    print('PASS ZH3/EN3 six actual signed rich saves -> receipt-bound native Card3; two late withdrawals remain zero-write; fixture suppliers only, full host/timeline factory/G6 UNRUN',flush=True)


if __name__=='__main__':main()
