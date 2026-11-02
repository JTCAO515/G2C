"""Explicit C consumer of CJ-PLACE-DRAFT@1; old producers stay exact."""
from dataclasses import dataclass
from typing import ClassVar

from cj_trip.domain import packed
from .needs_local import publisher as needs_publisher
from .needs_publisher import NeedsDraftPublisher
from .place_plan import choices,build,INPUT_VERSION

SYSTEM=('TRIP-place-plan.1: return only title/items/proposed_subjects/place_refs and version. '
        'Preserve original NEEDS/fixed declarations. Items retain original unconfirmed source rules, '
        'pending verification, empty evidence and source_refs. place_refs may only select offered choice_id '
        'for an item displaying the exact provider name; never upload snapshots, coordinates, source records, '
        'permissions or verified claims. No offered place means location UNKNOWN, not invented coordinates.')


class PlaceNeedsPublisher(NeedsDraftPublisher):
    system=SYSTEM
    def __init__(self,original,place_sources,content_version):
        super().__init__(original.repository,original.source,original.clock)
        self.place_sources,self.content_version=place_sources,content_version
        self._places={}

    def sources_for(self,binding):
        needs=super().sources_for(binding)
        batch=self.place_sources.capture(binding)
        self._places[binding]=(batch,choices(batch))
        return needs

    def model_messages(self,binding,text,capture,messages):
        before,_=capture.records();_,offered=self._places[binding]
        value=dict(version=INPUT_VERSION,content_version=self.content_version,needs_id=before.needs_id,
                   revision=before.version,fields=before.fields,place_choices=[v.public_value() for v in offered])
        return list(messages)+[dict(role='system',content=packed(value).decode())]

    def build_plan(self,raw,capture):
        batch,offered=self._places[capture.binding]
        # This method runs inside actual publish_for_message, never from holder
        # initialization. The batch is not a permission; B checks its issued lease.
        self.place_sources.check(capture.binding,batch)
        return build(raw,capture,offered,self.content_version)


@dataclass(frozen=True)
class PlaceDraftAdapter:
    content_version:str='structured.2'
    abi:ClassVar[str]='CJ-PLACE-DRAFT-PUBLISHER@1'

    def __post_init__(self):
        if self.content_version not in ('structured.1','structured.2'):
            raise ValueError('explicit structured.1/2 producer required')

    def bind(self,database,checker,message_context,token_supplier,scope,*,place_sources):
        original=needs_publisher(database,checker,message_context,token_supplier,scope)
        return PlaceNeedsPublisher(original,place_sources,self.content_version)
