"""Appended model plan with code-owned PLACE choices; no acquisition authority."""
from base64 import b64decode
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json

from cj_agent.draft import _model_object
from cj_place import Outcome
from cj_needs.revision_lease import LeaseUnavailable
from cj_trip.domain import packed
from cj_trip.needs_plan import build as build_needs
from .provenance import _source

MODEL_VERSION='TRIP-place-plan.1'
INPUT_VERSION='TRIP-place-source-input.1'


@dataclass(frozen=True,repr=False)
class PlaceChoice:
    choice_id:str
    source:dict

    def public_value(self):
        record=json.loads(b64decode(self.source['snapshot_utf8_base64']))['record']
        return dict(choice_id=self.choice_id,place=record['place'],query=record['query'],source=record['source'])


def choices(batch):
    """Typed results come from B's actual boundary; these projections are data."""
    values=[]
    for observation in batch.observations:
        result=observation.result
        if result.outcome is Outcome.NO_RESULTS:continue
        if result.outcome is not Outcome.OK:raise LeaseUnavailable('unavailable PLACE observation cannot be a source')
        for index,place in enumerate(result.places):
            if result.source is None:raise LeaseUnavailable('actual PLACE source required')
            identity=packed([observation.operation_key,observation.request_ref,index,place.provider,place.provider_id])
            source=_source(len(values)+1,'place',result.source.request_ref,place.name_zh,
                           dict(source=result.source,query=result.query,place=place),result.source.evidence)
            values.append(PlaceChoice('place-'+sha256(identity).hexdigest(),source))
            if len(values)>40:raise LeaseUnavailable('bounded PLACE choices required')
    return tuple(values)


def build(raw,capture,available,content_version):
    if type(raw) is not bytes or not 0<len(raw)<=1_000_000:raise ValueError('bounded place plan required')
    model=json.loads(raw,object_pairs_hook=_model_object)
    if (type(model) is not dict or set(model)!={'version','title','items','proposed_subjects','place_refs'}
            or model['version']!=MODEL_VERSION):raise ValueError('explicit place plan version/fields required')
    refs=model['place_refs']
    if type(refs) is not dict or len(refs)>40 or any(type(v) is not str for v in refs.values()):
        raise ValueError('bounded explicit item/choice references required')
    # Original NEEDS builder/protection is the only declaration engine. Model
    # snapshots/source_refs/queried labels never reach the document as authority.
    legacy={key:deepcopy(model[key]) for key in ('title','items','proposed_subjects')}
    legacy['version']='TRIP-model-plan.1'
    content,candidate,report=build_needs(packed(legacy),capture)
    document=json.loads(content);items={v['id']:v for v in document['items']}
    offered={v.choice_id:v for v in available}
    if not set(refs)<=set(items) or not set(refs.values())<=set(offered):
        raise ValueError('only original items and actual offered choices are allowed')
    used=set()
    for item_id,choice_id in refs.items():
        source=offered[choice_id].source;item=items[item_id]
        if item['text']!=source['text']:raise ValueError('queried text must retain the exact provider name')
        item.update(source_category='queried',source_refs=[source['id']])
        used.add(choice_id)
    document['sources']=[v.source for v in available if v.choice_id in used]
    document['content_version']=content_version
    if content_version=='structured.1':
        from cj_trip.structured import validate_document
        from cj_feasibility.trip_time import evaluate
    elif content_version=='structured.2':
        from cj_trip.structured_v2 import validate_document
        from cj_feasibility.trip_time_v2 import evaluate
    else:raise ValueError('explicit supported structured content required')
    validate_document(document)
    encoded=packed(document)
    if len(encoded)>1_000_000:raise ValueError('bounded place plan required')
    if evaluate(encoded).status=='CONFLICT':raise ValueError('explicit Trip time conflict')
    return encoded,candidate,report
