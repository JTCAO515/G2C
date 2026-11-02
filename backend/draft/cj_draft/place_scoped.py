"""PLACE-SCOPED@1: keep accepted mutable intent without changing old profiles."""
import base64,json
from dataclasses import dataclass,replace
from cj_needs.contract_v1 import decode_snapshot
from cj_trip.domain import Denied,packed
from cj_trip.needs_lineage import current_origin
from cj_trip.current_needs_source import CurrentSource
from cj_feasibility.scoped_trip import check
from cj_message.edit_protocol import EditConfiguration
from cj_message.edit_result_protocol import EditResultConfiguration
from .scoped_publisher import ScopedPublisher,local_configuration as original_configuration
from .scoped_result_publisher import ScopedResultPublisher


@dataclass(frozen=True,repr=False)
class _BaselineSource(CurrentSource):
    accepted_baseline:bool


class _AcceptedBaseline:
    def capture_state(self,binding,source,token,scope):
        state=super().capture_state(binding,source,token,scope)
        allowed=False
        if state.previous!=packed({}):
            repository=self.repository(binding.scope)
            with repository.transaction() as cur:origin=current_origin(cur,repository,scope.original)
            try:original=decode_snapshot(base64.b64decode(json.loads(origin['source'])['snapshot'],validate=True))
            except (ValueError,TypeError,KeyError) as exc:raise Denied('accepted source baseline unavailable') from exc
            # A newer NEEDS correction cannot inherit an older accepted override.
            allowed=original==state.needs.records()[0]
        return replace(state,needs=_BaselineSource(state.needs.raw,allowed))

    def constraint_check(self,content,source,previous,selected,limits):
        return check(content,source,previous,selected,limits,retain_adopted=source.accepted_baseline)


class PlaceScopedPublisher(_AcceptedBaseline,ScopedPublisher):pass
class PlaceScopedResultPublisher(_AcceptedBaseline,ScopedResultPublisher):pass


def local_configuration(*,results=False,**kwargs):
    database,original=original_configuration(**kwargs);p=original.publisher
    cls=PlaceScopedResultPublisher if results else PlaceScopedPublisher
    publisher=cls(database,p.checker,p.credentials,p.memory,p.confirmation,p.limits,language=p.language,clock=p.clock)
    configuration=(EditResultConfiguration if results else EditConfiguration)(original.memory,publisher)
    database.edit_configuration=configuration
    return database,configuration
